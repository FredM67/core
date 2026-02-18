"""Support for Freebox devices (Freebox v6 and Freebox mini 4K)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfDataRate,
    UnitOfInformation,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .entity import FreeboxHomeEntity
from .router import FreeboxConfigEntry, FreeboxRouter

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class FreeboxSensorEntityDescription(SensorEntityDescription):
    """Describes a Freebox sensor entity."""

    value_fn: Callable[[FreeboxRouter], float | int | None] | None = None
    is_suitable: Callable[[FreeboxRouter], bool] = lambda router: True


CONNECTION_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="rate_down",
        name="Freebox download speed",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.KILOBYTES_PER_SECOND,
        icon="mdi:download-network",
    ),
    SensorEntityDescription(
        key="rate_up",
        name="Freebox upload speed",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.KILOBYTES_PER_SECOND,
        icon="mdi:upload-network",
    ),
)

CALL_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="missed",
        name="Freebox missed calls",
        icon="mdi:phone-missed",
    ),
)

DISK_PARTITION_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="partition_free_space",
        name="free space",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:harddisk",
    ),
)

CONNECTION_EXTENDED_SENSORS: tuple[FreeboxSensorEntityDescription, ...] = (
    FreeboxSensorEntityDescription(
        key="bytes_down",
        translation_key="bytes_down",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda router: router.sensors_connection_extended.get("bytes_down"),
    ),
    FreeboxSensorEntityDescription(
        key="bytes_up",
        translation_key="bytes_up",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda router: router.sensors_connection_extended.get("bytes_up"),
    ),
    FreeboxSensorEntityDescription(
        key="bandwidth_down",
        translation_key="bandwidth_down",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda router: router.sensors_connection_extended.get("bandwidth_down"),
    ),
    FreeboxSensorEntityDescription(
        key="bandwidth_up",
        translation_key="bandwidth_up",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda router: router.sensors_connection_extended.get("bandwidth_up"),
    ),
)

XDSL_SENSORS: tuple[FreeboxSensorEntityDescription, ...] = (
    FreeboxSensorEntityDescription(
        key="xdsl_maxrate_down",
        translation_key="xdsl_maxrate_down",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda router: router.sensors_xdsl.get("xdsl_maxrate_down"),
        is_suitable=lambda router: router.connection_media == "xdsl",
    ),
    FreeboxSensorEntityDescription(
        key="xdsl_maxrate_up",
        translation_key="xdsl_maxrate_up",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda router: router.sensors_xdsl.get("xdsl_maxrate_up"),
        is_suitable=lambda router: router.connection_media == "xdsl",
    ),
    FreeboxSensorEntityDescription(
        key="xdsl_rate_down",
        translation_key="xdsl_rate_down",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda router: router.sensors_xdsl.get("xdsl_rate_down"),
        is_suitable=lambda router: router.connection_media == "xdsl",
    ),
    FreeboxSensorEntityDescription(
        key="xdsl_rate_up",
        translation_key="xdsl_rate_up",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda router: router.sensors_xdsl.get("xdsl_rate_up"),
        is_suitable=lambda router: router.connection_media == "xdsl",
    ),
    FreeboxSensorEntityDescription(
        key="xdsl_snr_down",
        translation_key="xdsl_snr_down",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="dB",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda router: (
            router.sensors_xdsl.get("xdsl_snr_down", 0) / 10
            if router.sensors_xdsl.get("xdsl_snr_down") is not None
            else None
        ),
        is_suitable=lambda router: router.connection_media == "xdsl",
    ),
    FreeboxSensorEntityDescription(
        key="xdsl_snr_up",
        translation_key="xdsl_snr_up",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="dB",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda router: (
            router.sensors_xdsl.get("xdsl_snr_up", 0) / 10
            if router.sensors_xdsl.get("xdsl_snr_up") is not None
            else None
        ),
        is_suitable=lambda router: router.connection_media == "xdsl",
    ),
    FreeboxSensorEntityDescription(
        key="xdsl_attn_down",
        translation_key="xdsl_attn_down",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="dB",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda router: (
            router.sensors_xdsl.get("xdsl_attn_down", 0) / 10
            if router.sensors_xdsl.get("xdsl_attn_down") is not None
            else None
        ),
        is_suitable=lambda router: router.connection_media == "xdsl",
    ),
    FreeboxSensorEntityDescription(
        key="xdsl_attn_up",
        translation_key="xdsl_attn_up",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="dB",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda router: (
            router.sensors_xdsl.get("xdsl_attn_up", 0) / 10
            if router.sensors_xdsl.get("xdsl_attn_up") is not None
            else None
        ),
        is_suitable=lambda router: router.connection_media == "xdsl",
    ),
    FreeboxSensorEntityDescription(
        key="xdsl_crc_down",
        translation_key="xdsl_crc",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda router: router.sensors_xdsl.get("xdsl_crc_down"),
        is_suitable=lambda router: router.connection_media == "xdsl",
    ),
)

FTTH_SENSORS: tuple[FreeboxSensorEntityDescription, ...] = (
    FreeboxSensorEntityDescription(
        key="ftth_sfp_pwr_rx",
        translation_key="ftth_sfp_pwr_rx",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="dBm",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
        value_fn=lambda router: (
            router.sensors_ftth.get("ftth_sfp_pwr_rx", 0) / 100
            if router.sensors_ftth.get("ftth_sfp_pwr_rx") is not None
            else None
        ),
        is_suitable=lambda router: router.connection_media == "ftth",
    ),
    FreeboxSensorEntityDescription(
        key="ftth_sfp_pwr_tx",
        translation_key="ftth_sfp_pwr_tx",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="dBm",
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
        value_fn=lambda router: (
            router.sensors_ftth.get("ftth_sfp_pwr_tx", 0) / 100
            if router.sensors_ftth.get("ftth_sfp_pwr_tx") is not None
            else None
        ),
        is_suitable=lambda router: router.connection_media == "ftth",
    ),
)

SWITCH_PORT_SENSORS: tuple[FreeboxSensorEntityDescription, ...] = (
    FreeboxSensorEntityDescription(
        key="rx_bytes_rate",
        translation_key="switch_port_rx_rate",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    FreeboxSensorEntityDescription(
        key="tx_bytes_rate",
        translation_key="switch_port_tx_rate",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    FreeboxSensorEntityDescription(
        key="speed",
        translation_key="switch_port_speed",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

FREEPLUG_SENSORS: tuple[FreeboxSensorEntityDescription, ...] = (
    FreeboxSensorEntityDescription(
        key="tx_rate",
        translation_key="freeplug_tx_rate",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    FreeboxSensorEntityDescription(
        key="rx_rate",
        translation_key="freeplug_rx_rate",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FreeboxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    router = entry.runtime_data

    _LOGGER.debug(
        "%s - %s - %s temperature sensors",
        router.name,
        router.mac,
        len(router.sensors_temperature),
    )
    entities: list[SensorEntity] = [
        FreeboxSensor(
            router,
            SensorEntityDescription(
                key=sensor_name,
                name=f"Freebox {sensor_name}",
                native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                device_class=SensorDeviceClass.TEMPERATURE,
                state_class=SensorStateClass.MEASUREMENT,
            ),
        )
        for sensor_name in router.sensors_temperature
    ]

    entities.extend(
        [FreeboxSensor(router, description) for description in CONNECTION_SENSORS]
    )
    entities.extend(
        [FreeboxCallSensor(router, description) for description in CALL_SENSORS]
    )

    _LOGGER.debug("%s - %s - %s disk(s)", router.name, router.mac, len(router.disks))
    entities.extend(
        FreeboxDiskSensor(router, disk, partition, description)
        for disk in router.disks.values()
        for partition in disk["partitions"].values()
        for description in DISK_PARTITION_SENSORS
    )

    entities.extend(
        FreeboxBatterySensor(router, node, endpoint)
        for node in router.home_devices.values()
        for endpoint in node["show_endpoints"]
        if (
            endpoint["name"] == "battery"
            and endpoint["ep_type"] == "signal"
            and endpoint.get("value") is not None
        )
    )

    # Extended connection sensors
    entities.extend(
        FreeboxExtendedSensor(router, description)
        for description in CONNECTION_EXTENDED_SENSORS
    )

    # xDSL sensors (only for xDSL connections)
    entities.extend(
        FreeboxExtendedSensor(router, description)
        for description in XDSL_SENSORS
        if description.is_suitable(router)
    )

    # FTTH sensors (only for FTTH connections)
    entities.extend(
        FreeboxExtendedSensor(router, description)
        for description in FTTH_SENSORS
        if description.is_suitable(router)
    )

    # Switch port sensors
    _LOGGER.debug(
        "%s - %s - %s switch port(s)",
        router.name,
        router.mac,
        len(router.switch_ports),
    )
    entities.extend(
        FreeboxSwitchPortSensor(router, port_id, port_data, description)
        for port_id, port_data in router.switch_ports.items()
        for description in SWITCH_PORT_SENSORS
    )

    # Freeplug sensors
    for network in router.freeplug_networks:
        for member in network.get("members", []):
            # Skip the master adapter as it may not have meaningful tx/rx rates
            if member.get("net_role") == "sta":
                entities.extend(
                    FreeboxFreeplugSensor(router, member, description)
                    for description in FREEPLUG_SENSORS
                )

    if entities:
        async_add_entities(entities, True)


class FreeboxSensor(SensorEntity):
    """Representation of a Freebox sensor."""

    _attr_should_poll = False

    def __init__(
        self, router: FreeboxRouter, description: SensorEntityDescription
    ) -> None:
        """Initialize a Freebox sensor."""
        self.entity_description = description
        self._router = router
        self._attr_unique_id = f"{router.mac} {description.name}"
        self._attr_device_info = router.device_info

    @callback
    def async_update_state(self) -> None:
        """Update the Freebox sensor."""
        state = self._router.sensors[self.entity_description.key]
        if self.native_unit_of_measurement == UnitOfDataRate.KILOBYTES_PER_SECOND:
            self._attr_native_value = round(state / 1000, 2)
        else:
            self._attr_native_value = state

    @callback
    def async_on_demand_update(self) -> None:
        """Update state."""
        self.async_update_state()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register state update callback."""
        self.async_update_state()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self._router.signal_sensor_update,
                self.async_on_demand_update,
            )
        )


