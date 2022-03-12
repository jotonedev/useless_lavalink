from __future__ import annotations

import re
from collections import deque
from typing import Tuple, Any, Optional, TYPE_CHECKING
from urllib.parse import quote, urlparse

from aiohttp.client_exceptions import ServerDisconnectedError
from yarl import URL

from . import log
from .enums import ExceptionSeverity, LoadType, PlayerState
from .tuples import PlaylistInfo

if TYPE_CHECKING:
    pass

__all__ = ["Track", "RESTClient", "playlist_info", "LoadResult"]


# This exists to preprocess rather than pull in dataclasses for __post_init__
# noinspection PyPep8Naming
def playlist_info(name: Optional[str] = None, selectedTrack: Optional[int] = None):
    return PlaylistInfo(
        name=name if name is not None else "Unknown",
        selectedTrack=selectedTrack if selectedTrack is not None else -1,
    )


_re_youtube_timestamp = re.compile(r"[&?]t=(\d+)s?")
_re_soundcloud_timestamp = re.compile(r"#t=(\d+):(\d+)s?")
_re_twitch_timestamp = re.compile(r"\?t=(\d+)h(\d+)m(\d+)s")


def parse_timestamps(data: dict[str, Any]) -> list[dict[str, Any]]:
    if data["loadType"] == LoadType.PLAYLIST_LOADED:
        return data["tracks"]

    new_tracks = deque()
    query = data["query"]
    try:
        query_url = URL(query)
    except ValueError:
        query_url = None

    if query_url is None:
        return data["tracks"]

    for track in data["tracks"]:
        start_time = 0

        try:
            if all([query_url.scheme, query_url.host, query_url.path]) or any(
                    x in query for x in ["ytsearch:", "scsearch:"]
            ):
                if (
                        (query_url.host in ["youtube.com", "youtu.be"] or "ytsearch:" in query)
                        and any(x in query for x in ["&t=", "?t="])
                        and not all(k in query for k in ["playlist?", "&list="])
                ):
                    match = re.search(_re_youtube_timestamp, query)
                    if match:
                        start_time = int(match.group(1))
                elif (query_url.host == "soundcloud.com" or "scsearch:" in query) and "#t=" in query:
                    if "/sets/" not in query or ("/sets/" in query and "?in=" in query):
                        match = re.search(_re_soundcloud_timestamp, query)
                        if match:
                            start_time = (int(match.group(1)) * 60) + int(match.group(2))
                elif query_url.host == "twitch.tv" and "?t=" in query:
                    match = re.search(_re_twitch_timestamp, query)
                    if match:
                        start_time = (
                                (int(match.group(1)) * 60 * 60)
                                + (int(match.group(2)) * 60)
                                + int(match.group(3))
                        )
        except:
            pass

        track["info"]["timestamp"] = start_time * 1000
        new_tracks.append(track)

    return new_tracks


def reformat_query(query: str) -> str:
    try:
        query_url = urlparse(query)

        if all([query_url.scheme, query_url.netloc, query_url.path]) or any(
                x in query for x in ["ytsearch:", "scsearch:"]
        ):
            url_domain = ".".join(query_url.netloc.split(".")[-2:])
            if not query_url.netloc:
                url_domain = ".".join(query_url.path.split("/")[0].split(".")[-2:])
            if (
                    (url_domain in ["youtube.com", "youtu.be"] or "ytsearch:" in query)
                    and any(x in query for x in ["&t=", "?t="])
                    and not all(k in query for k in ["playlist?", "&list="])
            ):
                match = re.search(_re_youtube_timestamp, query)
                if match:
                    query = query.split("&t=")[0].split("?t=")[0]
            elif (url_domain == "soundcloud.com" or "scsearch:" in query) and "#t=" in query:
                if "/sets/" not in query or ("/sets/" in query and "?in=" in query):
                    match = re.search(_re_soundcloud_timestamp, query)
                    if match:
                        query = query.split("#t=")[0]
            elif url_domain == "twitch.tv" and "?t=" in query:
                match = re.search(_re_twitch_timestamp, query)
                if match:
                    query = query.split("?t=")[0]
    except:
        pass
    return query


