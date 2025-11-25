#!/usr/bin/env python3
"""
The main driver logic of the integration driver.

:copyright: (c) 2024 by Peter Verhage.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import asyncio
import logging
import os
from typing import Any

import ucapi
import ucapi.api as uc
from ucapi import media_player

import config
import setup_flow
from device import EVENTS, DuneHDDevice

_LOG = logging.getLogger("driver")  # avoid having __main__ in log messages
_LOOP = asyncio.get_event_loop()


# Global variables
api = uc.IntegrationAPI(_LOOP)
_configured_devices: dict[str, DuneHDDevice] = {}


@api.listens_to(ucapi.Events.CONNECT)
async def on_r2_connect_cmd() -> None:
    """Connect all configured devices when the Remote Two sends the connect command."""
    _LOG.debug("Client connect command: connecting device(s)")
    await api.set_device_state(ucapi.DeviceStates.CONNECTED)
    for device in _configured_devices.values():
        device.connect()


@api.listens_to(ucapi.Events.DISCONNECT)
async def on_r2_disconnect_cmd():
    """Disconnect all configured devices when the Remote Two sends the disconnect command."""
    _LOG.debug("Client disconnect command: disconnecting device(s)")
    for device in _configured_devices.values():
        device.disconnect()


@api.listens_to(ucapi.Events.ENTER_STANDBY)
async def on_r2_enter_standby() -> None:
    """
    Enter standby notification from Remote Two.

    Disconnect every device instance.
    """
    _LOG.debug("Enter standby event: disconnecting device(s)")
    for device in _configured_devices.values():
        device.disconnect()


@api.listens_to(ucapi.Events.EXIT_STANDBY)
async def on_r2_exit_standby() -> None:
    """
    Exit standby notification from Remote Two.

    Connect all device instances.
    """
    _LOG.debug("Exit standby event: connecting device(s)")
    for device in _configured_devices.values():
        device.connect()


@api.listens_to(ucapi.Events.SUBSCRIBE_ENTITIES)
async def on_subscribe_entities(entity_ids: list[str]) -> None:
    """
    Subscribe to given entities.

    :param entity_ids: entity identifiers.
    """
    _LOG.debug("Subscribe entities event: %s", entity_ids)
    for entity_id in entity_ids:
        if entity_id in _configured_devices:
            device = _configured_devices[entity_id]
            api.configured_entities.update_attributes(entity_id, device.media_player_attributes)
            device.connect()
            continue

        device = config.devices.get(entity_id)
        if device:
            _configure_new_device(device, connect=True)
        else:
            _LOG.error("Failed to subscribe entity %s: no device config found", entity_id)


@api.listens_to(ucapi.Events.UNSUBSCRIBE_ENTITIES)
async def on_unsubscribe_entities(entity_ids: list[str]) -> None:
    """On unsubscribe, we disconnect the objects and remove listeners for events."""
    _LOG.debug("Unsubscribe entities event: %s", entity_ids)
    for entity_id in entity_ids:
        if entity_id in _configured_devices:
            device = _configured_devices[entity_id]
            await device.disconnect()
            device.events.remove_all_listeners()


async def on_device_connected(identifier: str, attributes: dict[str, Any]) -> None:
    """Handle device connection."""
    _LOG.debug("Dune-HD device connected: %s", identifier)

    on_device_update(identifier, attributes)
    await api.set_device_state(ucapi.DeviceStates.CONNECTED)


async def on_device_disconnected(identifier: str) -> None:
    """Handle device disconnection."""
    _LOG.debug("Dune-HD device disconnected: %s", identifier)

    api.configured_entities.update_attributes(
        identifier, {media_player.Attributes.STATE: media_player.States.UNAVAILABLE}
    )
    await api.set_device_state(ucapi.DeviceStates.DISCONNECTED)


async def on_device_connection_error(identifier: str, message) -> None:
    """Set entities of device to state UNAVAILABLE if device connection error occurred."""
    _LOG.error(message)

    api.configured_entities.update_attributes(
        identifier, {media_player.Attributes.STATE: media_player.States.UNAVAILABLE}
    )
    await api.set_device_state(ucapi.DeviceStates.ERROR)


async def on_device_update(identifier: str, attributes: dict[str, Any]) -> None:
    """Update attributes for device."""
    if attributes:
        if api.configured_entities.contains(identifier):
            api.configured_entities.update_attributes(identifier, attributes)
        elif api.available_entities.contains(identifier):
            api.available_entities.update_attributes(identifier, attributes)


def _configure_new_device(device: config.DuneHDDeviceConfig, connect: bool = True) -> None:
    # the device should not yet be configured, but better be safe
    if device.identifier in _configured_devices:
        device = _configured_devices[device.identifier]
        device.disconnect()
    else:
        _LOG.debug(
            "Adding new DuneHD device: %s (%s) %s",
            device.name,
            device.identifier,
            device.address if device.address else "",
        )
        device = DuneHDDevice(device, loop=_LOOP)
        device.events.on(EVENTS.CONNECTED, on_device_connected)
        device.events.on(EVENTS.DISCONNECTED, on_device_disconnected)
        device.events.on(EVENTS.ERROR, on_device_connection_error)
        device.events.on(EVENTS.UPDATE, on_device_update)

        _configured_devices[device.identifier] = device

    if connect:
        device.connect()

    _register_available_entities(device)


def _register_available_entities(device: DuneHDDevice) -> None:
    """Create entities for given Android TV device and register them as available entities."""
    if api.available_entities.contains(device.identifier):
        api.available_entities.remove(device.identifier)
    api.available_entities.add(device.media_player)


def on_device_added(device: config.DuneHDDeviceConfig) -> None:
    """Handle a newly added device in the configuration."""
    _LOG.debug("New device added: %s", device)
    _configure_new_device(device, connect=False)


def on_device_removed(device: config.DuneHDDeviceConfig | None) -> None:
    """Handle a removed device in the configuration."""
    if device is None:
        _LOG.debug("Configuration cleared, disconnecting & removing all configured devices")
        for current in _configured_devices.values():
            _remove_device(current)
        api.configured_entities.clear()
        api.available_entities.clear()
    else:
        if device.identifier in _configured_devices:
            device = _configured_devices[device.identifier]
            _remove_device(device)


def _remove_device(device: DuneHDDevice) -> None:
    """Disconnect from device and remove all listeners."""
    _LOG.debug("Disconnecting & removing device %s", device.identifier)
    device.events.remove_all_listeners()
    device.disconnect()
    entity_id = device.identifier
    api.configured_entities.remove(entity_id)
    api.available_entities.remove(entity_id)


async def main():
    """Start the Remote Two integration driver."""
    logging.basicConfig()

    level = os.getenv("UC_LOG_LEVEL", "DEBUG").upper()
    logging.getLogger("config").setLevel(level)
    logging.getLogger("driver").setLevel(level)
    logging.getLogger("device").setLevel(level)
    logging.getLogger("setup_flow").setLevel(level)

    config.devices = config.Devices(api.config_dir_path, on_device_added, on_device_removed)
    for device in config.devices.all():
        _configure_new_device(device)

    await api.init("driver.json", setup_flow.driver_setup_handler)


if __name__ == "__main__":
    _LOOP.run_until_complete(main())
    _LOOP.run_forever()
