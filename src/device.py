"""
Represents a device / media player entity of the integration driver.

:copyright: (c) 2024 by Peter Verhage.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import asyncio
import logging
import time
from asyncio import AbstractEventLoop
from enum import Enum, IntEnum
from typing import Any

from pyee.asyncio import AsyncIOEventEmitter
from ucapi import MediaPlayer, StatusCodes, media_player
from ucapi.media_player import Attributes, Commands, States

import dunehd
from config import DuneHDDeviceConfig


class SimpleCommands(str, Enum):
    """Additional simple commands of the Dune-HD player not covered by media-player features."""

    BLACK_SCREEN = "BLACK_SCREEN"
    MAIN_SCREEN = "MAIN_SCREEN"


_LOG = logging.getLogger(__name__)

BACKOFF_MAX = 30
BACKOFF_SEC = 2

POLL_INTERVAL = 1

EMPTY_IMAGE = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0k"
    "AAAAAXNSR0IArs4c6QAAAAlwSFlzAAAWJQAAFiUBSVIk8AAAABNJREFUCB1jZGBg+A/"
    "EDEwgAgQADigBA//q6GsAAAAASUVORK5CYII%3D"
)

FEATURES = [
    media_player.Features.ON_OFF,
    media_player.Features.VOLUME,
    media_player.Features.VOLUME_UP_DOWN,
    media_player.Features.MUTE_TOGGLE,
    media_player.Features.PLAY_PAUSE,
    media_player.Features.STOP,
    media_player.Features.NEXT,
    media_player.Features.PREVIOUS,
    media_player.Features.MEDIA_DURATION,
    media_player.Features.MEDIA_POSITION,
    media_player.Features.MEDIA_TITLE,
    media_player.Features.MEDIA_IMAGE_URL,
    media_player.Features.MEDIA_TYPE,
    media_player.Features.HOME,
    media_player.Features.CHANNEL_SWITCHER,
    media_player.Features.DPAD,
    media_player.Features.NUMPAD,
    media_player.Features.CONTEXT_MENU,
    media_player.Features.MENU,
    media_player.Features.HOME,
    media_player.Features.REWIND,
    media_player.Features.FAST_FORWARD,
    media_player.Features.SEEK,
    media_player.Features.INFO,
    media_player.Features.AUDIO_TRACK,
    media_player.Features.SUBTITLE,
    media_player.Features.COLOR_BUTTONS,
]


class EVENTS(IntEnum):
    """Internal driver events."""

    CONNECTING = 0
    CONNECTED = 1
    DISCONNECTED = 2
    ERROR = 4
    UPDATE = 5


class _ConnectionState(IntEnum):
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2


class DuneHDDevice:
    """Represents a Dune-HD device."""

    def __init__(self, device: DuneHDDeviceConfig, loop: AbstractEventLoop | None = None) -> None:
        """Create instance."""
        self._loop: AbstractEventLoop = loop or asyncio.get_running_loop()
        self.events = AsyncIOEventEmitter(self._loop)

        self._device = device
        self._media_player_attributes: dict[str, Any] = {
            media_player.Attributes.STATE: States.UNAVAILABLE,
            media_player.Attributes.MEDIA_TYPE: "",
            media_player.Attributes.MEDIA_DURATION: 0,
            media_player.Attributes.MEDIA_POSITION: 0,
            media_player.Attributes.MEDIA_TITLE: "",
            media_player.Attributes.MEDIA_IMAGE_URL: EMPTY_IMAGE,
            media_player.Attributes.VOLUME: 0,
            media_player.Attributes.MUTED: False,
        }
        self._media_player = self._create_media_player()
        self._client = dunehd.Client(device.address)
        self._connection_task: asyncio.Task | None = None
        self._connection_state: _ConnectionState = _ConnectionState.DISCONNECTED

    def _create_media_player(self) -> MediaPlayer:
        return MediaPlayer(
            self.identifier,
            self.name,
            FEATURES,
            self.media_player_attributes,
            device_class=media_player.DeviceClasses.STREAMING_BOX,
            options={media_player.Options.SIMPLE_COMMANDS: [e.value for e in SimpleCommands]},
            cmd_handler=self._media_player_cmd_handler,
        )

    def __del__(self):
        self.disconnect()

    @property
    def identifier(self) -> str:
        """Return the device identifier."""
        return self._device.identifier

    @property
    def name(self) -> str:
        """Return the device name."""
        return self._device.name

    @property
    def address(self) -> str:
        """Return the device address."""
        return self._device.address

    @property
    def log_id(self) -> str:
        """Return a log identifier."""
        return self._device.name if self._device.name else self._device.identifier

    @property
    def media_player(self) -> MediaPlayer:
        """Returns the media player entity."""
        return self._media_player

    @property
    def media_player_attributes(self) -> dict[str, Any] | None:
        """Returns the current media player attributes."""
        return self._media_player_attributes

    # pylint: disable=too-many-return-statements,too-many-branches,too-many-statements,unused-argument
    async def _media_player_cmd_handler(
        self, entity: MediaPlayer, cmd_id: str, params: dict[str, Any] | None
    ) -> StatusCodes:
        _LOG.debug("Process cmd %s", cmd_id)

        try:
            if cmd_id == Commands.PLAY_PAUSE:
                status = await self._client.toggle_play_pause()
            elif cmd_id == Commands.STOP:
                status = await self._client.stop()
            elif cmd_id == Commands.NEXT:
                status = await self._client.next()
            elif cmd_id == Commands.PREVIOUS:
                status = await self._client.previous()
            elif cmd_id == Commands.VOLUME:
                status = await self._client.set_volume(params.get("volume"))
            elif cmd_id == Commands.VOLUME_UP:
                status = await self._client.volume_up()
            elif cmd_id == Commands.VOLUME_DOWN:
                status = await self._client.volume_down()
            elif cmd_id == Commands.MUTE_TOGGLE:
                status = await self._client.toggle_mute()
            elif cmd_id == Commands.ON:
                status = await self._client.power_on()
            elif cmd_id == Commands.OFF:
                status = await self._client.power_off()
            elif cmd_id == Commands.CURSOR_UP:
                status = await self._client.cursor_up()
            elif cmd_id == Commands.CURSOR_DOWN:
                status = await self._client.cursor_down()
            elif cmd_id == Commands.CURSOR_LEFT:
                status = await self._client.cursor_left()
            elif cmd_id == Commands.CURSOR_RIGHT:
                status = await self._client.cursor_right()
            elif cmd_id == Commands.CURSOR_ENTER:
                status = await self._client.enter()
            elif cmd_id == Commands.BACK:
                status = await self._client.back()
            elif cmd_id == Commands.HOME:
                status = await self._client.top_menu()
            elif cmd_id == Commands.CONTEXT_MENU:
                status = await self._client.popup_menu()
            elif cmd_id == Commands.INFO:
                status = await self._client.info()
            elif cmd_id == Commands.SEEK:
                status = await self._client.seek(params.get("media_position"))
            elif cmd_id == Commands.DIGIT_0:
                status = await self._client.send_ir_code(dunehd.IrCode.DIGIT_0)
            elif cmd_id == Commands.DIGIT_1:
                status = await self._client.send_ir_code(dunehd.IrCode.DIGIT_1)
            elif cmd_id == Commands.DIGIT_2:
                status = await self._client.send_ir_code(dunehd.IrCode.DIGIT_2)
            elif cmd_id == Commands.DIGIT_3:
                status = await self._client.send_ir_code(dunehd.IrCode.DIGIT_3)
            elif cmd_id == Commands.DIGIT_4:
                status = await self._client.send_ir_code(dunehd.IrCode.DIGIT_4)
            elif cmd_id == Commands.DIGIT_5:
                status = await self._client.send_ir_code(dunehd.IrCode.DIGIT_5)
            elif cmd_id == Commands.DIGIT_6:
                status = await self._client.send_ir_code(dunehd.IrCode.DIGIT_6)
            elif cmd_id == Commands.DIGIT_7:
                status = await self._client.send_ir_code(dunehd.IrCode.DIGIT_7)
            elif cmd_id == Commands.DIGIT_8:
                status = await self._client.send_ir_code(dunehd.IrCode.DIGIT_8)
            elif cmd_id == Commands.DIGIT_9:
                status = await self._client.send_ir_code(dunehd.IrCode.DIGIT_9)
            elif cmd_id == Commands.CHANNEL_UP:
                status = await self._client.send_ir_code(dunehd.IrCode.PROGRAM_UP)
            elif cmd_id == Commands.CHANNEL_DOWN:
                status = await self._client.send_ir_code(dunehd.IrCode.PROGRAM_DOWN)
            elif cmd_id == Commands.AUDIO_TRACK:
                status = await self._client.send_ir_code(dunehd.IrCode.AUDIO)
            elif cmd_id == Commands.SUBTITLE:
                status = await self._client.send_ir_code(dunehd.IrCode.SUBTITLE)
            elif cmd_id == Commands.FUNCTION_BLUE:
                status = await self._client.send_ir_code(dunehd.IrCode.A)
            elif cmd_id == Commands.FUNCTION_GREEN:
                status = await self._client.send_ir_code(dunehd.IrCode.B)
            elif cmd_id == Commands.FUNCTION_RED:
                status = await self._client.send_ir_code(dunehd.IrCode.C)
            elif cmd_id == Commands.FUNCTION_YELLOW:
                status = await self._client.send_ir_code(dunehd.IrCode.D)
            elif cmd_id == SimpleCommands.BLACK_SCREEN:
                status = await self._client.send_command(dunehd.Command.BLACK_SCREEN)
            elif cmd_id == SimpleCommands.MAIN_SCREEN:
                status = await self._client.send_command(dunehd.Command.MAIN_SCREEN)
            else:
                return StatusCodes.NOT_IMPLEMENTED
        except Exception as e:  # pylint: disable=broad-except
            _LOG.error("Error for cmd %s: %s", cmd_id, e)
            return StatusCodes.SERVER_ERROR

        if status.command_status == dunehd.CommandStatus.FAILED:
            _LOG.error("Command status failed - %s: %s", status.error_kind, status.error_description)
            if status.error_kind == dunehd.ErrorKind.INVALID_PARAMETERS:
                return StatusCodes.BAD_REQUEST
            if status.error_kind == dunehd.ErrorKind.UNKNOWN_COMMAND:
                return StatusCodes.NOT_IMPLEMENTED
            if status.error_kind == dunehd.ErrorKind.ILLEGAL_STATE:
                return StatusCodes.CONFLICT
            return StatusCodes.SERVER_ERROR

        if status.command_status == dunehd.CommandStatus.TIMEOUT:
            return StatusCodes.TIMEOUT

        return StatusCodes.OK

    def _attributes_for_status(self, status: dunehd.Status) -> dict[str, Any]:
        attributes = {}

        if status.player_state == dunehd.PlayerState.STANDBY:
            attributes[Attributes.STATE] = States.OFF
        elif status.playback_is_buffering or status.playback_state == dunehd.PlaybackState.INITIALIZING:
            attributes[Attributes.STATE] = States.BUFFERING
        elif status.playback_state == dunehd.PlaybackState.PLAYING:
            attributes[Attributes.STATE] = States.PLAYING
        elif status.playback_state == dunehd.PlaybackState.PAUSED:
            attributes[Attributes.STATE] = States.PAUSED
        elif status.playback_state == dunehd.PlaybackState.SEEKING:
            attributes[Attributes.STATE] = self._media_player_attributes[Attributes.STATE]
        else:
            attributes[Attributes.STATE] = States.ON

        attributes[media_player.Attributes.MEDIA_TYPE] = (
            media_player.MediaType.VIDEO if status.playback_state is not None else ""
        )
        attributes[media_player.Attributes.MEDIA_DURATION] = status.playback_duration if status.playback_duration else 0
        attributes[media_player.Attributes.MEDIA_POSITION] = status.playback_position if status.playback_position else 0
        attributes[media_player.Attributes.MEDIA_TITLE] = status.playback_caption if status.playback_caption else ""

        if status.playback_state is not None and status.playback_picture is not None:
            attributes[media_player.Attributes.MEDIA_IMAGE_URL] = self._client.get_file_url(status.playback_picture)
        elif status.playback_state is not None and status.ui_state.screen.bg_url is not None:
            attributes[media_player.Attributes.MEDIA_IMAGE_URL] = self._client.get_file_url(
                status.ui_state.screen.bg_url
            )
        else:
            attributes[media_player.Attributes.MEDIA_IMAGE_URL] = EMPTY_IMAGE

        attributes[media_player.Attributes.VOLUME] = status.playback_volume
        attributes[media_player.Attributes.MUTED] = status.playback_mute

        return attributes

    def _filter_changed_attributes(
        self, old_attributes: dict[str, Any] | None, new_attributes: dict[str, Any]
    ) -> dict[str, Any]:
        if old_attributes is None:
            return new_attributes

        if old_attributes.get(media_player.Attributes.STATE) != new_attributes.get(media_player.Attributes.STATE):
            return new_attributes

        changed_attributes = {}
        for key in set([*new_attributes.keys(), *old_attributes.keys()]):
            if new_attributes.get(key) != old_attributes.get(key):
                changed_attributes[key] = new_attributes[key]

        return changed_attributes

    async def _connection(self) -> None:
        _LOG.debug("[%s] Connecting (attempt 1)...", self.identifier)
        self._connection_state = _ConnectionState.CONNECTING
        connection_attempt = 1

        self.events.emit(EVENTS.CONNECTING, self._device.identifier)

        async with dunehd.Client(self._device.address, loop=self._loop) as client:
            while True:
                start = time.time()

                try:
                    status = await client.ui_state()
                    attrs = self._attributes_for_status(status)

                    if self._connection_state == _ConnectionState.CONNECTING:
                        _LOG.debug("[%s] Connected", self.identifier)
                        self._connection_state = _ConnectionState.CONNECTED
                        self.events.emit(EVENTS.CONNECTED, self._device.identifier, attrs)
                    else:
                        changed_attrs = self._filter_changed_attributes(self._media_player_attributes, attrs)
                        if len(changed_attrs) > 0:
                            self.events.emit(EVENTS.UPDATE, self._device.identifier, changed_attrs)

                    self._media_player_attributes = attrs

                    delay = POLL_INTERVAL
                except asyncio.CancelledError:  # pylint: disable=try-except-raise
                    raise
                except Exception:  # pylint: disable=broad-exception-caught
                    if self._connection_state == _ConnectionState.CONNECTING:
                        connection_attempt += 1
                    else:
                        _LOG.debug("[%s] Disconnected...", self.identifier)
                        self.events.emit(EVENTS.DISCONNECTED, self._device.identifier)
                        self._connection_state = _ConnectionState.CONNECTING
                        connection_attempt = 1
                        self.events.emit(EVENTS.CONNECTING, self._device.identifier)

                    _LOG.debug("[%s] Connecting (attempt %d)...", self.identifier, connection_attempt)
                    duration = time.time() - start
                    delay = max(min(connection_attempt * BACKOFF_SEC, BACKOFF_MAX) - duration, 0.1)

                await asyncio.sleep(delay)

    def connect(self) -> None:
        if self._connection_task is None:
            self._connection_task = self._loop.create_task(self._connection())

    def disconnect(self) -> None:
        if self._connection_task:
            self._connection_task.cancel()
            self._connection_task = None
            self._connection_state = _ConnectionState.DISCONNECTED
            self.events.emit(EVENTS.DISCONNECTED, self._device.identifier)
