import pytest

import lavalink
import lavalink.node
import lavalink.player


@pytest.mark.asyncio
async def test_initialize(bot):
    await lavalink.initialize(bot)

    bot.add_listener.assert_called()

@pytest.mark.asyncio
async def test_add_node(bot):
    await lavalink.initialize(bot)
    await lavalink.add_node(bot, "localhost", "password", 2333, 2333)

    assert len(lavalink.node._nodes) == bot.shard_count
