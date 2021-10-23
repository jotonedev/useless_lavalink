def format_time(time: int) -> str:
    """ Formats the given time into HH:MM:SS """
    h, r = divmod(time / 1000, 3600)
    m, s = divmod(r, 60)

    return f"{h}:{m}:{s}"
