"""Tests for the Freebox sensors."""

from copy import deepcopy
from unittest.mock import Mock

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.components.freebox import SCAN_INTERVAL
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.core import HomeAssistant

from .common import setup_platform
from .const import (
    DATA_CONNECTION_GET_STATUS,
    DATA_CONNECTION_GET_XDSL,
    DATA_FREEPLUG_GET_NETWORKS,
    DATA_HOME_GET_NODES,
    DATA_STORAGE_GET_DISKS,
    DATA_SWITCH_GET_PORT_STATS_1,
)

from tests.common import async_fire_time_changed


async def test_network_speed(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, router: Mock
) -> None:
    """Test missed call sensor."""
    await setup_platform(hass, SENSOR_DOMAIN)

    assert hass.states.get("sensor.freebox_download_speed").state == "198.9"
    assert hass.states.get("sensor.freebox_upload_speed").state == "1440.0"

    # Simulate a changed speed
    data_connection_get_status_changed = deepcopy(DATA_CONNECTION_GET_STATUS)
    data_connection_get_status_changed["rate_down"] = 123400
    data_connection_get_status_changed["rate_up"] = 432100
    router().connection.get_status.return_value = data_connection_get_status_changed
    # Simulate an update
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    # To execute the save
    await hass.async_block_till_done()
    assert hass.states.get("sensor.freebox_download_speed").state == "123.4"
    assert hass.states.get("sensor.freebox_upload_speed").state == "432.1"


async def test_call(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, router: Mock
) -> None:
    """Test missed call sensor."""
    await setup_platform(hass, SENSOR_DOMAIN)

    assert hass.states.get("sensor.freebox_missed_calls").state == "3"

    # Simulate we marked calls as read
    data_call_get_calls_marked_as_read = []
    router().call.get_calls_log.return_value = data_call_get_calls_marked_as_read
    # Simulate an update
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    # To execute the save
    await hass.async_block_till_done()
    assert hass.states.get("sensor.freebox_missed_calls").state == "0"


async def test_disk(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, router: Mock
) -> None:
    """Test disk sensor."""
    await setup_platform(hass, SENSOR_DOMAIN)

    # Initial state
    assert (
        router().storage.get_disks.return_value[2]["partitions"][0]["total_bytes"]
        == 1960000000000
    )

    assert (
        router().storage.get_disks.return_value[2]["partitions"][0]["free_bytes"]
        == 1730000000000
    )

    assert hass.states.get("sensor.freebox_free_space").state == "88.27"

    # Simulate a changed storage size
    data_storage_get_disks_changed = deepcopy(DATA_STORAGE_GET_DISKS)
    data_storage_get_disks_changed[2]["partitions"][0]["free_bytes"] = 880000000000
    router().storage.get_disks.return_value = data_storage_get_disks_changed
    # Simulate an update
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    # To execute the save
    await hass.async_block_till_done()
    assert hass.states.get("sensor.freebox_free_space").state == "44.9"


async def test_battery(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, router: Mock
) -> None:
    """Test battery sensor."""
    await setup_platform(hass, SENSOR_DOMAIN)

    assert hass.states.get("sensor.telecommande_niveau_de_batterie").state == "100"
    assert hass.states.get("sensor.ouverture_porte_niveau_de_batterie").state == "100"
    assert hass.states.get("sensor.detecteur_niveau_de_batterie").state == "100"

    # Simulate a changed battery
    data_home_get_nodes_changed = deepcopy(DATA_HOME_GET_NODES)
    data_home_get_nodes_changed[2]["show_endpoints"][3]["value"] = 25
    data_home_get_nodes_changed[3]["show_endpoints"][4]["value"] = 50
    data_home_get_nodes_changed[4]["show_endpoints"][5]["value"] = 75
    router().home.get_home_nodes.return_value = data_home_get_nodes_changed
    # Simulate an update
    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    # To execute the save
    await hass.async_block_till_done()
    assert hass.states.get("sensor.telecommande_niveau_de_batterie").state == "25"
    assert hass.states.get("sensor.ouverture_porte_niveau_de_batterie").state == "50"
    assert hass.states.get("sensor.detecteur_niveau_de_batterie").state == "75"


async def test_connection_extended_sensors(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, router: Mock
) -> None:
    """Test extended connection sensors."""
    await setup_platform(hass, SENSOR_DOMAIN)

    # Verify bytes_down and bytes_up sensors
    assert (
        hass.states.get("sensor.freebox_server_r2_total_downloaded").state
        == "2355966141297"
    )
    assert (
        hass.states.get("sensor.freebox_server_r2_total_uploaded").state
        == "12035728872949"
    )

    # Verify bandwidth sensors
    assert (
        hass.states.get("sensor.freebox_server_r2_download_bandwidth").state
        == "1000000000"
    )
    assert (
        hass.states.get("sensor.freebox_server_r2_upload_bandwidth").state
        == "700000000"
    )

    # Simulate updated data
    data_connection_changed = deepcopy(DATA_CONNECTION_GET_STATUS)
    data_connection_changed["bytes_down"] = 3000000000000
    data_connection_changed["bytes_up"] = 15000000000000
    router().connection.get_status.return_value = data_connection_changed

    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert (
        hass.states.get("sensor.freebox_server_r2_total_downloaded").state
        == "3000000000000"
    )
    assert (
        hass.states.get("sensor.freebox_server_r2_total_uploaded").state
        == "15000000000000"
    )


