"""
Asynchronous implementation of a Dune-HD API client.

:copyright: (c) 2024 by Peter Verhage.
:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import asyncio
import re
from enum import Enum, IntEnum
from types import TracebackType
from typing import Any, Literal, Optional, Self, Type, overload

import aiohttp
from pydantic import BaseModel
from yarl import URL

NEC_CUSTOMER_CODE = "CFCF"

DEFAULT_TIMEOUT = 5


class PlayerState(Enum):
    NAVIGATOR = "navigator"
    FILE_PLAYBACK = "file_playback"
    DVD_PLAYBACK = "dvd_playback"
    BLURAY_PLAYBACK = "bluray_playback"
    BLACK_SCREEN = "black_screen"
    STANDBY = "standby"
    OSD_SCREEN = "osd_screen"


class PlaybackState(Enum):
    INITIALIZING = "initializing"
    PLAYING = "playing"
    PAUSED = "paused"
    SEEKING = "seeking"
    DEINITIALIZING = "deinitializing"
    STOPPED = "stopped"


class PlaybackSpeed(IntEnum):
    MIN_X32 = -8192
    MIN_X16 = -4096
    MIN_X8 = -2048
    MIN_X4 = -1024
    MIN_X2 = -512
    X0 = 0
    X1 = 256
    X2 = 512
    X4 = 1024
    X8 = 2048
    X16 = 4096
    X32 = 8192


class IrCode(Enum):
    EJECT = "10EF"
    MUTE = "46B9"
    MODE = "45BA"
    POWER = "43BC"
    POWER_ON = "5FA0"
    POWER_OFF = "5EA1"
    A = "40BF"  # RED
    B = "1FE0"  # GREEN
    C = "00FF"  # YELLOW
    D = "41BE"  # BLUE
    DIGIT_1 = "0BF4"
    DIGIT_2 = "0CF3"
    DIGIT_3 = "0DF2"
    DIGIT_4 = "0EF1"
    DIGIT_5 = "0FF0"
    DIGIT_6 = "01FE"
    DIGIT_7 = "11EE"
    DIGIT_8 = "12ED"
    DIGIT_9 = "13EC"
    DIGIT_0 = "0AF5"
    CLEAR = "05FA"
    SELECT = "42BD"
    VOLUME_UP = "52AD"
    VOLUME_DOWN = "53AC"
    PROGRAM_UP = "4BB4"
    PROGRAM_DOWN = "4CB3"
    SEARCH = "06F9"
    ZOOM = "02FD"
    SETUP = "4EB1"
    UP = "15EA"
    DOWN = "16E9"
    LEFT = "17E8"
    RIGHT = "18E7"
    ENTER = "14EB"
    RETURN = "04FB"
    INFO = "50AF"
    POPUP_MENU = "07F8"
    TOP_MENU = "51AE"
    PLAY = "48B7"
    PAUSE = "1EE1"
    PLAY_PAUSE = "48B7"
    PREV = "49B6"
    NEXT = "1DE2"
    STOP = "19E6"
    SLOW = "1AE5"
    REW = "1CE3"
    FWD = "1BE4"
    SUBTITLE = "54AB"
    AUDIO = "44BB"


class Command(Enum):
    STATUS = "status"
    UI_STATE = "ui_state"
    SET_PLAYBACK_STATE = "set_playback_state"
    IR_CODE = "ir_code"
    STANDBY = "standby"
    BLACK_SCREEN = "black_screen"
    MAIN_SCREEN = "main_screen"
    GET_FILE = "get_file"
    LAUNCH_MEDIA_URL = "launch_media_url"


class CommandStatus(Enum):
    OK = "ok"
    FAILED = "failed"
    TIMEOUT = "timeout"


class ErrorKind(Enum):
    UNKNOWN_COMMAND = "unknown_command"
    INVALID_PARAMETERS = "invalid_parameters"
    ILLEGAL_STATE = "illegal_state"
    INTERNAL_ERROR = "internal_error"
    OPERATION_FAILED = "operation_failed"


class ResultType(Enum):
    STATUS = "status"
    BYTES = "bytes"


class UIStateScreen(BaseModel):
    bg_url: Optional[str] = None
    poster_url: Optional[str] = None


class UIState(BaseModel):
    screen: Optional[UIStateScreen] = None


class Status(BaseModel):
    command_status: Optional[CommandStatus] = None
    error_kind: Optional[ErrorKind] = None
    error_description: Optional[str] = None
    player_state: PlayerState
    playback_url: Optional[str] = None
    playback_state: Optional[PlaybackState] = None
    previous_playback_state: Optional[PlaybackState] = None
    playback_speed: Optional[PlaybackSpeed] = None
    playback_duration: Optional[int] = None
    playback_position: Optional[int] = None
    playback_is_buffering: Optional[bool] = None
    playback_volume: int
    playback_mute: bool
    playback_caption: Optional[str] = None
    playback_extra_caption: Optional[str] = None
    playback_picture: Optional[str] = None
    protocol_version: int
    product_id: str
    product_name: str
    serial_number: str
    commercial_serial_number: str
    firmware_version: str
    ui_state: Optional[UIState] = (None,)
    raw: dict[str, Any] = None


class Client:
    def __init__(
        self, address=str, *, timeout: int = DEFAULT_TIMEOUT, loop: asyncio.AbstractEventLoop | None = None
    ) -> None:
        self._address = address
        self._client = aiohttp.ClientSession(
            base_url="http://" + address,
            connector=aiohttp.TCPConnector(limit=1),
            timeout=aiohttp.ClientTimeout(total=timeout),
            loop=loop,
            raise_for_status=True,
        )

    async def close(self) -> None:
        return await self._client.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self, exc_type=Optional[Type[BaseException]], exc_val=Optional[BaseException], exc_tb=Optional[TracebackType]
    ) -> Optional[bool]:
        await self.close()
        return None

    async def status(self) -> Status:
        return await self.send_command(Command.STATUS)

    async def ui_state(self) -> Status:
        return await self.send_command(Command.UI_STATE)

    async def toggle_power(self) -> Status:
        return await self.send_ir_code(IrCode.POWER)

    async def power_on(self) -> Status:
        return await self.send_ir_code(IrCode.POWER_ON)

    async def power_off(self) -> Status:
        return await self.send_ir_code(IrCode.POWER_OFF)

    async def top_menu(self) -> Status:
        return await self.send_ir_code(IrCode.TOP_MENU)

    async def popup_menu(self):
        return await self.send_ir_code(IrCode.POPUP_MENU)

    async def info(self):
        return await self.send_ir_code(IrCode.INFO)

    async def cursor_left(self):
        return await self.send_ir_code(IrCode.LEFT)

    async def cursor_right(self):
        return await self.send_ir_code(IrCode.RIGHT)

    async def cursor_up(self):
        return await self.send_ir_code(IrCode.UP)

    async def cursor_down(self):
        return await self.send_ir_code(IrCode.DOWN)

    async def enter(self):
        return await self.send_ir_code(IrCode.ENTER)

    async def back(self):
        return await self.send_ir_code(IrCode.RETURN)

    async def play(self) -> Status:
        return await self.send_ir_code(IrCode.PLAY)

    async def pause(self) -> Status:
        return await self.send_ir_code(IrCode.PAUSE)

    async def toggle_play_pause(self) -> Status:
        return await self.send_ir_code(IrCode.PLAY_PAUSE)

    async def fast_forward(self) -> Status:
        return await self.send_ir_code(IrCode.FWD)

    async def rewind(self) -> Status:
        return await self.send_ir_code(IrCode.REW)

    async def stop(self) -> Status:
        return await self.send_ir_code(IrCode.STOP)

    async def previous(self) -> Status:
        return await self.send_ir_code(IrCode.PREV)

    async def next(self) -> Status:
        return await self.send_ir_code(IrCode.NEXT)

    async def volume_up(self) -> Status:
        return await self.send_ir_code(IrCode.VOLUME_UP)

    async def volume_down(self) -> Status:
        return await self.send_ir_code(IrCode.VOLUME_DOWN)

    async def set_volume(self, level: int) -> Status:
        return await self.send_command(Command.SET_PLAYBACK_STATE, params={"volume": level})

    async def toggle_mute(self) -> Status:
        return await self.send_ir_code(IrCode.MUTE)

    async def mute(self, mute: bool = True) -> Status:
        return await self.send_command(Command.SET_PLAYBACK_STATE, params={"mute": 1 if mute else 0})

    async def seek(self, position: int) -> Status:
        return await self.send_command(Command.SET_PLAYBACK_STATE, params={"position": position})

    async def launch_media_url(self, media_url: str) -> Status:
        return await self.send_command(Command.LAUNCH_MEDIA_URL, params={"media_url": media_url})

    async def get_file(self, path: str) -> bytes:
        return await self.send_command(Command.GET_FILE, params={"path": path}, result_type=ResultType.BYTES)

    def get_file_url(self, path: str) -> str:
        return URL.build(
            scheme="http", host=self._address, path="/cgi-bin/do", query={"cmd": Command.GET_FILE.value, "path": path}
        ).human_repr()

    async def send_ir_code(self, code: IrCode):
        reversed_code = "".join(re.findall(r"[A-F0-9]{2}", code.value)[::-1])
        return await self.send_command(Command.IR_CODE, params={"ir_code": reversed_code + NEC_CUSTOMER_CODE})

    def __parse_status(self, status) -> Status:
        return Status(**status, raw=status)

    @overload
    async def send_command(
        self,
        cmd: Command | str,
        *,
        params: dict[str, Any] | None = None,
        result_type: Literal[ResultType.STATUS] = ResultType.STATUS,
    ) -> Status: ...

    @overload
    async def send_command(
        self, cmd: Command | str, *, params: dict[str, Any] | None = None, result_type: Literal[ResultType.BYTES]
    ) -> bytes: ...

    async def send_command(
        self, cmd: Command | str, *, params: dict[str, Any] | None = None, result_type: ResultType = ResultType.STATUS
    ) -> Status | bytes:
        if params is None:
            params = {}

        params["cmd"] = cmd.value if isinstance(cmd, Command) else cmd
        if result_type == ResultType.STATUS:
            params["result_syntax"] = "json"

        async with self._client.get("/cgi-bin/do", params=params) as response:
            if result_type == ResultType.BYTES:
                return await response.read()

            status = await response.json()
            return self.__parse_status(status)
