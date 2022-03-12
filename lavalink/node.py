from __future__ import annotations

import asyncio
import contextlib
import secrets
import string
import typing
from collections import deque
from typing import Awaitable, KeysView, Optional, ValuesView, cast, Union, Any

import aiohttp
from discord.backoff import ExponentialBackoff
from discord.ext.commands import Bot

from . import log, ws_ll_log, ws_rll_log
from .enums import LavalinkEvents, LavalinkIncomingOp, LavalinkOutgoingOp, NodeState, PlayerState, FiltersOp
from .player import Player
from .rest_api import Track
from .tuples import *
from .utils import VoiceChannel

__all__ = ["Stats", "Node", "NodeStats", "get_node", "get_nodes_stats"]

_nodes: list[Node] = []


# Originally Added in: https://github.com/PythonistaGuild/Wavelink/pull/66
class _Key:
    def __init__(self, key_len: int = 32):
        self.length: int = key_len
        self.persistent: str = ""
        self.__repr__()

    def __repr__(self) -> str:
        """Generate a new key, return it and make it persistent"""
        alphabet = string.ascii_letters + string.digits + "#$%&()*+,-./:;<=>?@[]^_~!"
        key = "".join(secrets.choice(alphabet) for _ in range(self.length))
        self.persistent = key
        return key

    def __str__(self) -> str:
        """Return the persistent key."""
        # Ensure output is not a non-string
        # Since input could be Any object.
        if not self.persistent:
            return self.__repr__()
        return str(self.persistent)


class Stats:
    def __init__(self,
                 memory: dict[str, int],
                 players: int,
                 active_players: int,
                 cpu: dict[str, Union[str, float]],
                 uptime: int
                 ):
        self.memory = MemoryInfo(**memory)
        self.players = players
        self.active_players = active_players
        self.cpu_info = CPUInfo(**cpu)
        self.uptime = uptime


# Node stats related class below and how it is called is originally from:
# https://github.com/PythonistaGuild/Wavelink/blob/master/wavelink/stats.py#L41
# https://github.com/PythonistaGuild/Wavelink/blob/master/wavelink/websocket.py#L132
class NodeStats:
    def __init__(self, data: dict[str, Union[int, dict[str, Union[int, float]]]]):
        self.uptime: int = data["uptime"]

        self.players: int = data["players"]
        self.playing_players: int = data["playingPlayers"]

        memory: dict[str, int] = data["memory"]
        self.memory_free: int = memory["free"]
        self.memory_used: int = memory["used"]
        self.memory_allocated: int = memory["allocated"]
        self.memory_reservable: int = memory["reservable"]

        cpu: dict[str, Union[int, float]] = data["cpu"]
        self.cpu_cores: int = cpu["cores"]
        self.system_load: float = cpu["systemLoad"]
        self.lavalink_load: float = cpu["lavalinkLoad"]

        frame_stats: Optional[dict[str, int]] = data.get("frameStats", {})
        self.frames_sent: int = frame_stats.get("sent", -1)
        self.frames_nulled: int = frame_stats.get("nulled", -1)
        self.frames_deficit: int = frame_stats.get("deficit", -1)

    def __repr__(self) -> str:
        return (
            "<NodeStats: "
            f"uptime={self.uptime}, "
            f"players={self.players}, "
            f"playing_players={self.playing_players}, "
            f"memory_free={self.memory_free}, memory_used={self.memory_used}, "
            f"cpu_cores={self.cpu_cores}, system_load={self.system_load}, "
            f"lavalink_load={self.lavalink_load}>"
        )


