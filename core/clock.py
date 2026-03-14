# core/clock.py

from datetime import datetime
from events import TIME_REACHED


_last_trigger_key = None


def check_time(target_hour, target_minute):
    """
    Non-blocking check.
    Returns TIME_REACHED only once per matching minute.
    """
    global _last_trigger_key
    now = datetime.now()
    current_key = now.strftime("%Y-%m-%d %H:%M")

    if now.hour == target_hour and now.minute == target_minute:
        if _last_trigger_key != current_key:
            _last_trigger_key = current_key
            return TIME_REACHED

    return None