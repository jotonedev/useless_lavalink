import pytest
from nextcord.ext.commands import Bot

import lavalink
import lavalink.node
import lavalink.player


@pytest.mark.asyncio
async def test_initialize(bot: Bot):
    await lavalink.initialize(bot, "localhost", "password", 2333, 2333)

    assert len(lavalink.node._nodes) == bot.shard_count

    bot.add_listener.assert_called()