class Track:
    """
    Information about a Lavalink track.

    Attributes
    ----------
    requester : discord.User
        The user who requested the track.
    track_identifier : str
        Track identifier used by the Lavalink player to play tracks.
    seekable : bool
        Boolean determining if seeking can be done on this track.
    author : str
        The author of this track.
    length : int
        The length of this track in milliseconds.
    is_stream : bool
        Determines whether Lavalink will stream this track.
    position : int
        Current seeked position to begin playback.
    title : str
        Title of this track.
    uri : str
        The playback url of this track.
    start_timestamp: int
        The track start time in milliseconds as provided by the query.
    """

    def __init__(self, data: dict[str, Any]):
        self.requester = None

        self.track_identifier: str = data.get("track")
        self._info: dict = data.get("info", {})
        self.source: Optional[str] = self._info.get("sourceName", None)
        self.seekable: bool = self._info.get("isSeekable", False)
        self.author: str = self._info.get("author")
        self.length: int = self._info.get("length", 0)
        self.is_stream: bool = self._info.get("isStream", False)
        self.position: int = self._info.get("position")
        self.title: str = self._info.get("title")
        self.uri: str = self._info.get("uri")
        self.start_timestamp: int = self._info.get("timestamp", 0)
        self.extras: dict = data.get("extras", {})

    @property
    def thumbnail(self) -> Optional[str]:
        """Returns a thumbnail URL for YouTube tracks."""
        if self.source == "youtube":
            return f"https://img.youtube.com/vi/{self._info['identifier']}/mqdefault.jpg"
        elif self.source == "twitch":
            return f"https://static-cdn.jtvnw.net/previews-ttv/live_user_{self.author.lower()}.jpg"
        elif self.source == "soundcloud":
            # TODO: return a real thumbnail
            return f"https://developers.soundcloud.com/assets/logo_big_black-4fbe88aa0bf28767bbfc65a08c828c76.png"
        else:
            return None

    def __eq__(self, other):
        """Overrides the default implementation"""
        if isinstance(other, Track):
            return self.track_identifier == other.track_identifier
        return NotImplemented

    def __ne__(self, other):
        """Overrides the default implementation"""
        x = self.__eq__(other)
        if x is not NotImplemented:
            return not x
        return NotImplemented

    def __hash__(self):
        """Overrides the default implementation"""
        return hash(tuple(sorted([self.track_identifier, self.title, self.author, self.uri])))

    def __repr__(self):
        return (
            "<Track: "
            f"track_identifier={self.track_identifier!r}, "
            f"author={self.author!r}, "
            f"length={self.length}, "
            f"is_stream={self.is_stream}, uri={self.uri!r}, title={self.title!r}>"
        )


class LoadResult:
    """
    The result of a load_tracks request.

    Attributes
    ----------
    load_type : LoadType
        The result of the loadtracks request
    playlist_info : Optional[PlaylistInfo]
        The playlist information detected by Lavalink
    tracks : tuple[Track, ...]
        The tracks that were loaded, if any
    """

    def __init__(self, data: dict[str]):
        self._raw = data
        _fallback = {
            "loadType": LoadType.LOAD_FAILED,
            "exception": {
                "message": "Lavalink API returned an unsupported response, Please report it.",
                "severity": ExceptionSeverity.SUSPICIOUS,
            },
            "playlistInfo": {},
            "tracks": [],
        }
        for (k, v) in _fallback.items():
            if k not in data:
                if (
                        k == "exception"
                        and data.get("loadType", LoadType.LOAD_FAILED) != LoadType.LOAD_FAILED
                ):
                    continue
                elif k == "exception":
                    v["message"] = (
                        f"Timestamp: {self._raw.get('timestamp', 'Unknown')}\n"
                        f"Status Code: {self._raw.get('status', 'Unknown')}\n"
                        f"Error: {self._raw.get('error', 'Unknown')}\n"
                        f"Query: {self._raw.get('query', 'Unknown')}\n"
                        f"Load Type: {self._raw['loadType']}\n"
                        f"Message: {self._raw.get('message', v['message'])}"
                    )
                self._raw.update({k: v})

        self.load_type = LoadType(self._raw["loadType"])

        is_playlist = self._raw.get("isPlaylist") or self.load_type == LoadType.PLAYLIST_LOADED
        if is_playlist is True:
            self.is_playlist = True
            self.playlist_info = playlist_info(**self._raw["playlistInfo"])
        elif is_playlist is False:
            self.is_playlist = False
            self.playlist_info = None
        else:
            self.is_playlist = None
            self.playlist_info = None
        _tracks = parse_timestamps(self._raw) if self._raw.get("query") else self._raw["tracks"]
        self.tracks = tuple(Track(t) for t in _tracks)

    @property
    def has_error(self) -> bool:
        return self.load_type == LoadType.LOAD_FAILED

    @property
    def exception_message(self) -> Optional[str]:
        """
        On Lavalink V3, if there was an exception during a load or get tracks call
        this property will be populated with the error message.
        If there was no error this property will be ``None``.
        """
        if self.has_error:
            exception_data = self._raw.get("exception", {})
            return exception_data.get("message")
        return None

    @property
    def exception_severity(self) -> Optional[ExceptionSeverity]:
        if self.has_error:
            exception_data = self._raw.get("exception", {})
            severity = exception_data.get("severity")
            if severity is not None:
                return ExceptionSeverity(severity)
        return None


