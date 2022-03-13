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

    def __repr__(self) -> str:
        return (
            "<PositionTime: "
            f"position={self.position}, "
            f"time={self.time}, "
            f"connected={self.connected}"
        )


class MemoryInfo(NamedTuple):
    reservable: int
    used: int
    free: int
    allocated: int

    def __repr__(self) -> str:
        return (
            "<MemoryInfo: "
            f"reservable={self.reservable}, "
            f"used={self.used}, "
            f"free={self.free}, "
            f"allocated={self.allocated}"
        )


class CPUInfo(NamedTuple):
    cores: int
    systemLoad: float
    lavalinkLoad: float

    def __repr__(self) -> str:
        return (
            "<CPUInfo: "
            f"cores={self.cores}, "
            f"systemLoad={self.systemLoad}, "
            f"lavalinkLoad={self.lavalinkLoad}"
        )


class EqualizerBands(NamedTuple):
    band: int
    gain: float

    def __repr__(self) -> str:
        return (
            "<EqualizerBands: "
            f"band={self.band}, "
            f"gain={self.gain}"
        )


class PlaylistInfo(NamedTuple):
    name: str
    selectedTrack: int

    def __repr__(self) -> str:
        return (
            "<PlaylistInfo: "
            f"name={self.name}, "
            f"selectedTrack={self.selectedTrack}"
        )
