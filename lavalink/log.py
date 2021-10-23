import logging

log = logging.getLogger("useless_bot.lavalink")
socket_log = logging.getLogger("useless_bot.lavalink.socket")
socket_log.setLevel(logging.INFO)

ws_discord_log = logging.getLogger("useless_bot.lavalink.WS.discord")
ws_ll_log = logging.getLogger("useless_bot.lavalink.WS.LLServer")
ws_rll_log = logging.getLogger("useless_bot.lavalink.RLL")


def set_logging_level(level=logging.INFO):
    log.setLevel(level)
    ws_discord_log.setLevel(level)
    ws_ll_log.setLevel(level)
    ws_rll_log.setLevel(level)
