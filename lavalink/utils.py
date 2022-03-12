from typing import Union

import discord


def format_time(time):
    """Formats the given time into HH:MM:SS"""
    h, r = divmod(time / 1000, 3600)
    m, s = divmod(r, 60)

    return f"{h}:{m}:{s}"


VoiceChannel = Union[discord.VoiceChannel, discord.StageChannel]
