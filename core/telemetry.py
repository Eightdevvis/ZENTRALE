# core/telemetry.py
#
# Baut den PC-Telemetrie-Snapshot fuer das Dashboard (/api/telemetry).
# Der PC ist die Maschine, auf der Backend + Ollama (RTX 4070) laufen -
# darum ist hier VRAM die wichtigste Zahl (genau das ist beim Modell-Wechsel
# der Crash-Ausloeser gewesen, siehe memory/ki/ki_system.md).
#
# Quelle: core/host_metrics.py (dependency-frei, /proc + /sys + nvidia-smi).
# Die Pi-Telemetrie kommt NICHT von hier, sondern wird vom Pi an
# /api/telemetry/pi gePOSTet und in state.py gehalten (siehe ui/app.py).
#
# Shape (so wie das Frontend-Design die Meter erwartet: je Metrik ein .v):
#   { "cpu":  {"v": %},
#     "gpu":  {"v": %},
#     "vram": {"v": %, "used": GB, "total": GB},
#     "temp": {"v": °C},
#     "ram":  {"v": %, "used": GB, "total": GB} }
# Fehlt eine Quelle, ist .v = None → das Frontend zeigt ehrlich '–'.

import socket
import host_metrics  # liegt in core/, wird ueber sys.path gefunden (siehe ui/app.py)


def pc_snapshot() -> dict:
    """Aktuelle PC-Telemetrie. CPU/GPU/VRAM/Temp/RAM, jeweils None-sicher.

    `host` = Hostname DIESER Maschine (= Host des Backends). Wichtig, weil die
    Fronten nur HTTP-Clients sind: die TUI auf dem Pi zeigt diese Werte, sie
    stammen aber vom Backend-Host (i.d.R. der PC). Ohne das Feld beschriftete
    die TUI sie frueher hart als "LAP" — falsch, sobald das Backend woanders
    laeuft. Die Front leitet aus `host` ihr Kuerzel ab (PC/LAP/PI)."""
    ram = host_metrics.mem_percent()       # (pct, used_gb, total_gb) | None
    gpu = host_metrics.gpu_nvidia()         # dict | None

    return {
        "host": socket.gethostname(),
        "cpu":  {"v": host_metrics.cpu_percent()},
        "gpu":  {"v": gpu["util"] if gpu else None},
        "vram": {
            "v":     gpu["vram_pct"] if gpu else None,
            "used":  gpu["vram_used_gb"] if gpu else None,
            "total": gpu["vram_total_gb"] if gpu else None,
        },
        "temp": {"v": host_metrics.temp_c()},
        "ram":  {
            "v":     ram[0] if ram else None,
            "used":  ram[1] if ram else None,
            "total": ram[2] if ram else None,
        },
    }
