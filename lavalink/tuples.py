from __future__ import annotations

from collections import namedtuple

PositionTime = namedtuple("PositionTime", "position time connected")
MemoryInfo = namedtuple("MemoryInfo", "reservable used free allocated")
CPUInfo = namedtuple("CPUInfo", "cores systemLoad lavalinkLoad")
EqualizerBands = namedtuple("EqualizerBands", "band gain")
_PlaylistInfo = namedtuple("PlaylistInfo", "name selectedTrack")
