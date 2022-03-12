from typing import NamedTuple

__all__ = [
    "PositionTime",
    "MemoryInfo",
    "CPUInfo",
    "EqualizerBands",
    "PlaylistInfo"
]


class PositionTime(NamedTuple):
    position: int
    time: int
    connected: bool


class MemoryInfo(NamedTuple):
    reservable: int
    used: int
    free: int
    allocated: int


class CPUInfo(NamedTuple):
    cores: int
    systemLoad: float
    lavalinkLoad: float


class EqualizerBands(NamedTuple):
    band: int
    gain: float


class PlaylistInfo(NamedTuple):
    name: str
    selectedTrack: int
