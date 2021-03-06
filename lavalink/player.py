from __future__ import annotations

import asyncio
import datetime
import random
from collections import deque
from random import shuffle
from typing import TYPE_CHECKING, Optional, Any, Union

import discord
from discord.backoff import ExponentialBackoff
from discord.ext.commands import Bot
from discord.voice_client import VoiceProtocol

from . import log, ws_rll_log
from .enums import (
    LavalinkEvents,
    LavalinkIncomingOp,
    LavalinkOutgoingOp,
    PlayerState,
    TrackEndReason,
)
from .rest_api import RESTClient, Track
from .tuples import EqualizerBands, PositionTime

if TYPE_CHECKING:
    from .node import Node

__all__ = ["Player"]


class Player(RESTClient, VoiceProtocol):
    """
    The Player class represents the current state of playback.
    It also is used to control playback and queue tracks.

    The existence of this object guarantees that the bot is connected
    to a voice channel.

    Attributes
    ----------
    channel: discord.VoiceChannel
        The channel the bot is connected to.
    queue : deque[Track]
        list of Track
    position : int
        The seeked position in the track of the current playback.
    current : Track
        The current playing track
    repeat : bool
        Repeat the current track
    loop_queue: bool
        Repeat the current queue
    shuffle : bool
        The newly added tracks to the queue gets shuffled
    """
    channel: discord.VoiceChannel
    queue: deque[Track]
    position: int
    current: Track
    repeat: bool
    loop_queue: bool
    shuffle: bool

    def __call__(self, client: Bot, channel: discord.VoiceChannel):
        self.client: Bot = client
        self.channel: discord.VoiceChannel = channel

        return self

    def __init__(
            self, client: Bot = None, channel: discord.VoiceChannel = None, node: "Node" = None, ssl: bool = False
    ):
        """
        Initialize the player

        Parameters
        ----------
        client: discord.ext.commands.Bot
            The bot instance
        channel : discord.VoiceChannel
            The channel to connect to
        node : Node
            The node to use
        ssl : bool
            Whether to use the `https://` protocol.
        """
        self.client: Bot = client
        self.channel: discord.VoiceChannel = channel
        self.guild: discord.Guild = channel.guild
        self._last_channel_id: int = channel.id
        self.queue: deque[Track] = deque()
        self.position = 0
        self.current: Optional[Track] = None
        self._paused = False
        self.repeat = False
        self.loop_queue = False
        self.shuffle = False
        self.shuffle_bumped = True
        self._is_autoplaying = False
        self._auto_play_sent = False
        self._volume = 100
        self.state = PlayerState.CREATED
        self._voice_state = {}
        self.connected_at = None
        self._connected = False

        self._is_playing = False
        self._metadata = {}

        if node is None:
            from .node import get_node

            self.node = get_node()
        else:
            self.node = node

        self._con_delay = None
        self._last_resume = None
        self.voice_state = {}

        super().__init__(self, ssl)

    def __repr__(self):
        return (
            "<Player: "
            f"state={self.state.name}, connected={self.connected}, "
            f"guild={self.guild.name!r} ({self.guild.id}), "
            f"channel={self.channel.name!r} ({self.channel.id}), "
            f"playing={self.is_playing}, paused={self.paused}, volume={self.volume}, "
            f"queue_size={len(self.queue)}, current={self.current!r}, "
            f"position={self.position}, "
            f"length={self.current.length if self.current else 0}, node={self.node!r}>"
        )

    @property
    def is_auto_playing(self) -> bool:
        """
        Current status of playback
        """
        return self._is_playing and not self._paused and self._is_autoplaying

    @property
    def is_playing(self) -> bool:
        """
        Current status of playback
        """
        return self._is_playing and not self._paused and self._connected

    @property
    def paused(self) -> bool:
        """
        Player's paused state.
        """
        return self._paused

    @property
    def volume(self) -> int:
        """
        The current volume.
        """
        return self._volume

    @property
    def ready(self) -> bool:
        """
        Whether the underlying node is ready for requests.
        """
        return self.node.ready

    @property
    def connected(self) -> bool:
        """
        Whether the player is ready to be used.
        """
        return self._connected

    async def on_voice_server_update(self, data: dict[str, Any]):
        """
        Send voice server update data to the node

        Parameters
        ----------
        data : dict[str, Any]
            The data to send
        """
        self._voice_state.update({"event": data})
        await self._send_lavalink_voice_update(self._voice_state)

    async def on_voice_state_update(self, data: dict):
        """
        Send voice state update data to the node

        Parameters
        ----------
        data : dict[str, Any]
            The data to send
        """
        self._voice_state.update({"sessionId": data["session_id"]})
        if (channel_id := data["channel_id"]) is None:
            ws_rll_log.info("Received voice disconnect from discord, removing player.")
            self._voice_state.clear()
            await self.disconnect(force=True)
        else:
            channel = self.guild.get_channel(int(channel_id))
            if channel != self.channel:
                if self.channel:
                    self._last_channel_id = self.channel.id
                self.channel = channel

        await self._send_lavalink_voice_update({**self._voice_state, "event": data})

    async def _send_lavalink_voice_update(self, voice_state: dict):
        if self._voice_state.keys() == {"sessionId", "event"}:
            await self.node.send(
                {
                    "op": LavalinkOutgoingOp.VOICE_UPDATE.value,
                    "guildId": str(self.guild.id),
                    "sessionId": voice_state["sessionId"],
                    "event": voice_state["event"],
                }
            )

    async def wait_until_ready(
            self, timeout: Optional[float] = None, no_raise: bool = False
    ) -> bool:
        """
        Waits for the underlying node to become ready.

        Parameters
        ----------
        timeout : Optional[float]
            The time to wait for the node to get ready. A timeout of None means to wait indefinitely.
        no_raise: bool
            If no_raise is set, returns false when a timeout occurs instead of propagating TimeoutError.
        """
        if self.node.ready:
            return True

        try:
            return await self.node.wait_until_ready(timeout=timeout)
        except asyncio.TimeoutError:
            if no_raise:
                return False
            else:
                raise

    async def connect(self, timeout: float = 2.0, reconnect: bool = False, deafen: bool = False):
        """
        Connects to the voice channel associated with this Player.

        Parameters
        ----------
        deafen: bool
            Prevent the bot from listening others'
        timeout : float
            Actually is not used, but must be present to match the signature
        reconnect: bool
            Actually is not used, but must be present to match the signature
        """
        self._last_resume = datetime.datetime.now(datetime.timezone.utc)
        self.connected_at = datetime.datetime.now(datetime.timezone.utc)
        self._connected = True
        self.node.add_player(self.guild.id, self)
        await self.node.refresh_player_state(self)
        await self.guild.change_voice_state(
            channel=self.channel, self_mute=False, self_deaf=deafen
        )

    async def move_to(self, channel: discord.VoiceChannel, deafen: bool = False):
        """
        Moves this player to a voice channel.

        Parameters
        ----------
        deafen : bool
            Prevent the bot from listening others
        channel : discord.VoiceChannel
            The channel to move to

        Raises
        ------
        TypeError
            If the channel is in another guild
        """
        if channel.guild != self.guild:
            raise TypeError(f"Cannot move {self!r} to a different guild.")
        if self.channel:
            self._last_channel_id = self.channel.id
        self.channel = channel
        await self.connect(deafen=deafen)
        if self.current:
            await self.resume(
                track=self.current, replace=True, start=self.position, pause=self._paused
            )

    async def disconnect(self, force: bool = False):
        """
        Disconnects this player from its voice channel.

        Parameters
        ----------
        force : bool
            Force the player to disconnect
        """
        self._is_autoplaying = False
        self._auto_play_sent = False
        self._connected = False
        if self.state == PlayerState.DISCONNECTING:
            return

        await self.update_state(PlayerState.DISCONNECTING)
        guild_id = self.guild.id
        if force:
            log.debug("Forcing player disconnect for %r", self)
            self.node.event_handler(
                LavalinkIncomingOp.EVENT,
                LavalinkEvents.FORCED_DISCONNECT,
                {
                    "guildId": guild_id,
                    "code": 42069,
                    "reason": "Forced Disconnect - Do not Reconnect",
                    "byRemote": True,
                    "retries": -1,
                },
            )

        await self.guild.change_voice_state(channel=None)
        await self.node.destroy_guild(guild_id)
        self.node.remove_player(self)
        self.cleanup()

    def store(self, key: Union[str, int], value: Any):
        """
        Stores a metadata value by key.

        Parameters
        ----------
        key : Union[str, int]
        value : Any
        """
        self._metadata[key] = value

    def fetch(self, key: Union[str, int], default: Optional[Any] = None) -> Any:
        """
        Returns a stored metadata value.

        Parameters
        ----------
        key
            Used to store metadata.
        default
            Optional, used if the key doesn't exist.

        Returns
        -------
        Any
            If the key doesn't exist returns the default value, otherwise the set value
        """
        return self._metadata.get(key, default)

    async def update_state(self, state: PlayerState):
        """
        Change the current player state
        Parameters
        ----------
        state: PlayerState
            The state to set
        """
        if state == self.state:
            return

        ws_rll_log.debug("Player %r changing state: %s -> %s", self, self.state.name, state.name)

        self.state = state

        if self._con_delay:
            self._con_delay = None

    async def handle_event(self, event: "LavalinkEvents", extra: Any):
        """
        Handles various Lavalink Events.

        If the event is TRACK END, extra will be TrackEndReason.

        If the event is TRACK EXCEPTION, extra will be the string reason.

        If the event is TRACK STUCK, extra will be the threshold ms.

        Parameters
        ----------
        event : node.LavalinkEvents
        extra : Any
        """
        log.debug("Received player event for player: %r - %r - %r.", self, event, extra)

        if event == LavalinkEvents.TRACK_END:
            if extra == TrackEndReason.FINISHED:
                await self.play()
            else:
                self._is_playing = False
        elif event == LavalinkEvents.WEBSOCKET_CLOSED:
            code = extra.get("code")
            if code in (4015, 4014, 4009, 4006, 4000, 1006):
                if not self._con_delay:
                    self._con_delay = ExponentialBackoff(base=1)

    async def handle_player_update(self, state: "PositionTime"):
        """
        Handles player updates from lavalink.

        Parameters
        ----------
        state : websocket.PlayerState
        """
        if state.position > self.position:
            self._is_playing = True
        log.debug("Updated player position for player: %r - %ds.", self, state.position // 1000)
        self.position = state.position

    # Play commands
    def add(self, requester: discord.User, track: Track):
        """
        Adds a track to the queue.

        Parameters
        ----------
        requester : discord.User
            Who requested the track.
        track : Track
            Result from any of the lavalink track search methods.
        """
        track.requester = requester
        self.queue.append(track)

    def maybe_shuffle(self, sticky_songs: int = 1):
        """Shuffle"""
        if self.shuffle and self.queue:  # Keeps queue order consistent unless adding new tracks
            self.force_shuffle(sticky_songs)

    def force_shuffle(self, sticky_songs: int = 1):
        """Shuffle the queue"""
        if not self.queue:
            return
        sticky = max(0, sticky_songs)  # Songs to  bypass shuffle
        # Keeps queue order consistent unless adding new tracks
        if sticky > 0:
            to_keep = self.queue[:sticky]
            to_shuffle = self.queue[sticky:]
        else:
            to_shuffle = self.queue
            to_keep = []
        if not self.shuffle_bumped:
            to_keep_bumped = [t for t in to_shuffle if t.extras.get("bumped", None)]
            to_shuffle = [t for t in to_shuffle if not t.extras.get("bumped", None)]
            to_keep.extend(to_keep_bumped)
            # Shuffles whole queue
        shuffle(to_shuffle)
        to_keep.extend(to_shuffle)
        # Keep next track in queue consistent while adding new tracks
        self.queue = to_keep

    async def play(self):
        """
        Starts playback from lavalink.
        """
        if self.repeat and self.current is not None:
            self.queue.append(self.current)

        self.current = None
        self.position = 0
        self._paused = False

        if not self.queue:
            await self.stop()
        else:
            self._is_playing = True

            track = self.queue.pop()

            if self.loop_queue:
                if self.current is not None:
                    self.queue.append(self.current)
                else:
                    self.queue.append(track)

            self.current = track
            log.debug("Assigned current track for player: %r.", self)
            await self.node.play(self.guild.id, track, start=track.start_timestamp, replace=True)

    async def resume(
            self, track: Track, replace: bool = True, start: int = 0, pause: bool = False
    ):
        log.debug("Resuming current track for player: %r.", self)
        self._is_playing = False
        self._paused = True
        await self.node.play(self.guild.id, track, start=start, replace=replace, pause=True)
        await self.pause(True)
        await self.pause(pause, timed=1)

    async def stop(self):
        """
        Stops playback from lavalink.

        .. important::

            This method will clear the queue.
        """
        await self.node.stop(self.guild.id)
        self.queue = deque()
        self.current = None
        self.position = 0
        self._paused = False
        self._is_autoplaying = False
        self._auto_play_sent = False

    async def skip(self):
        """
        Skips to the next song.
        """
        await self.play()

    async def pause(self, pause: bool = True, timed: Optional[int] = None):
        """
        Pauses the current song.

        Parameters
        ----------
        pause : bool
            Set to ``False`` to resume.
        timed : Optional[int]
            If an int is given the op will be called after it.
        """
        if timed is not None:
            await asyncio.sleep(timed)

        self._paused = pause
        await self.node.pause(self.guild.id, pause)

    async def set_volume(self, volume: int):
        """
        Sets the volume of Lavalink.

        Parameters
        ----------
        volume : int
            Between 0 and 150
        """
        self._volume = max(min(volume, 150), 0)
        await self.node.volume(self.guild.id, self.volume)

    async def seek(self, position: int):
        """
        If the track allows it, seeks to a position.

        Parameters
        ----------
        position : int
            Between 0 and track length.
        """
        if self.current.seekable:
            position = max(min(position, self.current.length), 0)
            await self.node.seek(self.guild.id, position)

    async def bass_boost(self):
        """Bass boost the song"""
        await self.node.equalizer(self.guild.id,
                                  [EqualizerBands(0, 0.15), EqualizerBands(1, 0.15), EqualizerBands(2, 0.15)])

    async def nightcore(self):
        """Apply the effect nightcore on the song"""
        await self.node.time_scale(self.guild.id, speed=1.20, pitch=1.1, rate=1.20)

    async def random_distortion(self):
        """
        Apply a random distortion

        .. warning::
            It can be extremely painful to listen to
        """
        await self.node.distortion(
            self.guild.id,
            random.randrange(0, 10),
            random.randrange(0, 10),
            random.randrange(0, 10),
            random.randrange(0, 10),
            random.randrange(0, 10),
            random.randrange(0, 10),
            random.randrange(0, 10),
            random.randrange(0, 10)
        )

    async def reset_filter(self):
        """Remove any applied filter"""
        await self.node.reset_filter(self.guild.id)

    async def equalizer(self, band: int, gain: float = 0.25):
        """
        Change the equalizer

        Parameters
        ----------
        band: int
            0 ??? x ??? 14
        gain: float
            is the multiplier for the given band
            -0.25 ??? x ??? 1
        """
        await self.node.equalizer(self.guild.id, [EqualizerBands(band, gain)])

    async def karaoke(self, level: float = 1.0, mono_level: float = 1.0, filter_band: float = 220.0,
                      filter_width: float = 100.0):
        """
        Remove the vocals

        Parameters
        ----------
        level : float
            how much to filter
        mono_level : float
            how much to filter
        filter_band : float
            the frequency band to filter
        filter_width : float
            the frequency width to filter
        """
        await self.node.karaoke(self.guild.id, level, mono_level, filter_band, filter_width)

    async def rotation(self, rotation: Optional[int] = None):
        """
        Rotates the sound around the stereo channels/user headphones
        Audio Panning

        Parameters
        ----------
        rotation : Optional[int]
            The frequency of the audio rotating around the listener in Hz
        """
        if rotation is None:
            rotation = random.randint(0, 60)

        await self.node.rotation(self.guild.id, rotation=rotation)

    async def timescale(self, speed: float = 1.0, pitch: float = 1.0, rate: float = 1.0):
        """
        Changes the speed, pitch, and rate

        Parameters
        ----------
        speed : float
            Should be >= 0
        pitch : float
            Should be >= 0
        rate : float
            Should be >= 0
        """
        await self.node.time_scale(self.guild.id, speed, pitch, rate)

    async def vibrato(self, frequency: float = 2.0, depth: float = 0.5):
        """
        Oscillates the pitch.

        Parameters
        ----------
        frequency : float
             0 < x ??? 14
        depth : float
            0 < x ??? 1
        """
        await self.node.vibrato(self.guild.id, frequency, depth)

    async def tremolo(self, frequency: float = 2.0, depth: float = 0.5):
        """
        Uses amplification to create a shuddering effect.
        Oscillates the volume

        Parameters
        ----------
        frequency : float
            Should be >= 0
        depth : float
            0 < x ??? 1
        """
        await self.node.tremolo(self.guild.id, frequency, depth)

    async def distortion(self, sin_offset: float = 0, sin_scale: float = 1, cos_offset: float = 0, cos_scale: float = 1,
                         tan_offset: float = 0, tan_scale: float = 1, offset: float = 0, scale: float = 1):
        """
        Distortion effect

        Parameters
        ----------
        sin_offset : int
        sin_scale : int
        cos_offset : float
        cos_scale : float
        tan_offset : float
        tan_scale : float
        offset : float
        scale : float
        """
        await self.node.distortion(self.guild.id, sin_offset, sin_scale, cos_offset, cos_scale, tan_offset, tan_scale,
                                   offset, scale)

    async def channel_mix(self, left_to_left: float = 1.0, left_to_right: float = 0.0, right_to_left: float = 0.0,
                          right_to_right: float = 1.0):
        """
        Mixes both channels (left and right)

        Parameters
        ----------
        left_to_left : float
        left_to_right : float
        right_to_left : float
        right_to_right : float
        """
        await self.node.channel_mix(self.guild.id, left_to_left, left_to_right, right_to_left, right_to_right)

    async def low_pass(self, smoothing: float = 20.0):
        """
        Higher frequencies get suppressed, while lower frequencies pass through this filter

        Parameters
        ----------
        smoothing : float
            how much to suppress
        """
        await self.node.low_pass(self.guild.id, smoothing)