class FreeboxCallSensor(FreeboxSensor):
    """Representation of a Freebox call sensor."""

    def __init__(
        self, router: FreeboxRouter, description: SensorEntityDescription
    ) -> None:
        """Initialize a Freebox call sensor."""
        super().__init__(router, description)
        self._call_list_for_type: list[dict[str, Any]] = []

    @callback
    def async_update_state(self) -> None:
        """Update the Freebox call sensor."""
        self._call_list_for_type = []
        if self._router.call_list:
            for call in self._router.call_list:
                if not call["new"]:
                    continue
                if self.entity_description.key == call["type"]:
                    self._call_list_for_type.append(call)

        self._attr_native_value = len(self._call_list_for_type)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return device specific state attributes."""
        return {
            dt_util.utc_from_timestamp(call["datetime"]).isoformat(): call["name"]
            for call in self._call_list_for_type
        }


class FreeboxDiskSensor(FreeboxSensor):
    """Representation of a Freebox disk sensor."""

    def __init__(
        self,
        router: FreeboxRouter,
        disk: dict[str, Any],
        partition: dict[str, Any],
        description: SensorEntityDescription,
    ) -> None:
        """Initialize a Freebox disk sensor."""
        super().__init__(router, description)
        self._disk_id = disk["id"]
        self._partition_id = partition["id"]
        self._attr_name = f"{partition['label']} {description.name}"
        self._attr_unique_id = (
            f"{router.mac} {description.key} {disk['id']} {partition['id']}"
        )

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, disk["id"])},
            model=disk["model"],
            name=f"Disk {disk['id']}",
            sw_version=disk["firmware"],
            via_device=(
                DOMAIN,
                router.mac,
            ),
        )

    @callback
    def async_update_state(self) -> None:
        """Update the Freebox disk sensor."""
        value = None
        disk: dict[str, Any] = self._router.disks[self._disk_id]
        partition: dict[str, Any] = disk["partitions"][self._partition_id]
        if partition.get("total_bytes"):
            value = round(partition["free_bytes"] * 100 / partition["total_bytes"], 2)
        self._attr_native_value = value


class FreeboxBatterySensor(FreeboxHomeEntity, SensorEntity):
    """Representation of a Freebox battery sensor."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE

    @property
    def native_value(self) -> int:
        """Return the current state of the device."""
        return self.get_value("signal", "battery")


