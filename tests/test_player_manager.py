import pytest

import lavalink.node
import lavalink.player


@pytest.fixture
def voice_server_update(guild):
    def func(guild_id=guild.id):
        return {
            "t": "VOICE_SERVER_UPDATE",
            "s": 87,
            "op": 0,
            "d": {
                "token": "e5bbc4a783a1af5b",
                "guild_id": str(guild_id),
                "endpoint": "us-west43.discord.gg:80",
            },
        }

    return func


@pytest.fixture
def voice_state_update(bot, voice_channel):
    def func(user_id=bot.user.id, channel_id=voice_channel.id, guild_id=voice_channel.guild.id):
        return {
            "t": "VOICE_STATE_UPDATE",
            "s": 84,
            "op": 0,
            "d": {
                "user_id": str(user_id),
                "suppress": False,
                "session_id": "744d1ac65d00e31fb7ab29fc2436be3e",
                "self_video": False,
                "self_mute": False,
                "self_deaf": False,
                "mute": False,
                "guild_id": str(guild_id),
                "deaf": False,
                "channel_id": str(channel_id),
            },
        }

    return func


@pytest.mark.asyncio
async def test_configure_resuming(
        initialize_lavalink, voice_channel, voice_server_update, voice_state_update, node
):
    send_call = {
        "op": "configureResuming",
        'key': 'Test',
        'timeout': 60
    }

    node._MOCK_send.assert_called_with(send_call)
    node._resuming_configured = True
