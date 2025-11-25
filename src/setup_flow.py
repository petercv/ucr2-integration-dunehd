"""
Setup flow for Dune-HD integration.

:copyright: (c) 2024 by Peter Verhage.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import asyncio
import logging
from enum import IntEnum

from ucapi import (
    AbortDriverSetup,
    DriverSetupRequest,
    IntegrationSetupError,
    RequestUserInput,
    SetupAction,
    SetupComplete,
    SetupDriver,
    SetupError,
    UserDataResponse,
)

import config
import dunehd
from config import DuneHDDeviceConfig

_LOG = logging.getLogger(__name__)


class SetupSteps(IntEnum):
    """Enumeration of setup steps to keep track of user data responses."""

    INIT = 0
    CONFIGURATION_MODE = 1
    DEVICE_CHOICE = 2


_setup_step = SetupSteps.INIT


async def driver_setup_handler(msg: SetupDriver) -> SetupAction:
    """
    Dispatch driver setup requests to corresponding handlers.

    Either start the setup process or handle the selected Dune-HD device.

    :param msg: the setup driver request object, either DriverSetupRequest or UserDataResponse
    :return: the setup action on how to continue
    """
    global _setup_step

    if isinstance(msg, DriverSetupRequest):
        _setup_step = SetupSteps.INIT
        return await handle_driver_setup(msg)
    if isinstance(msg, UserDataResponse):
        _LOG.debug(msg)
        if _setup_step == SetupSteps.CONFIGURATION_MODE and "address" in msg.input_values:
            return await handle_configuration_mode(msg)
        if _setup_step == SetupSteps.DEVICE_CHOICE and "choice" in msg.input_values:
            return await handle_device_choice(msg)
        _LOG.error("No or invalid user response was received: %s", msg)
    elif isinstance(msg, AbortDriverSetup):
        _LOG.info("Setup was aborted with code: %s", msg.error)
        _setup_step = SetupSteps.INIT

    # user confirmation not used in setup process
    # if isinstance(msg, UserConfirmationResponse):
    #     return handle_user_confirmation(msg)

    return SetupError()


async def handle_driver_setup(_msg: DriverSetupRequest) -> RequestUserInput | SetupError:
    """
    Start driver setup.

    Initiated by Remote Two to set up the driver.
    Ask user to enter ip-address for manual configuration, otherwise auto-discovery is used.

    :param _msg: not used, we don't have any input fields in the first setup screen.
    :return: the setup action on how to continue
    """
    global _setup_step

    _LOG.debug("Starting driver setup")
    _setup_step = SetupSteps.CONFIGURATION_MODE
    # pylint: disable=line-too-long
    return RequestUserInput(
        {"en": "Setup mode"},
        [
            {
                "id": "info",
                "label": {"en": ""},
                "field": {
                    "label": {
                        "value": {
                            "en": (
                                "Enter IP address and click _Next_."
                                "The device must be on the same network as the remote."
                            )
                        }
                    }
                },
            },
            {
                "field": {"text": {"value": ""}},
                "id": "address",
                "label": {"en": "IP address"},
            },
        ],
    )


async def handle_configuration_mode(msg: UserDataResponse) -> RequestUserInput | SetupError:
    """
    Process user data response in a setup process.

    Try connecting to device and retrieve model information.

    :param msg: response data from the requested user data
    :return: the setup action on how to continue
    """
    global _setup_step

    config.devices.clear()  # triggers device instance removal

    dropdown_items = []
    address = msg.input_values["address"]

    if not bool(address):
        _LOG.warning("No device entered")
        return SetupError(error_type=IntegrationSetupError.NOT_FOUND)

    _LOG.debug("Starting manual driver setup for %s", address)
    try:
        async with dunehd.Client(address) as client:
            status = await client.status()
    except Exception as e:  # pylint: disable=broad-exception-caught
        _LOG.error("Cannot connect to manually entered address %s: %s", address, e)
        return SetupError(error_type=IntegrationSetupError.CONNECTION_REFUSED)

    dropdown_items.append({"id": address, "label": {"en": f"{status.product_name} [{address}]"}})

    _setup_step = SetupSteps.DEVICE_CHOICE
    return RequestUserInput(
        {"en": "Confirm your Dune-HD device"},
        [
            {
                "field": {"dropdown": {"value": dropdown_items[0]["id"], "items": dropdown_items}},
                "id": "choice",
                "label": {"en": "Device"},
            }
        ],
    )


async def handle_device_choice(msg: UserDataResponse) -> SetupComplete | SetupError:
    """
    Process user data response in a setup process.

    Driver setup callback to provide requested user data during the setup process.

    :param msg: response data from the requested user data
    :return: the setup action on how to continue: SetupComplete if a valid AVR device was chosen.
    """
    address = msg.input_values["choice"]
    _LOG.debug("Chosen Dune-HD device: %s. Trying to connect and retrieve device information...", address)

    try:
        async with dunehd.Client(address) as client:
            status = await client.status()
    except:  # pylint: disable=bare-except
        _LOG.error("Cannot connect to address %s", address)
        return SetupError(error_type=IntegrationSetupError.CONNECTION_REFUSED)

    device = DuneHDDeviceConfig(status.serial_number, status.product_name, address)
    config.devices.add(device)
    config.devices.store()

    await asyncio.sleep(1)

    _LOG.info("Setup successfully completed for %s", device.name)
    return SetupComplete()
