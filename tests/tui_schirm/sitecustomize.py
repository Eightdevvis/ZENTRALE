# Friert für den Bildschirm-Vergleich die Uhr ein (nur wenn ZTUI_EINGEFROREN gesetzt).
# Wanduhr (time.time, localtime, strftime, date.today, datetime.now) steht fest,
# time.monotonic auch — aber erst NACHDEM threading/queue/subprocess/socket ihre
# echte Uhr gebunden haben, sonst warten deren Timeouts ewig.
import os

if os.environ.get("ZTUI_EINGEFROREN"):
    import threading, queue, subprocess, socket, selectors, http.client, urllib.request  # noqa
    import time as _t
    import datetime as _dt

    T0 = float(os.environ["ZTUI_EINGEFROREN"])
    _lt, _gm, _sf = _t.localtime, _t.gmtime, _t.strftime
    _t.time = lambda: T0
    _t.time_ns = lambda: int(T0 * 1e9)
    _t.monotonic = lambda: 100000.0
    _t.monotonic_ns = lambda: int(100000.0 * 1e9)
    _t.perf_counter = lambda: 100000.0

    def localtime(s=None):
        return _lt(T0 if s is None else s)

    def gmtime(s=None):
        return _gm(T0 if s is None else s)

    def strftime(fmt, tup=None):
        return _sf(fmt, localtime() if tup is None else tup)

    _t.localtime, _t.gmtime, _t.strftime = localtime, gmtime, strftime

    class date(_dt.date):
        @classmethod
        def today(cls):
            return cls.fromtimestamp(T0)

    class datetime(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(T0, tz)

        @classmethod
        def today(cls):
            return cls.fromtimestamp(T0)

    _dt.date = date
    _dt.datetime = datetime