class FreeboxExtendedSensor(SensorEntity):
    """Representation of an extended Freebox sensor using value_fn."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    entity_description: FreeboxSensorEntityDescription

    def __init__(
        self,
        router: FreeboxRouter,
        description: FreeboxSensorEntityDescription,
    ) -> None:
        """Initialize the extended Freebox sensor."""
        self.entity_description = description
        self._router = router
        self._attr_unique_id = f"{router.mac}_{description.key}"
        self._attr_device_info = router.device_info

    @callback
    def async_update_state(self) -> None:
        """Update the sensor state."""
        if self.entity_description.value_fn is not None:
            self._attr_native_value = self.entity_description.value_fn(self._router)

    @callback
    def async_on_demand_update(self) -> None:
        """Update state on demand."""
        self.async_update_state()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register state update callback."""
        self.async_update_state()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self._router.signal_sensor_update,
                self.async_on_demand_update,
            )
        )


class FreeboxSwitchPortSensor(SensorEntity):
    """Representation of a Freebox switch port sensor."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    entity_description: FreeboxSensorEntityDescription

    def __init__(
        self,
        router: FreeboxRouter,
        port_id: int,
        port_data: dict[str, Any],
        description: FreeboxSensorEntityDescription,
    ) -> None:
        """Initialize the switch port sensor."""
        self.entity_description = description
        self._router = router
        self._port_id = port_id
        self._attr_unique_id = f"{router.mac}_switch_port_{port_id}_{description.key}"
        self._attr_device_info = router.device_info
        self._attr_translation_placeholders = {"port_id": str(port_id)}

    @callback
    def async_update_state(self) -> None:
        """Update the sensor state."""
        port_data = self._router.switch_ports.get(self._port_id, {})
        self._attr_native_value = port_data.get(self.entity_description.key)

    @callback
    def async_on_demand_update(self) -> None:
        """Update state on demand."""
        self.async_update_state()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register state update callback."""
        self.async_update_state()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self._router.signal_sensor_update,
                self.async_on_demand_update,
            )
        )


