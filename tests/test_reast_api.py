from lavalink.rest_api import LoadResult, Track


def test_load_result_track():
    data = {
        "loadType": "TRACK_LOADED",
        "playlistInfo": {},
        "tracks": [
            {
                "track": "QAAAjQIAJVJpY2sgQXN0bGV5IC0gTmV2ZXIgR29ubmEgR2l2ZSBZb3UgVXAADlJpY2tBc3RsZXlWRVZPAAAAAAADPCAAC2RRdzR3OVdnWGNRAAEAK2h0dHBzOi8vd3d3LnlvdXR1YmUuY29tL3dhdGNoP3Y9ZFF3NHc5V2dYY1EAB3lvdXR1YmUAAAAAAAAAAA==",
                "info": {
                    "identifier": "dQw4w9WgXcQ",
                    "isSeekable": True,
                    "author": "RickAstleyVEVO",
                    "length": 212000,
                    "isStream": False,
                    "position": 0,
                    "title": "Rick Astley - Never Gonna Give You Up",
                    "uri": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "sourceName": "youtube"
                }
            }
        ]
    }

    result = LoadResult(data)

    assert not result.has_error
    assert not result.is_playlist
    assert len(result.tracks) == 1


def test_load_result_playlist():
    data = {
        "loadType": "PLAYLIST_LOADED",
        "playlistInfo": {
            "name": "Example YouTube Playlist",
            "selectedTrack": 2
        },
        "tracks": [
            {
                "track": "QAAAjQIAJVJpY2sgQXN0bGV5IC0gTmV2ZXIgR29ubmEgR2l2ZSBZb3UgVXAADlJpY2tBc3RsZXlWRVZPAAAAAAADPCAAC2RRdzR3OVdnWGNRAAEAK2h0dHBzOi8vd3d3LnlvdXR1YmUuY29tL3dhdGNoP3Y9ZFF3NHc5V2dYY1EAB3lvdXR1YmUAAAAAAAAAAA==",
                "info": {
                    "identifier": "dQw4w9WgXcQ",
                    "isSeekable": True,
                    "author": "RickAstleyVEVO",
                    "length": 212000,
                    "isStream": False,
                    "position": 0,
                    "title": "Rick Astley - Never Gonna Give You Up",
                    "uri": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "sourceName": "youtube"
                }
            },
            {
                "track": "QAAAjQIAJVJpY2sgQXN0bGV5IC0gTmV2ZXIgR29ubmEgR2l2ZSBZb3UgVXAADlJpY2tBc3RsZXlWRVZPAAAAAAADPCAAC2RRdzR3OVdnWGNRAAEAK2h0dHBzOi8vd3d3LnlvdXR1YmUuY29tL3dhdGNoP3Y9ZFF3NHc5V2dYY1EAB3lvdXR1YmUAAAAAAAAAAA==",
                "info": {
                    "identifier": "dQw4w9WgXcQ",
                    "isSeekable": True,
                    "author": "RickAstleyVEVO",
                    "length": 212000,
                    "isStream": False,
                    "position": 0,
                    "title": "Rick Astley - Never Gonna Give You Up",
                    "uri": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "sourceName": "youtube"
                }
            }
        ]
    }

    result = LoadResult(data)

    assert not result.has_error
    assert result.is_playlist
    assert len(result.tracks) == 2
    assert result.playlist_info.selectedTrack == 2
    assert result.playlist_info.name == "Example YouTube Playlist"


def test_track():
    data = {
        "track": "QAAAjQIAJVJpY2sgQXN0bGV5IC0gTmV2ZXIgR29ubmEgR2l2ZSBZb3UgVXAADlJpY2tBc3RsZXlWRVZPAAAAAAADPCAAC2RRdzR3OVdnWGNRAAEAK2h0dHBzOi8vd3d3LnlvdXR1YmUuY29tL3dhdGNoP3Y9ZFF3NHc5V2dYY1EAB3lvdXR1YmUAAAAAAAAAAA==",
        "info": {
            "identifier": "dQw4w9WgXcQ",
            "isSeekable": True,
            "author": "RickAstleyVEVO",
            "length": 212000,
            "isStream": False,
            "position": 0,
            "title": "Rick Astley - Never Gonna Give You Up",
            "uri": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "sourceName": "youtube"
        }
    }

    track = Track(data)

    assert track.source == "youtube"
    assert track.identifier == "dQw4w9WgXcQ"
    assert track.thumbnail == "https://img.youtube.com/vi/dQw4w9WgXcQ/mqdefault.jpg"
    assert not track.is_stream
