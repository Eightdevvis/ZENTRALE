#!/usr/bin/env python3
# scripts/test_net_internet.py
#
# Tests fuer den Internet-Traffic-Channel (core/net.py + core/state.py).
#
# Was hier geprueft wird:
#   1. _is_internet(): viele URL-Varianten, inkl. Edge-Cases (IPv6, Ports,
#      User-Info, Pfade, kaputte URLs).
#   2. push_internet_log(): saubere Trennung von _logs und _internet_logs.
#   3. Integration: _log_out/_log_in/_log_err spiegeln korrekt.
#   4. maxlen-Verhalten: deque(maxlen=100) wirft Aelteste raus.
#
# Aufruf aus dem Projektroot:
#   python3 scripts/test_net_internet.py
#
# Macht keine echten HTTP-Calls - alles in-process.

import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(_ROOT, 'core'))

import net    # noqa: E402
import state  # noqa: E402

# ── Test-Framework (winzig, kein pytest noetig) ───────────────────────
_passed = 0
_failed = 0
_failures = []

def check(name, cond, detail=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  \033[32mOK\033[0m   {name}")
    else:
        _failed += 1
        _failures.append((name, detail))
        print(f"  \033[31mFAIL\033[0m {name}  {detail}")


def section(title):
    print(f"\n── {title} " + "─" * (60 - len(title)))


def clear_state():
    """Beide Log-Buffer leeren - sauberer Start pro Test-Block."""
    state._logs.clear()
    state._internet_logs.clear()


# ══════════════════════════════════════════════════════════════════════
# 1. Klassifizierung
# ══════════════════════════════════════════════════════════════════════
section("_is_internet() - Klassifizierung")

CASES = [
    # (url, expected_is_internet, beschreibung)
    # Lokal
    ("http://localhost:11434/api/chat",                False, "localhost mit Port"),
    ("http://127.0.0.1:5050/transcribe",               False, "127.0.0.1 IPv4 loopback"),
    ("http://[::1]:5051/speak",                        False, "IPv6 loopback ::1"),
    ("http://0.0.0.0:8000/x",                          False, "0.0.0.0 wildcard"),
    # LAN (RFC1918)
    ("http://192.168.50.1:5000/api/state",             False, "192.168/16 (unser PC)"),
    ("http://192.168.50.10/api/sensor/door",           False, "192.168/16 (Pi)"),
    ("http://10.0.0.5/api",                            False, "10/8 private"),
    ("http://172.16.5.1/x",                            False, "172.16/12 private (low)"),
    ("http://172.31.255.254/x",                        False, "172.16/12 private (high)"),
    # Link-local
    ("http://169.254.1.1/x",                           False, "169.254/16 link-local"),
    # mDNS
    ("http://pi.local/x",                              False, ".local mDNS"),
    ("http://ZENTRALE.local:5000/api",                 False, ".local case-insensitive"),
    # Internet (Hostnames)
    ("https://api.openai.com/v1/chat",                 True,  "public hostname"),
    ("https://github.com/foo/bar",                     True,  "public hostname"),
    ("http://ollama.com/library/qwen2.5",              True,  "public hostname"),
    # Internet (Public-IPs)
    ("http://8.8.8.8/dns",                             True,  "8.8.8.8 google DNS"),
    ("http://1.1.1.1/",                                True,  "1.1.1.1 cloudflare"),
    ("http://[2001:4860:4860::8888]/",                 True,  "IPv6 public"),
    # Random Edge-Cases
    ("https://example.com:443/path?q=1#frag",          True,  "mit query + fragment"),
    ("http://user:pass@evil.com/x",                    True,  "mit user-info"),
    # 172.32 ist KEIN private range (private ist 172.16-31)
    ("http://172.32.0.1/x",                            True,  "172.32 (NICHT private!)"),
    # 192.169 ist KEIN private range (private ist 192.168/16)
    ("http://192.169.0.1/x",                           True,  "192.169 (NICHT private!)"),
]

for url, expected, desc in CASES:
    got = net._is_internet(url)
    check(f"{desc:40s}  → {url}", got == expected,
          f"got={got} expected={expected}")

# Kaputte URLs - sollten defensiv False zurueckgeben (kein Crash)
section("_is_internet() - kaputte URLs (defensiv False)")
BROKEN = [
    "",                              # leer
    "not-a-url",                     # plain string
    "://missing-scheme",             # leeres scheme
    "http://",                       # kein host
    "http:///path-no-host",          # nur path
]
for url in BROKEN:
    got = net._is_internet(url)
    check(f"defensiv False fuer  '{url}'", got is False,
          f"got={got!r}")

# ══════════════════════════════════════════════════════════════════════
# 2. State-Channel: Isolation
# ══════════════════════════════════════════════════════════════════════
section("state.push_internet_log() - Isolation vom normalen _logs")

clear_state()
state.push_internet_log("NET → POST https://api.openai.com/v1/x")
snap = state.get_snapshot()
check("push_internet_log fuellt internet_logs",
      len(snap["internet_logs"]) == 1, f"len={len(snap['internet_logs'])}")
check("push_internet_log fuellt NICHT _logs",
      len(snap["logs"]) == 0, f"len={len(snap['logs'])}")

clear_state()
state.push_log("normaler log")
snap = state.get_snapshot()
check("push_log fuellt _logs",
      len(snap["logs"]) == 1)
check("push_log fuellt NICHT internet_logs",
      len(snap["internet_logs"]) == 0)

# ══════════════════════════════════════════════════════════════════════
# 3. Integration: _log_out / _log_in / _log_err spiegeln korrekt
# ══════════════════════════════════════════════════════════════════════
section("Integration: _log_out/_log_in/_log_err Spiegelung")

# Internet-Call: muss in BEIDEN Buffern landen
clear_state()
net._log_out("POST", "https://api.openai.com/v1/chat")
snap = state.get_snapshot()
check("Internet _log_out  →  _logs befuellt",
      len(snap["logs"]) == 1)
check("Internet _log_out  →  internet_logs befuellt",
      len(snap["internet_logs"]) == 1)

clear_state()
net._log_in(200, "https://github.com/x", 1234)
snap = state.get_snapshot()
check("Internet _log_in   →  beide Buffer befuellt",
      len(snap["logs"]) == 1 and len(snap["internet_logs"]) == 1)

clear_state()
net._log_err("https://api.openai.com/x", "timeout")
snap = state.get_snapshot()
check("Internet _log_err  →  beide Buffer befuellt",
      len(snap["logs"]) == 1 and len(snap["internet_logs"]) == 1)
check("Internet _log_err  →  FAIL-Marker drin",
      "FAIL" in snap["internet_logs"][0]["text"])

# Lokaler/LAN-Call: nur _logs, NICHT internet_logs
clear_state()
net._log_out("POST", "http://localhost:11434/api/chat")
snap = state.get_snapshot()
check("localhost _log_out →  _logs befuellt",
      len(snap["logs"]) == 1)
check("localhost _log_out →  internet_logs LEER (kein Leak)",
      len(snap["internet_logs"]) == 0)

clear_state()
net._log_in(200, "http://192.168.50.10/api/sensor/door", 12)
snap = state.get_snapshot()
check("LAN-IP _log_in     →  _logs befuellt",
      len(snap["logs"]) == 1)
check("LAN-IP _log_in     →  internet_logs LEER",
      len(snap["internet_logs"]) == 0)

clear_state()
net._log_err("http://pi.local/x", "refused")
snap = state.get_snapshot()
check("pi.local _log_err  →  internet_logs LEER",
      len(snap["internet_logs"]) == 0)

# ══════════════════════════════════════════════════════════════════════
# 4. maxlen-Verhalten
# ══════════════════════════════════════════════════════════════════════
section("deque(maxlen=100) - Aelteste fliegen raus")

clear_state()
for i in range(150):
    state.push_internet_log(f"line {i}")
snap = state.get_snapshot()
check("internet_logs auf maxlen=100 gekappt",
      len(snap["internet_logs"]) == 100,
      f"len={len(snap['internet_logs'])}")
check("Aelteste sind weg (line 0 fehlt)",
      not any(l["text"] == "line 0" for l in snap["internet_logs"]))
check("Neueste sind da (line 149 vorhanden)",
      any(l["text"] == "line 149" for l in snap["internet_logs"]))

# ══════════════════════════════════════════════════════════════════════
# 5. Snapshot-Format
# ══════════════════════════════════════════════════════════════════════
section("get_snapshot() - Format-Stabilitaet")

clear_state()
state.push_internet_log("test")
snap = state.get_snapshot()
check("snapshot enthaelt 'internet_logs' key",
      "internet_logs" in snap)
check("snapshot enthaelt 'logs' key",
      "logs" in snap)
check("internet_logs ist eine Liste",
      isinstance(snap["internet_logs"], list))
check("Eintrag hat 'text' + 'time' keys",
      "text" in snap["internet_logs"][0]
      and "time" in snap["internet_logs"][0])

# ══════════════════════════════════════════════════════════════════════
# Zusammenfassung
# ══════════════════════════════════════════════════════════════════════
print()
total = _passed + _failed
if _failed == 0:
    print(f"\033[32m✓ ALLE {total} TESTS BESTANDEN\033[0m")
    sys.exit(0)
else:
    print(f"\033[31m✗ {_failed}/{total} TESTS FEHLGESCHLAGEN\033[0m")
    for name, detail in _failures:
        print(f"  - {name}  {detail}")
    sys.exit(1)
