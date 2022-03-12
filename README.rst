============
useless_lavalink
============

A Lavalink client library written for Python 3.9 using the AsyncIO framework. This is a fork of `Red-Lavalink <https://github.com/Cog-Creators/Red-Lavalink>`_.

To install::

    pip install useless_lavalink

*****
Usage
*****

.. code-block:: python

    import lavalink
    from discord.ext.commands import Bot

    bot = Bot()


    @bot.event
    async def on_ready():
        lavalink.initialize(
            bot, host='localhost', password='password',  ws_port=2333
        )


    async def search_and_play(voice_channel, search_terms):
        player = await lavalink.connect(voice_channel)
        tracks = await player.search_yt(search_terms)
        player.add(tracks[0])
        await player.play()

*********
Shuffling
*********
.. code-block:: python

    def shuffle_queue(player_id, forced=True):
        player = lavalink.get_player(player_id)
        if not forced:
            player.maybe_shuffle(sticky_songs=0)
            """
            `player.maybe_shuffle` respects `player.shuffle`
            And will only shuffle if `player.shuffle` is True.

            `player.maybe_shuffle` should be called every time
            you would expect the queue to be shuffled.

            `sticky_songs=0` will shuffle every song in the queue.
            """
        else:
            player.force_shuffle(sticky_songs=3)
            """
            `player.force_shuffle` does not respect `player.shuffle`
            And will always shuffle the queue.

            `sticky_songs=3` will shuffle every song after the first 3 songs in the queue.
            """




When shutting down, be sure to do the following::

    await lavalink.close(bot)
