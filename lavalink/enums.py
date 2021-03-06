import enum

__all__ = [
    "DiscordVoiceSocketResponses",
    "LavalinkEvents",
    "TrackEndReason",
    "LavalinkIncomingOp",
    "LavalinkOutgoingOp",
    "FiltersOp",
    "NodeState",
    "PlayerState",
    "LoadType",
    "ExceptionSeverity",
]


class DiscordVoiceSocketResponses(enum.Enum):
    VOICE_STATE_UPDATE = "VOICE_STATE_UPDATE"
    VOICE_SERVER_UPDATE = "VOICE_SERVER_UPDATE"


class LavalinkEvents(enum.Enum):
    """
    An enumeration of the Lavalink Track Events.
    """

    TRACK_END = "TrackEndEvent"
    """The track playback has ended."""

    TRACK_EXCEPTION = "TrackExceptionEvent"
    """There was an exception during track playback."""

    TRACK_STUCK = "TrackStuckEvent"
    """Track playback got stuck during playback."""

    TRACK_START = "TrackStartEvent"
    """The track playback started."""

    WEBSOCKET_CLOSED = "WebSocketClosedEvent"
    """Websocket has been closed."""

    FORCED_DISCONNECT = "ForcefulDisconnectEvent"
    """Connection has been disconnect, do not attempt to reconnect."""

    # Custom events
    QUEUE_END = "QueueEndEvent"
    """This is a custom event generated by this library to denote the
    end of all tracks in the queue.
    """


class TrackEndReason(enum.Enum):
    """
    The reasons why track playback has ended.
    """

    FINISHED = "FINISHED"
    """The track reached the end, or the track itself ended with an
    exception.
    """

    LOAD_FAILED = "LOAD_FAILED"
    """The track failed to start, throwing an exception before
    providing any audio.
    """

    STOPPED = "STOPPED"
    """The track was stopped due to the player being stopped.
    """

    REPLACED = "REPLACED"
    """The track stopped playing because a new track started playing.
    """

    CLEANUP = "CLEANUP"
    """The track was stopped because the cleanup threshold for the
    audio player was reached.
    """


class LavalinkIncomingOp(enum.Enum):
    EVENT = "event"
    PLAYER_UPDATE = "playerUpdate"
    STATS = "stats"


class LavalinkOutgoingOp(enum.Enum):
    VOICE_UPDATE = "voiceUpdate"
    DESTROY = "destroy"
    PLAY = "play"
    STOP = "stop"
    PAUSE = "pause"
    SEEK = "seek"
    VOLUME = "volume"
    FILTERS = "filters"


class FiltersOp(enum.Enum):
    """
    An enumeration of all filters available to use
    """
    VOLUME = "volume"
    """Manage song volume"""

    EQUALIZER = "equalizer"
    """Edit equalizer"""

    KARAOKE = "karaoke"
    """Remove vocals"""

    TIMESCALE = "timescale"
    """Changes the speed, pitch, and rate"""

    TREMOLO = "tremolo"
    """Create a shuddering effect"""

    VIBRATO = "vibrato"
    """Produce a pulsating change of the pitch"""

    ROTATION = "rotation"
    """Audio Panning"""

    DISTORTION = "distortion"
    """Distortion effect"""

    CHANNEL_MIX = "channelMix"
    """Mixes both channels (left and right)"""

    LOW_PASS = "lowPass"
    """Higher frequencies get suppressed, while lower frequencies pass through this filter"""


class NodeState(enum.Enum):
    CONNECTING = 0
    """The client is connecting to the node"""

    READY = 1
    """The node is ready to send and receive requests"""

    RECONNECTING = 2
    """The connection with the node was lost. Now it's reconnecting with it"""

    DISCONNECTING = 3
    """Closing connection with the node"""


class PlayerState(enum.Enum):
    CREATED = -1
    """Player was created"""

    CONNECTING = 0
    """The client is connecting to the player"""

    READY = 1
    """The player is ready to reproduce"""

    NODE_BUSY = 2
    """The node cannot respond to the player requests"""

    RECONNECTING = 3
    """The connection with the player was lost. Now it's reconnecting with it"""

    DISCONNECTING = 4
    """Closing connection with the player"""


class LoadType(enum.Enum):
    """
    The result type of loadtracks request

    Attributes
    ----------
    TRACK_LOADED
    PLAYLIST_LOADED
    SEARCH_RESULT
    NO_MATCHES
    LOAD_FAILED
    """

    TRACK_LOADED = "TRACK_LOADED"
    PLAYLIST_LOADED = "PLAYLIST_LOADED"
    SEARCH_RESULT = "SEARCH_RESULT"
    NO_MATCHES = "NO_MATCHES"
    LOAD_FAILED = "LOAD_FAILED"
    V2_COMPAT = "V2_COMPAT"
    V2_COMPACT = "V2_COMPACT"


class ExceptionSeverity(enum.Enum):
    COMMON = "COMMON"
    SUSPICIOUS = "SUSPICIOUS"
    FATAL = "FATAL"
