"""Represent the Freebox router and its devices and sensors."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
from typing import Any

from freebox_api import Freepybox
from freebox_api.api.call import Call
from freebox_api.api.home import Home
from freebox_api.api.wifi import Wifi
from freebox_api.exceptions import HttpRequestError, NotOpenError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import slugify

from .const import (
    API_VERSION,
    APP_DESC,
    CONNECTION_EXTENDED_SENSORS_KEYS,
    CONNECTION_SENSORS_KEYS,
    DOMAIN,
    HOME_COMPATIBLE_CATEGORIES,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

type FreeboxConfigEntry = ConfigEntry[FreeboxRouter]


def is_json(json_str: str) -> bool:
    """Validate if a String is a JSON value or not."""
    try:
        json.loads(json_str)
    except (ValueError, TypeError) as err:
        _LOGGER.error(
            "Failed to parse JSON '%s', error '%s'",
            json_str,
            err,
        )
        return False
    return True


async def get_api(hass: HomeAssistant, host: str) -> Freepybox:
    """Get the Freebox API."""
    freebox_path = Store(hass, STORAGE_VERSION, STORAGE_KEY).path

    if not os.path.exists(freebox_path):
        await hass.async_add_executor_job(os.makedirs, freebox_path)

    token_file = Path(f"{freebox_path}/{slugify(host)}.conf")

    return Freepybox(APP_DESC, token_file, API_VERSION)


async def get_hosts_list_if_supported(
    fbx_api: Freepybox,
) -> tuple[bool, list[dict[str, Any]]]:
    """Hosts list is not supported when freebox is configured in bridge mode."""
    supports_hosts: bool = True
    fbx_devices: list[dict[str, Any]] = []
    try:
        fbx_interfaces = await fbx_api.lan.get_interfaces() or []
        for interface in fbx_interfaces:
            fbx_devices.extend(
                await fbx_api.lan.get_hosts_list(interface["name"]) or []
            )
    except HttpRequestError as err:
        if (
            (matcher := re.search(r"Request failed \(APIResponse: (.+)\)", str(err)))
            and is_json(json_str := matcher.group(1))
            and (json_resp := json.loads(json_str)).get("error_code") == "nodev"
        ):
            # No need to retry, Host list not available
            supports_hosts = False
            _LOGGER.debug(
                "Host list is not available using bridge mode (%s)",
                json_resp.get("msg"),
            )

        else:
            raise

    return supports_hosts, fbx_devices


class FreeboxRouter:
    """Representation of a Freebox router."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: FreeboxConfigEntry,
        api: Freepybox,
        freebox_config: Mapping[str, Any],
    ) -> None:
        """Initialize a Freebox router."""
        self.hass = hass
        self._host = entry.data[CONF_HOST]
        self._port = entry.data[CONF_PORT]

        self._api: Freepybox = api
        self.name: str = freebox_config["model_info"]["pretty_name"]
        self.model_id: str = freebox_config["model_info"]["name"]
        self.mac: str = freebox_config["mac"]
        self._sw_v: str = freebox_config["firmware_version"]
        self._hw_v: str | None = freebox_config.get("board_name")
        self._attrs: dict[str, Any] = {}

        self.supports_hosts = True
        self.devices: dict[str, dict[str, Any]] = {}
        self.disks: dict[int, dict[str, Any]] = {}
        self.supports_raid = True
        self.raids: dict[int, dict[str, Any]] = {}
        self.sensors_temperature: dict[str, int] = {}
        self.sensors_connection: dict[str, float] = {}
        self.call_list: list[dict[str, Any]] = []
        self.home_granted = True
        self.home_devices: dict[str, Any] = {}
        self.listeners: list[Callable[[], None]] = []

        # Extended connection data
        self.connection_media: str = ""
        self.sensors_connection_extended: dict[str, int] = {}

        # xDSL sensors (only available for xDSL connections)
        self.supports_xdsl: bool = True
        self.sensors_xdsl: dict[str, float | int] = {}

        # FTTH sensors (only available for FTTH connections)
        self.supports_ftth: bool = True
        self.sensors_ftth: dict[str, float] = {}

        # Switch port sensors
        self.supports_switch: bool = True
        self.switch_ports: dict[int, dict[str, Any]] = {}

        # Freeplug (powerline) sensors
        self.supports_freeplug: bool = True
        self.freeplug_networks: list[dict[str, Any]] = []

    async def update_all(self, now: datetime | None = None) -> None:
        """Update all Freebox platforms."""
        await self.update_device_trackers()
        await self.update_sensors()
        await self.update_home_devices()

    async def update_device_trackers(self) -> None:
        """Update Freebox devices."""
        new_device = False

        fbx_devices: list[dict[str, Any]] = []

        # Access to Host list not available in bridge mode, API return error_code 'nodev'
        if self.supports_hosts:
            self.supports_hosts, fbx_devices = await get_hosts_list_if_supported(
                self._api
            )

        # Adds the Freebox itself
        fbx_devices.append(
            {
                "primary_name": self.name,
                "l2ident": {"id": self.mac},
                "vendor_name": "Freebox SAS",
                "host_type": "router",
                "active": True,
                "attrs": self._attrs,
            }
        )

        for fbx_device in fbx_devices:
            device_mac = fbx_device["l2ident"]["id"]

            if self.devices.get(device_mac) is None:
                new_device = True

            self.devices[device_mac] = fbx_device

        async_dispatcher_send(self.hass, self.signal_device_update)

        if new_device:
            async_dispatcher_send(self.hass, self.signal_device_new)

    async def update_sensors(self) -> None:
        """Update Freebox sensors."""

        # System sensors
        syst_datas: dict[str, Any] = await self._api.system.get_config()

        # According to the doc `syst_datas["sensors"]` is temperature sensors in celsius degree.
        # Name and id of sensors may vary under Freebox devices.
        for sensor in syst_datas["sensors"]:
            self.sensors_temperature[sensor["name"]] = sensor.get("value")

        # Connection sensors
        connection_datas: dict[str, Any] = await self._api.connection.get_status()
        for sensor_key in CONNECTION_SENSORS_KEYS:
            self.sensors_connection[sensor_key] = connection_datas[sensor_key]

        # Store connection media type and extended connection data
        self.connection_media = connection_datas.get("media", "")
        for sensor_key in CONNECTION_EXTENDED_SENSORS_KEYS:
            if sensor_key in connection_datas:
                self.sensors_connection_extended[sensor_key] = connection_datas[
                    sensor_key
                ]

        self._attrs = {
            "IPv4": connection_datas.get("ipv4"),
            "IPv6": connection_datas.get("ipv6"),
            "connection_type": connection_datas["media"],
            "uptime": datetime.fromtimestamp(
                round(datetime.now().timestamp()) - syst_datas["uptime_val"]
            ),
            "firmware_version": self._sw_v,
            "serial": syst_datas["serial"],
        }

        self.call_list = await self._api.call.get_calls_log()

        await self._update_disks_sensors()
        await self._update_raids_sensors()
        await self._update_xdsl_sensors()
        await self._update_ftth_sensors()
        await self._update_switch_sensors()
        await self._update_freeplug_sensors()

        async_dispatcher_send(self.hass, self.signal_sensor_update)

    async def _update_disks_sensors(self) -> None:
        """Update Freebox disks."""
        # None at first request
        fbx_disks: list[dict[str, Any]] = await self._api.storage.get_disks() or []

        for fbx_disk in fbx_disks:
            disk: dict[str, Any] = {**fbx_disk}
            disk_part: dict[int, dict[str, Any]] = {}
            for fbx_disk_part in fbx_disk["partitions"]:
                disk_part[fbx_disk_part["id"]] = fbx_disk_part
            disk["partitions"] = disk_part
            self.disks[fbx_disk["id"]] = disk

    async def _update_raids_sensors(self) -> None:
        """Update Freebox raids."""
        # None at first request
        if not self.supports_raid:
            return

        try:
            fbx_raids: list[dict[str, Any]] = await self._api.storage.get_raids() or []
        except HttpRequestError:
            self.supports_raid = False
            _LOGGER.warning(
                "Router %s API does not support RAID",
                self.name,
            )
            return

        for fbx_raid in fbx_raids:
            self.raids[fbx_raid["id"]] = fbx_raid

    async def _update_xdsl_sensors(self) -> None:
        """Update xDSL line sensors."""
        if not self.supports_xdsl or self.connection_media != "xdsl":
            return

        try:
            xdsl_data: dict[str, Any] = await self._api.connection.get_xdsl()
        except HttpRequestError:
            self.supports_xdsl = False
            _LOGGER.debug(
                "Router %s API does not support xDSL sensors",
                self.name,
            )
            return

        # Extract downstream data
        if down := xdsl_data.get("down"):
            self.sensors_xdsl["xdsl_maxrate_down"] = down.get("maxrate", 0)
            self.sensors_xdsl["xdsl_rate_down"] = down.get("rate", 0)
            self.sensors_xdsl["xdsl_snr_down"] = down.get("snr", 0)
            self.sensors_xdsl["xdsl_attn_down"] = down.get("attn", 0)
            self.sensors_xdsl["xdsl_crc_down"] = down.get("crc", 0)

        # Extract upstream data
        if up := xdsl_data.get("up"):
            self.sensors_xdsl["xdsl_maxrate_up"] = up.get("maxrate", 0)
            self.sensors_xdsl["xdsl_rate_up"] = up.get("rate", 0)
            self.sensors_xdsl["xdsl_snr_up"] = up.get("snr", 0)
            self.sensors_xdsl["xdsl_attn_up"] = up.get("attn", 0)

    async def _update_ftth_sensors(self) -> None:
        """Update FTTH (fiber) sensors."""
        if not self.supports_ftth or self.connection_media != "ftth":
            return

        try:
            ftth_data: dict[str, Any] = await self._api.connection.get_ftth()
        except HttpRequestError:
            self.supports_ftth = False
            _LOGGER.debug(
                "Router %s API does not support FTTH sensors",
                self.name,
            )
            return

        # Extract SFP optical power data
        if sfp := ftth_data.get("sfp"):
            if "pwr_rx" in sfp:
                self.sensors_ftth["ftth_sfp_pwr_rx"] = sfp["pwr_rx"]
            if "pwr_tx" in sfp:
                self.sensors_ftth["ftth_sfp_pwr_tx"] = sfp["pwr_tx"]

    async def _update_switch_sensors(self) -> None:
        """Update Ethernet switch port sensors."""
        if not self.supports_switch:
            return

        try:
            switch_status: list[dict[str, Any]] = (
                await self._api.switch.get_status() or []
            )
        except HttpRequestError:
            self.supports_switch = False
            _LOGGER.debug(
                "Router %s API does not support switch sensors",
                self.name,
            )
            return

        for port in switch_status:
            port_id = port.get("id")
            if port_id is None:
                continue

            port_data: dict[str, Any] = {
                "id": port_id,
                "link": port.get("link", "down") == "up",
                "speed": port.get("speed", ""),
                "duplex": port.get("duplex", ""),
            }

            # Get port stats
            try:
                stats: dict[str, Any] = await self._api.switch.get_port_stats(port_id)
                port_data["rx_bytes_rate"] = stats.get("rx_bytes_rate", 0)
                port_data["tx_bytes_rate"] = stats.get("tx_bytes_rate", 0)
            except HttpRequestError:
                port_data["rx_bytes_rate"] = 0
                port_data["tx_bytes_rate"] = 0

            self.switch_ports[port_id] = port_data

    async def _update_freeplug_sensors(self) -> None:
        """Update Freeplug (powerline) sensors."""
        if not self.supports_freeplug:
            return

        try:
            freeplug_networks: list[dict[str, Any]] = (
                await self._api.freeplug.get_freeplug_networks() or []
            )
        except HttpRequestError:
            self.supports_freeplug = False
            _LOGGER.debug(
                "Router %s API does not support Freeplug sensors",
                self.name,
            )
            return

        self.freeplug_networks = freeplug_networks

    async def update_home_devices(self) -> None:
        """Update Home devices (alarm, light, sensor, switch, remote ...)."""
        if not self.home_granted:
            return

        try:
            home_nodes: list[Any] = await self.home.get_home_nodes() or []
        except HttpRequestError:
            self.home_granted = False
            _LOGGER.warning("Home access is not granted")
            return

        new_device = False
        for home_node in home_nodes:
            if home_node["category"] in HOME_COMPATIBLE_CATEGORIES:
                if self.home_devices.get(home_node["id"]) is None:
                    new_device = True
                self.home_devices[home_node["id"]] = home_node

        async_dispatcher_send(self.hass, self.signal_home_device_update)

        if new_device:
            async_dispatcher_send(self.hass, self.signal_home_device_new)

    async def reboot(self) -> None:
        """Reboot the Freebox."""
        await self._api.system.reboot()

    async def close(self) -> None:
        """Close the connection."""
        with suppress(NotOpenError):
            await self._api.close()

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        return DeviceInfo(
            configuration_url=f"https://{self._host}:{self._port}/",
            connections={(CONNECTION_NETWORK_MAC, self.mac)},
            identifiers={(DOMAIN, self.mac)},
            manufacturer="Freebox SAS",
            name=self.name,
            model=self.name,
            model_id=self.model_id,
            sw_version=self._sw_v,
            hw_version=self._hw_v,
        )

    @property
    def signal_device_new(self) -> str:
        """Event specific per Freebox entry to signal new device."""
        return f"{DOMAIN}-{self._host}-device-new"

    @property
    def signal_home_device_new(self) -> str:
        """Event specific per Freebox entry to signal new home device."""
        return f"{DOMAIN}-{self._host}-home-device-new"

    @property
    def signal_device_update(self) -> str:
        """Event specific per Freebox entry to signal updates in devices."""
        return f"{DOMAIN}-{self._host}-device-update"

    @property
    def signal_sensor_update(self) -> str:
        """Event specific per Freebox entry to signal updates in sensors."""
        return f"{DOMAIN}-{self._host}-sensor-update"

    @property
    def signal_home_device_update(self) -> str:
        """Event specific per Freebox entry to signal update in home devices."""
        return f"{DOMAIN}-{self._host}-home-device-update"

    @property
    def sensors(self) -> dict[str, Any]:
        """Return sensors."""
        return {**self.sensors_temperature, **self.sensors_connection}

    @property
    def call(self) -> Call:
        """Return the call."""
        return self._api.call

    @property
    def wifi(self) -> Wifi:
        """Return the wifi."""
        return self._api.wifi

    @property
    def home(self) -> Home:
        """Return the home."""
        return self._api.home