class Node:
    _is_shutdown: bool = False

    def __init__(
            self,
            _loop: asyncio.BaseEventLoop,
            event_handler: typing.Callable,
            host: str,
            password: str,
            port: int,
            user_id: int,
            num_shards: int,
            resume_key: Optional[str] = None,
            resume_timeout: int = 60,
            bot: Optional[Bot] = None,
    ):
        """
        Represents a Lavalink node.

        Parameters
        ----------
        _loop : asyncio.BaseEventLoop
            The event loop of the bot.
        event_handler
            Function to dispatch events to.
        host : str
            Lavalink player host.
        password : str
            Password for the Lavalink player.
        port : int
            Port of the Lavalink player event websocket.
        user_id : int
            User ID of the bot.
        num_shards : int
            Number of shards to which the bot is currently connected.
        resume_key : Optional[str]
            A resume key used for resuming a session upon re-establishing a WebSocket connection to Lavalink.
        resume_timeout : int
            How long the node should wait for a connection while disconnected before clearing all players.
        bot: AutoShardedBot
            The Bot object that's connect to discord.
        """
        self.loop = _loop
        self.bot = bot
        self.event_handler = event_handler
        self.host = host
        self.port = port
        self.password = password
        self._resume_key = resume_key
        if self._resume_key is None:
            self._resume_key = self._gen_key()
        self._resume_timeout = resume_timeout
        self._resuming_configured = False
        self.num_shards = num_shards
        self.user_id = user_id

        self._ready_event = asyncio.Event()

        self._ws = None
        self._listener_task = None
        self.session = aiohttp.ClientSession()

        self._queue = deque()
        self._players_dict = {}

        self.state = NodeState.CONNECTING
        self._state_handlers = deque()
        self._retries = 0

        self.stats = None

        if self not in _nodes:
            _nodes.append(self)

        self._closers = (
            aiohttp.WSMsgType.CLOSE,
            aiohttp.WSMsgType.CLOSING,
            aiohttp.WSMsgType.CLOSED,
        )

        self.register_state_handler(self.node_state_handler)

    def __repr__(self) -> str:
        return (
            "<Node: "
            f"state={self.state.name}, "
            f"host={self.host}, "
            f"port={self.port}, "
            f"password={'*' * len(self.password)}, resume_key={self._resume_key}, "
            f"shards={self.num_shards}, user={self.user_id}, stats={self.stats}>"
        )

    @property
    def headers(self) -> dict:
        return self._get_connect_headers()

    @property
    def players(self) -> ValuesView[Player]:
        return self._players_dict.values()

    @property
    def guild_ids(self) -> KeysView[int]:
        return self._players_dict.keys()

    def _gen_key(self):
        if self._resume_key is None:
            return _Key()
        else:
            # if this is a class then it will generate a persistent key
            # We should not check the instance since
            # we would still make 1 extra call to check, which is useless.
            self._resume_key.__repr__()
            return self._resume_key

    async def connect(self, timeout: int = None, secured: bool = True):
        """
        Connects to the Lavalink player event websocket.

        Parameters
        ----------
        secured: bool
           Whether to use the `wss://` protocol.
        timeout : int
            Time after which to timeout on attempting to connect to the Lavalink websocket,
            ``None`` is considered never, but the underlying code may stop trying past a
            certain point.

        Raises
        ------
        asyncio.TimeoutError
            If the websocket failed to connect after the given time.
        """
        self._is_shutdown = False

        if secured:
            uri = f"wss://{self.host}:{self.port}"
        else:
            uri = f"ws://{self.host}:{self.port}"

        ws_ll_log.info("Lavalink WS connecting to %s with headers %s", uri, self.headers)

        await asyncio.wait_for(self._multi_try_connect(uri), timeout)

        ws_ll_log.debug("Creating Lavalink WS listener.")
        if self._listener_task is not None:
            self._listener_task.cancel()
        self._listener_task = self.loop.create_task(self.listener())
        self.loop.create_task(self._configure_resume())
        if self._queue:
            for data in self._queue:
                await self.send(data)
            self._queue.clear()
        self._ready_event.set()
        self.update_state(NodeState.READY)
        ws_ll_log.info("Lavalink WS connected to %s", uri)

    async def _configure_resume(self):
        if self._resuming_configured:
            return
        if self._resume_key and self._resume_timeout and self._resume_timeout > 0:
            await self.send(
                dict(
                    op="configureResuming",
                    key=str(self._resume_key),
                    timeout=self._resume_timeout,
                )
            )
            self._resuming_configured = True
            ws_ll_log.debug("Server Resuming has been configured.")

    async def wait_until_ready(self, timeout: Optional[float] = None):
        await asyncio.wait_for(self._ready_event.wait(), timeout=timeout)

    def _get_connect_headers(self) -> dict:
        headers = {
            "Authorization": self.password,
            "User-Id": str(self.user_id),
            "Num-Shards": str(self.num_shards),
            "Client-Name": "Useless-Lavalink"
        }
        if self._resume_key:
            headers["Resume-Key"] = str(self._resume_key)
        return headers

    @property
    def lavalink_major_version(self):
        if not self.ready:
            raise RuntimeError("Node not ready!")
        return self._ws.response_headers.get("Lavalink-Major-Version")

    @property
    def ready(self) -> bool:
        """
        Whether the underlying node is ready for requests.
        """
        return self.state == NodeState.READY

    async def _multi_try_connect(self, uri):
        backoff = ExponentialBackoff()
        attempt = 1
        if self._ws is not None:
            await self._ws.close(code=4006, message=b"Reconnecting")

        while self._is_shutdown is False and (self._ws is None or self._ws.closed):
            self._retries += 1
            try:
                ws = await self.session.ws_connect(url=uri, headers=self.headers, heartbeat=60)
            except (OSError, aiohttp.ClientConnectionError):
                delay = backoff.delay()
                ws_ll_log.error("Failed connect attempt %s, retrying in %s", attempt, delay)
                await asyncio.sleep(delay)
                attempt += 1
                if attempt > 5:
                    raise asyncio.TimeoutError
            except aiohttp.WSServerHandshakeError:
                ws_ll_log.error("Failed connect WSServerHandshakeError")
                raise asyncio.TimeoutError
            else:
                self.session_resumed = ws._response.headers.get("Session-Resumed", False)
                if self._ws is not None and self.session_resumed:
                    ws_ll_log.info("WEBSOCKET Resumed Session with key: %s", self._resume_key)
                self._ws = ws
                break

    async def listener(self):
        """
        Listener task for receiving ops from Lavalink.
        """
        while self._is_shutdown is False:
            msg = await self._ws.receive()
            if msg.type in self._closers:
                if self._resuming_configured:
                    if self.state != NodeState.RECONNECTING:
                        ws_ll_log.info("[NODE] | NODE Resuming: %s", msg.extra)
                        self.update_state(NodeState.RECONNECTING)
                        self.loop.create_task(self._reconnect())
                    return
                else:
                    ws_ll_log.info("[NODE] | Listener closing: %s", msg.extra)
                    break
            elif msg.type == aiohttp.WSMsgType.TEXT:
                data = msg.json()
                try:
                    op = LavalinkIncomingOp(data.get("op"))
                except ValueError:
                    ws_ll_log.info("[NODE] | Received unknown op: %s", data)
                else:
                    ws_ll_log.debug("[NODE] | Received known op: %s", data)
                    self.loop.create_task(self._handle_op(op, data))
            elif msg.type == aiohttp.WSMsgType.ERROR:
                exc = self._ws.exception()
                ws_ll_log.info("[NODE] | Exception in WebSocket!", exc_info=exc)
                break
            else:
                ws_ll_log.info(
                    "[NODE] | WebSocket connection received unexpected message: %s:%s",
                    msg.type,
                    msg.data,
                )
        if self.state != NodeState.RECONNECTING:
            ws_ll_log.warning(
                "[NODE] | %s - WS %s SHUTDOWN %s.", self, not self._ws.closed, self._is_shutdown
            )
            self.update_state(NodeState.RECONNECTING)
            self.loop.create_task(self._reconnect())

    async def _handle_op(self, op: LavalinkIncomingOp, data: dict[str, Any]):
        if op == LavalinkIncomingOp.EVENT:
            try:
                event = LavalinkEvents(data.get("type"))
            except ValueError:
                ws_ll_log.info("Unknown event type: %s", data)
            else:
                self.event_handler(op, event, data)
        elif op == LavalinkIncomingOp.PLAYER_UPDATE:
            state = data.get("state", {})
            state = PositionTime(position=state.get("position", 0), time=state.get("time", 0),
                                 connected=state.get("connected", False))
            self.event_handler(op, state, data)
        elif op == LavalinkIncomingOp.STATS:
            stats = Stats(
                memory=data.get("memory"),
                players=data.get("players"),
                active_players=data.get("playingPlayers"),
                cpu=data.get("cpu"),
                uptime=data.get("uptime"),
            )
            self.stats = NodeStats(data)
            self.event_handler(op, stats, data)
        else:
            ws_ll_log.info("Unknown op type: %r", data)

    async def _reconnect(self):
        self._ready_event.clear()

        if self._is_shutdown is True:
            ws_ll_log.info("[NODE] | Shutting down Lavalink WS.")
            return
        if self.state != NodeState.CONNECTING:
            self.update_state(NodeState.RECONNECTING)
        if self.state != NodeState.RECONNECTING:
            return
        backoff = ExponentialBackoff(base=1)
        attempt = 1
        while self.state == NodeState.RECONNECTING:
            attempt += 1
            try:
                await self.connect()
            except asyncio.TimeoutError:
                delay = backoff.delay()
                ws_ll_log.info("[NODE] | Failed to reconnect to the Lavalink server.")
                ws_ll_log.info(
                    "[NODE] | Lavalink WS reconnect connect attempt %s, retrying in %s",
                    attempt,
                    delay,
                )

            else:
                ws_ll_log.info("[NODE] | Reconnect successful.")
                self.dispatch_reconnect()
                self._retries = 0

    def dispatch_reconnect(self):
        for guild_id in self.guild_ids:
            self.event_handler(
                LavalinkIncomingOp.EVENT,
                LavalinkEvents.WEBSOCKET_CLOSED,
                {
                    "guildId": guild_id,
                    "code": 42069,
                    "reason": "Lavalink WS reconnected",
                    "byRemote": True,
                    "retries": self._retries,
                },
            )

    def update_state(self, next_state: NodeState):
        if next_state == self.state:
            return

        ws_ll_log.debug("Changing node state: %s -> %s", self.state.name, next_state.name)
        old_state = self.state
        self.state = next_state
        if self.loop.is_closed():
            ws_ll_log.debug("Event loop closed, not notifying state handlers.")
            return
        for handler in self._state_handlers:
            self.loop.create_task(handler(next_state, old_state))

    def register_state_handler(self, func):
        if not asyncio.iscoroutinefunction(func):
            raise ValueError("Argument must be a coroutine object.")

        if func not in self._state_handlers:
            self._state_handlers.append(func)

    def unregister_state_handler(self, func):
        self._state_handlers.remove(func)

    async def create_player(self, channel: VoiceChannel, deafen: bool = False) -> Player:
        """
        Connects to a discord voice channel.

        This function is safe to repeatedly call as it will return an existing
        player if there is one.

        Parameters
        ----------
        deafen
        channel

        Returns
        -------
        Player
            The created Player object.
        """
        if self._already_in_guild(channel):
            p = self.get_player(channel.guild.id)
            await p.move_to(channel, deafen=deafen)
        else:
            p = await channel.connect(cls=Player)
            if deafen:
                await p.guild.change_voice_state(channel=p.channel, self_deaf=True)
            self._players_dict[channel.guild.id] = p
            await self.refresh_player_state(p)
        return p

    def _already_in_guild(self, channel: VoiceChannel) -> bool:
        return channel.guild.id in self._players_dict

    def get_player(self, guild_id: int) -> Player:
        """
        Gets a Player object from a guild ID.

        Parameters
        ----------
        guild_id : int
            Discord guild ID.

        Returns
        -------
        Player

        Raises
        ------
        KeyError
            If that guild does not have a Player, e.g. is not connected to any
            voice channel.
        """
        if guild_id in self._players_dict:
            return self._players_dict[guild_id]
        raise KeyError("No such player for that guild.")

    async def node_state_handler(self, next_state: NodeState, old_state: NodeState):
        ws_rll_log.debug("Received node state update: %s -> %s", old_state.name, next_state.name)
        if next_state == NodeState.READY:
            await self.update_player_states(PlayerState.READY)
        elif next_state == NodeState.DISCONNECTING:
            await self.update_player_states(PlayerState.DISCONNECTING)
        elif next_state in (NodeState.CONNECTING, NodeState.RECONNECTING):
            await self.update_player_states(PlayerState.NODE_BUSY)

    async def update_player_states(self, state: PlayerState):
        for p in self.players:
            await p.update_state(state)

    async def refresh_player_state(self, player: Player):
        if self.ready:
            await player.update_state(PlayerState.READY)
        elif self.state == NodeState.DISCONNECTING:
            await player.update_state(PlayerState.DISCONNECTING)
        else:
            await player.update_state(PlayerState.NODE_BUSY)

    def add_player(self, guild_id: int, player: Player):
        """Register a player"""
        self._players_dict[guild_id] = player

    def remove_player(self, player: Player):
        if player.state != PlayerState.DISCONNECTING:
            log.error(
                "Attempting to remove a player (%r) from player list with state: %s",
                player,
                player.state.name,
            )
            return
        guild_id = player.channel.guild.id
        if guild_id in self._players_dict:
            del self._players_dict[guild_id]

    async def disconnect(self):
        """
        Shuts down and disconnects the websocket.
        """
        self._is_shutdown = True
        self._ready_event.clear()

        self.update_state(NodeState.DISCONNECTING)

        if self._resuming_configured:
            await self.send(dict(op="configureResuming", key=None))
        self._resuming_configured = False

        for p in tuple(self.players):
            await p.disconnect(force=True)
        log.debug("Disconnected all players.")

        if self._ws is not None and not self._ws.closed:
            await self._ws.close()

        if self._listener_task is not None and not self.loop.is_closed():
            self._listener_task.cancel()

        await self.session.close()

        self._state_handlers = []

        _nodes.remove(self)
        ws_ll_log.info("Shutdown Lavalink WS.")

    async def send(self, data):
        if self._ws is None or self._ws.closed:
            self._queue.append(data)
        else:
            ws_ll_log.debug("Sending data to Lavalink: %s", data)
            await self._ws.send_json(data)

    async def send_lavalink_voice_update(self, guild_id, session_id, event):
        await self.send(
            {
                "op": LavalinkOutgoingOp.VOICE_UPDATE.value,
                "guildId": str(guild_id),
                "sessionId": session_id,
                "event": event,
            }
        )

    async def destroy_guild(self, guild_id: int):
        await self.send({"op": LavalinkOutgoingOp.DESTROY.value, "guildId": str(guild_id)})

    async def no_event_stop(self, guild_id: int):
        await self.send({"op": LavalinkOutgoingOp.STOP.value, "guildId": str(guild_id)})

    # Player commands
    async def stop(self, guild_id: int):
        await self.no_event_stop(guild_id=guild_id)
        self.event_handler(
            LavalinkIncomingOp.EVENT, LavalinkEvents.QUEUE_END, {"guildId": str(guild_id)}
        )

    async def no_stop_play(
            self,
            guild_id: int,
            track: Track,
            replace: bool = True,
            start: int = 0,
            pause: bool = False,
    ):
        await self.send(
            {
                "op": LavalinkOutgoingOp.PLAY.value,
                "guildId": str(guild_id),
                "track": track.track_identifier,
                "noReplace": not replace,
                "startTime": str(start),
                "pause": pause,
            }
        )

    async def play(
            self,
            guild_id: int,
            track: Track,
            replace: bool = True,
            start: int = 0,
            pause: bool = False,
    ):
        # await self.send({"op": LavalinkOutgoingOp.STOP.value, "guildId": str(guild_id)})
        await self.no_stop_play(
            guild_id=guild_id, track=track, replace=replace, start=start, pause=pause
        )

    async def pause(self, guild_id, paused):
        await self.send(
            {"op": LavalinkOutgoingOp.PAUSE.value, "guildId": str(guild_id), "pause": paused}
        )

    async def volume(self, guild_id: int, _volume: int):
        await self.send(
            {"op": LavalinkOutgoingOp.VOLUME.value, "guildId": str(guild_id), "volume": _volume}
        )

    async def seek(self, guild_id: int, position: int):
        await self.send(
            {"op": LavalinkOutgoingOp.SEEK.value, "guildId": str(guild_id), "position": position}
        )

    async def equalizer(self, guild_id: int, bands: list[EqualizerBands]):
        await self.send(
            {
                "op": LavalinkOutgoingOp.FILTERS.value,
                "guildId": str(guild_id),
                FiltersOp.EQUALIZER.value: [{"band": band.band, "gain": band.gain} for band in bands]
            }
        )

    async def karaoke(self, guild_id: int, level: float = 1.0, mono_level: float = 1.0, filter_band: float = 220.0,
                      filter_width: float = 100.0):
        await self.send(
            {
                "op": LavalinkOutgoingOp.FILTERS.value,
                "guildId": str(guild_id),
                FiltersOp.KARAOKE.value: {
                    "level": level,
                    "monoLevel": mono_level,
                    "filterBand": filter_band,
                    "filterWidth": filter_width
                }
            }
        )

    async def time_scale(self, guild_id: int, speed: float = 1.0, pitch: float = 1.0, rate: float = 1.0):
        await self.send(
            {
                "op": LavalinkOutgoingOp.FILTERS.value,
                "guildId": str(guild_id),
                FiltersOp.TIMESCALE.value: {
                    "speed": speed,
                    "pitch": pitch,
                    "rate": rate,
                }
            }
        )

    async def tremolo(self, guild_id: int, frequency: float = 2.0, depth: float = 0.5):
        if not (0 < depth <= 1):
            raise ValueError("Depth must be 0 < x ≤ 1")

        if frequency <= 0:
            raise ValueError("Frequency must be greater than 0")

        await self.send(
            {
                "op": LavalinkOutgoingOp.FILTERS.value,
                "guildId": str(guild_id),
                FiltersOp.TREMOLO.value: {
                    "frequency": frequency,
                    "depth": depth,
                }
            }
        )

    async def vibrato(self, guild_id: int, frequency: float = 2.0, depth: float = 0.5):
        if not (0 < depth <= 1):
            raise ValueError("Depth must be 0 < x ≤ 1")

        if not (0 < frequency <= 14):
            raise ValueError("Frequency must be 0 < x ≤ 14")

        await self.send(
            {
                "op": LavalinkOutgoingOp.FILTERS.value,
                "guildId": str(guild_id),
                FiltersOp.VIBRATO.value: {
                    "frequency": frequency,
                    "depth": depth,
                }
            }
        )

    async def rotation(self, guild_id: int, rotation: int = 0):
        await self.send(
            {
                "op": LavalinkOutgoingOp.FILTERS.value,
                "guildId": str(guild_id),
                FiltersOp.ROTATION.value: {
                    "rotation": rotation,
                }
            }
        )

    async def distortion(self, guild_id: int, sin_offset: int = 0, sin_scale: int = 1, cos_offset: int = 0,
                         cos_scale: int = 1, tan_offset: int = 0, tan_scale: int = 1, offset: int = 0, scale: int = 1):
        await self.send(
            {
                "op": LavalinkOutgoingOp.FILTERS.value,
                "guildId": str(guild_id),
                FiltersOp.DISTORTION.value: {
                    "sinOffset": sin_offset,
                    "sinScale": sin_scale,
                    "cosOffset": cos_offset,
                    "cosScale": cos_scale,
                    "tanOffset": tan_offset,
                    "tanScale": tan_scale,
                    "offset": offset,
                    "scale": scale
                }
            }
        )

    async def channel_mix(self, guild_id: int, left_to_left: float = 1.0, left_to_right: float = 0.0,
                          right_to_left: float = 0.0, right_to_right: float = 1.0):
        await self.send(
            {
                "op": LavalinkOutgoingOp.FILTERS.value,
                "guildId": str(guild_id),
                FiltersOp.CHANNEL_MIX.value: {
                    "leftToLeft": left_to_left,
                    "leftToRight": left_to_right,
                    "rightToLeft": right_to_left,
                    "rightToRight": right_to_right,
                }
            }
        )

    async def low_pass(self, guild_id: int, smoothing: float = 0.0):
        await self.send(
            {
                "op": LavalinkOutgoingOp.FILTERS.value,
                "guildId": str(guild_id),
                FiltersOp.LOW_PASS.value: {
                    "smoothing": smoothing,
                }
            }
        )

    async def reset_filter(self, guild_id: int):
        await self.send(
            {
                "op": LavalinkOutgoingOp.FILTERS.value,
                "guildId": str(guild_id)
            }
        )


def get_node(guild_id: int = None, ignore_ready_status: bool = False) -> Node:
    """
    Gets a node based on a guild ID, useful for noding separation. If the
    guild ID does not already have a node association, the least used
    node is returned. Skips over nodes that are not yet ready.

    Parameters
    ----------
    guild_id : int
    ignore_ready_status : bool

    Returns
    -------
    Node
    """
    guild_count = 1e10
    least_used = None

    for node in _nodes:
        guild_ids = node.guild_ids

        if ignore_ready_status is False and not node.ready:
            continue
        elif len(guild_ids) < guild_count:
            guild_count = len(guild_ids)
            least_used = node

        if guild_id in guild_ids:
            return node

    if least_used is None:
        raise IndexError("No nodes found.")

    return least_used


def get_nodes_stats():
    return [node.stats for node in _nodes]


async def disconnect():
    for node in _nodes.copy():
        await node.disconnect()