class FreeboxFreeplugSensor(SensorEntity):
    """Representation of a Freebox Freeplug (powerline) sensor."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    entity_description: FreeboxSensorEntityDescription

    def __init__(
        self,
        router: FreeboxRouter,
        freeplug: dict[str, Any],
        description: FreeboxSensorEntityDescription,
    ) -> None:
        """Initialize the Freeplug sensor."""
        self.entity_description = description
        self._router = router
        self._freeplug_id = freeplug.get("id", "")
        self._freeplug = freeplug
        self._attr_unique_id = (
            f"{router.mac}_freeplug_{self._freeplug_id}_{description.key}"
        )

        # Create separate device for each Freeplug adapter
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._freeplug_id)},
            name=f"Freeplug {freeplug.get('local_id', self._freeplug_id)}",
            manufacturer="Freebox SAS",
            model=freeplug.get("model", "Freeplug"),
            via_device=(DOMAIN, router.mac),
        )

    @callback
    def async_update_state(self) -> None:
        """Update the sensor state."""
        # Find the updated freeplug data
        for network in self._router.freeplug_networks:
            for member in network.get("members", []):
                if member.get("id") == self._freeplug_id:
                    self._freeplug = member
                    break

        self._attr_native_value = self._freeplug.get(self.entity_description.key)

    @callback
    def async_on_demand_update(self) -> None:
        """Update state on demand."""
        self.async_update_state()
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register state update callback."""
        self.async_update_state()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self._router.signal_sensor_update,
                self.async_on_demand_update,
            )
        )
