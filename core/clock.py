# core/clock.py

import time
from datetime import datetime
from events import TIME_REACHED


def check_time(target_hour, target_minute):
    """
    Blocks until the target time is reached,
    then returns TIME_REACHED once.
    """
    while True:
        now = datetime.now()

        if now.hour == target_hour and now.minute == target_minute:
            return TIME_REACHED

        time.sleep(1)