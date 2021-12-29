from __future__ import annotations
from collections import namedtuple

__all__ = [
    "PositionTime",
    "MemoryInfo",
    "CPUInfo",
    "EqualizerBands",
    "PlaylistInfo"
]

PositionTime = namedtuple("PositionTime", "position time connected")
MemoryInfo = namedtuple("MemoryInfo", "reservable used free allocated")
CPUInfo = namedtuple("CPUInfo", "cores systemLoad lavalinkLoad")
EqualizerBands = namedtuple("EqualizerBands", "band gain")
PlaylistInfo = namedtuple("PlaylistInfo", "name selectedTrack")