async def test_ftth_sensors(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, router: Mock
) -> None:
    """Test FTTH (fiber) sensors."""
    await setup_platform(hass, SENSOR_DOMAIN)

    # FTTH sensors should be present (connection status has media: ftth)
    # Values are divided by 100 to convert to dBm
    assert hass.states.get("sensor.freebox_server_r2_optical_rx_power").state == "-18.5"
    assert hass.states.get("sensor.freebox_server_r2_optical_tx_power").state == "2.5"


async def test_xdsl_sensors(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, router_xdsl: Mock
) -> None:
    """Test xDSL sensors with xDSL connection type."""
    await setup_platform(hass, SENSOR_DOMAIN)

    # xDSL sensors should be present
    assert (
        hass.states.get("sensor.freebox_server_r2_xdsl_max_download_rate").state
        == "20640000"
    )
    assert (
        hass.states.get("sensor.freebox_server_r2_xdsl_max_upload_rate").state
        == "1024000"
    )
    assert (
        hass.states.get("sensor.freebox_server_r2_xdsl_download_rate").state
        == "19232000"
    )
    assert (
        hass.states.get("sensor.freebox_server_r2_xdsl_upload_rate").state == "1024000"
    )
    assert hass.states.get("sensor.freebox_server_r2_xdsl_crc_errors").state == "42"


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_xdsl_snr_sensors(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, router_xdsl: Mock
) -> None:
    """Test xDSL SNR and attenuation sensors (disabled by default)."""
    await setup_platform(hass, SENSOR_DOMAIN)

    # SNR values are divided by 10 to convert to dB
    assert (
        hass.states.get("sensor.freebox_server_r2_xdsl_download_snr_margin").state
        == "12.0"
    )
    assert (
        hass.states.get("sensor.freebox_server_r2_xdsl_upload_snr_margin").state
        == "15.0"
    )
    # Attenuation values are divided by 10 to convert to dB
    assert (
        hass.states.get("sensor.freebox_server_r2_xdsl_download_attenuation").state
        == "22.0"
    )
    assert (
        hass.states.get("sensor.freebox_server_r2_xdsl_upload_attenuation").state
        == "11.0"
    )


async def test_xdsl_sensors_not_created_for_ftth(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, router: Mock
) -> None:
    """Test that xDSL sensors are not created for FTTH connections."""
    await setup_platform(hass, SENSOR_DOMAIN)

    # xDSL sensors should NOT be present for FTTH connections
    assert hass.states.get("sensor.freebox_server_r2_xdsl_max_download_rate") is None
    assert hass.states.get("sensor.freebox_server_r2_xdsl_download_rate") is None


async def test_switch_port_sensors(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, router: Mock
) -> None:
    """Test switch port sensors."""
    await setup_platform(hass, SENSOR_DOMAIN)

    # Port 1 sensors (connected at 1000baseT-FD)
    assert hass.states.get("sensor.freebox_server_r2_port_1_rx_rate").state == "125000"
    assert hass.states.get("sensor.freebox_server_r2_port_1_tx_rate").state == "250000"
    assert (
        hass.states.get("sensor.freebox_server_r2_port_1_speed").state == "1000baseT-FD"
    )

    # Port 2 sensors (connected at 100baseT-FD)
    assert hass.states.get("sensor.freebox_server_r2_port_2_rx_rate").state == "50000"
    assert hass.states.get("sensor.freebox_server_r2_port_2_tx_rate").state == "75000"
    assert (
        hass.states.get("sensor.freebox_server_r2_port_2_speed").state == "100baseT-FD"
    )

    # Simulate changed port stats
    data_port_stats_changed = deepcopy(DATA_SWITCH_GET_PORT_STATS_1)
    data_port_stats_changed["rx_bytes_rate"] = 500000
    data_port_stats_changed["tx_bytes_rate"] = 600000
    router().switch.get_port_stats.side_effect = lambda port_id: (
        data_port_stats_changed if port_id == 1 else DATA_SWITCH_GET_PORT_STATS_1
    )

    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.freebox_server_r2_port_1_rx_rate").state == "500000"
    assert hass.states.get("sensor.freebox_server_r2_port_1_tx_rate").state == "600000"


async def test_freeplug_sensors(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, router: Mock
) -> None:
    """Test Freeplug (powerline) sensors."""
    await setup_platform(hass, SENSOR_DOMAIN)

    # Only station (sta) freeplugs should have sensors, not the master (cco)
    # First freeplug (FP-Salon)
    assert hass.states.get("sensor.freeplug_fp_salon_powerline_tx_rate").state == "320"
    assert hass.states.get("sensor.freeplug_fp_salon_powerline_rx_rate").state == "280"

    # Second freeplug (FP-Bureau)
    assert hass.states.get("sensor.freeplug_fp_bureau_powerline_tx_rate").state == "180"
    assert hass.states.get("sensor.freeplug_fp_bureau_powerline_rx_rate").state == "150"

    # Simulate changed freeplug data
    data_freeplug_changed = deepcopy(DATA_FREEPLUG_GET_NETWORKS)
    data_freeplug_changed[0]["members"][1]["tx_rate"] = 400
    data_freeplug_changed[0]["members"][1]["rx_rate"] = 350
    router().freeplug.get_freeplug_networks.return_value = data_freeplug_changed

    freezer.tick(SCAN_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.freeplug_fp_salon_powerline_tx_rate").state == "400"
    assert hass.states.get("sensor.freeplug_fp_salon_powerline_rx_rate").state == "350"
