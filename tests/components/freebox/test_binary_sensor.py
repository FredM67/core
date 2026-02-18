"""Tests for the Freebox binary sensors."""

from copy import deepcopy
from unittest.mock import Mock

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.components.binary_sensor import (
    DOMAIN as BINARY_SENSOR_DOMAIN,
    BinarySensorDeviceClass,
)
from homeassistant.components.freebox import SCAN_INTERVAL
from homeassistant.const import ATTR_DEVICE_CLASS, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant

from .common import setup_platform
from .const import DATA_HOME_PIR_GET_VALUE, DATA_STORAGE_GET_RAIDS, DATA_SWITCH_GET_STATUS

from tests.common import async_fire_time_changed


async def test_raid_array_degraded(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, router: Mock
) -> None:
    """Test raid array degraded binary sensor."""
    await setup_platform(hass, BINARY_SENSOR_DOMAIN)

    assert (
        hass.states.get("binary_sensor.freebox_server_r2_raid_array_0_degraded").state
        == "off"
    )

    # Now simulate we degraded
    data_storage_get_raids_degraded = deepcopy(DATA_STORAGE_GET_RAIDS)
    data_storage_get_raids_degraded[0]["degraded"] = True
    router().storage.get_raids.return_value = data_storage_get_raids_degraded
    # Simulate an update
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    # To execute the save
    await hass.async_block_till_done()
    assert (
        hass.states.get("binary_sensor.freebox_server_r2_raid_array_0_degraded").state
        == "on"
    )


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_home(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, router: Mock
) -> None:
    """Test home binary sensors."""
    await setup_platform(hass, BINARY_SENSOR_DOMAIN)

    # Device class
    assert (
        hass.states.get("binary_sensor.detecteur").attributes[ATTR_DEVICE_CLASS]
        == BinarySensorDeviceClass.MOTION
    )
    assert (
        hass.states.get("binary_sensor.ouverture_porte").attributes[ATTR_DEVICE_CLASS]
        == BinarySensorDeviceClass.DOOR
    )
    assert (
        hass.states.get("binary_sensor.ouverture_porte_couvercle").attributes[
            ATTR_DEVICE_CLASS
        ]
        == BinarySensorDeviceClass.SAFETY
    )

    # Initial state
    assert hass.states.get("binary_sensor.detecteur").state == "on"
    assert hass.states.get("binary_sensor.detecteur_couvercle").state == "off"
    assert hass.states.get("binary_sensor.ouverture_porte").state == "unknown"
    assert hass.states.get("binary_sensor.ouverture_porte_couvercle").state == "off"

    # Now simulate a changed status
    data_home_get_values_changed = deepcopy(DATA_HOME_PIR_GET_VALUE)
    data_home_get_values_changed["value"] = True
    router().home.get_home_endpoint_value.return_value = data_home_get_values_changed

    # Simulate an update
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.detecteur").state == "off"
    assert hass.states.get("binary_sensor.detecteur_couvercle").state == "on"
    assert hass.states.get("binary_sensor.ouverture_porte").state == "off"
    assert hass.states.get("binary_sensor.ouverture_porte_couvercle").state == "on"


async def test_switch_port_link(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, router: Mock
) -> None:
    """Test switch port link binary sensors."""
    await setup_platform(hass, BINARY_SENSOR_DOMAIN)

    # Port 1 and 2 are up, Port 3 and 4 are down
    assert (
        hass.states.get("binary_sensor.freebox_server_r2_port_1_link").state == STATE_ON
    )
    assert (
        hass.states.get("binary_sensor.freebox_server_r2_port_2_link").state == STATE_ON
    )
    assert (
        hass.states.get("binary_sensor.freebox_server_r2_port_3_link").state
        == STATE_OFF
    )
    assert (
        hass.states.get("binary_sensor.freebox_server_r2_port_4_link").state
        == STATE_OFF
    )

    # Device class should be connectivity
    assert (
        hass.states.get("binary_sensor.freebox_server_r2_port_1_link").attributes[
            ATTR_DEVICE_CLASS
        ]
        == BinarySensorDeviceClass.CONNECTIVITY
    )

    # Now simulate port 1 goes down and port 3 goes up
    data_switch_status_changed = deepcopy(DATA_SWITCH_GET_STATUS)
    data_switch_status_changed[0]["link"] = "down"
    data_switch_status_changed[2]["link"] = "up"
    data_switch_status_changed[2]["speed"] = "1000baseT-FD"
    router().switch.get_status.return_value = data_switch_status_changed

    # Simulate an update
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert (
        hass.states.get("binary_sensor.freebox_server_r2_port_1_link").state
        == STATE_OFF
    )
    assert (
        hass.states.get("binary_sensor.freebox_server_r2_port_3_link").state == STATE_ON
    )
