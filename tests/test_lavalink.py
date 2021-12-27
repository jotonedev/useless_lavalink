import nextcord

import lavalink
import lavalink.node
import lavalink.player_manager


async def test_initialize(bot: nextcord.Client):
    await lavalink.initialize(bot, "localhost", "password", 2333, 2333)

    assert len(lavalink.node._nodes) == bot.shard_count

    bot.add_listener.assert_called()