class RESTClient:
    """
    Client class used to access the REST endpoints on a Lavalink node.
    """

    def __init__(self, player: "player.Player"):
        self.player = player
        self.node = player.node
        self._session = self.node.session
        self._uri = "http://{}:{}/loadtracks?identifier=".format(self.node.host, self.node.port)
        self._headers = {"Authorization": self.node.password}

        self.state = player.state

        self._warned = False

    def __check_node_ready(self):
        if self.state != PlayerState.READY:
            raise RuntimeError("Cannot execute REST request when node not ready.")

    async def _get(self, url: str) -> dict[str, Any]:
        try:
            async with self._session.get(url, headers=self._headers) as resp:
                data = await resp.json(content_type=None)
        except ServerDisconnectedError:
            if self.state == PlayerState.DISCONNECTING:
                return {
                    "loadType": LoadType.LOAD_FAILED,
                    "exception": {
                        "message": "Load tracks interrupted by player disconnect.",
                        "severity": ExceptionSeverity.COMMON,
                    },
                    "tracks": [],
                }
            log.debug("Received server disconnected error when player state = %s", self.state.name)
            raise
        return data

    async def load_tracks(self, query: str) -> LoadResult:
        """
        Executes a loadtracks request. Only works on Lavalink V3.

        Parameters
        ----------
        query : str

        Returns
        -------
        LoadResult
        """
        self.__check_node_ready()
        _raw_url = str(query)
        parsed_url = reformat_query(_raw_url)
        url = self._uri + quote(parsed_url)

        data = await self._get(url)
        if isinstance(data, dict):
            data["query"] = _raw_url
            data["encodedquery"] = url
            return LoadResult(data)
        elif isinstance(data, list):
            modified_data = {
                "loadType": LoadType.V2_COMPAT,
                "tracks": data,
                "query": _raw_url,
                "encodedquery": url,
            }
            return LoadResult(modified_data)

    async def get_tracks(self, query: str) -> Tuple[Track, ...]:
        """
        Gets tracks from lavalink.

        Parameters
        ----------
        query : str

        Returns
        -------
        Tuple[Track, ...]
        """
        if not self._warned:
            log.warn("get_tracks() is now deprecated. Please switch to using load_tracks().")
            self._warned = True
        result = await self.load_tracks(query)
        return result.tracks

    async def search_yt(self, query: str) -> LoadResult:
        """
        Gets track results from YouTube from Lavalink.

        Parameters
        ----------
        query : str

        Returns
        -------
        list of Track
        """
        return await self.load_tracks(f"ytsearch:{query}")

    async def search_sc(self, query: str) -> LoadResult:
        """
        Gets track results from SoundCloud from Lavalink.

        Parameters
        ----------
        query : str

        Returns
        -------
        list of Track
        """
        return await self.load_tracks(f"scsearch:{query}")
