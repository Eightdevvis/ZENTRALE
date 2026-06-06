# core/host_metrics.py
#
# Dependency-freie Host-Telemetrie. Liest direkt aus /proc, /sys und (fuer
# die GPU) nvidia-smi. Bewusst OHNE psutil o.ae. - kein pip install noetig,
# voll offline, und jede Zeile ist nachlesbar (Kontroll-Achse der ZENTRALE).
#
# Wird von ZWEI Maschinen benutzt:
#   - PC : core/telemetry.py baut daraus den /api/telemetry-Snapshot
#          (CPU, GPU-Last, VRAM, Temp, RAM).
#   - Pi : scripts/pi_sensor_bridge.py pollt CPU/Temp/RAM/SD und POSTet
#          sie an /api/telemetry/pi.
#
# Alle Funktionen sind defensiv: wenn eine Quelle fehlt (z.B. keine
# nvidia-GPU auf dem Pi, kein Thermal-Zone), geben sie None zurueck statt
# zu crashen. Das Frontend zeigt dann ehrlich '–' statt eines Fake-Werts.

import os
import subprocess

# ── CPU-Auslastung ─────────────────────────────────────────────────────
# /proc/stat erste Zeile: "cpu user nice system idle iowait irq softirq ..."
# Auslastung ist KEIN Momentanwert, sondern ein Delta zwischen zwei
# Messungen. Wir merken uns die letzte Messung modulweit und rechnen die
# Differenz zum letzten Aufruf. Beim allerersten Aufruf gibt es noch kein
# Delta → None (das Frontend zeigt eine Runde '–', danach echte Werte).
_last_cpu = {}


def cpu_percent():
    """Gesamte CPU-Auslastung in % seit dem letzten Aufruf (oder None)."""
    try:
        with open("/proc/stat", "r") as f:
            parts = f.readline().split()[1:]   # ohne das fuehrende "cpu"
        vals = [int(x) for x in parts]
        idle = vals[3] + (vals[4] if len(vals) > 4 else 0)   # idle + iowait
        total = sum(vals)
        prev = _last_cpu.get("t")
        _last_cpu["t"] = (total, idle)
        if prev is None:
            return None
        dt, di = total - prev[0], idle - prev[1]
        if dt <= 0:
            return None
        return round((1 - di / dt) * 100, 1)
    except Exception:
        return None


# ── RAM ────────────────────────────────────────────────────────────────
def mem_percent():
    """
    RAM-Belegung. Gibt (pct, used_gb, total_gb) zurueck, oder None.
    Belegt = MemTotal - MemAvailable (MemAvailable ist die ehrliche Zahl:
    frei + Cache der freigegeben werden kann).
    """
    try:
        info = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                k, _, v = line.partition(":")
                info[k] = int(v.split()[0])   # in kB
        total = info["MemTotal"]
        avail = info.get("MemAvailable", info.get("MemFree", 0))
        used = total - avail
        return (round(used / total * 100, 1), round(used / 1048576, 1), round(total / 1048576, 1))
    except Exception:
        return None


# ── Temperatur ───────────────────────────────────────────────────────────
def temp_c():
    """
    CPU/SoC-Temperatur in °C aus /sys/class/thermal. Bevorzugt eine Zone
    deren Typ nach CPU/Package/SoC aussieht (x86_pkg_temp am PC,
    cpu-thermal am Pi), sonst die erste verfuegbare. None wenn keine da.
    """
    base = "/sys/class/thermal"
    try:
        zones = [z for z in os.listdir(base) if z.startswith("thermal_zone")]
    except Exception:
        return None
    pref = ("pkg", "cpu", "soc", "core")

    def read(zone):
        try:
            with open(os.path.join(base, zone, "temp")) as f:
                return int(f.read().strip()) / 1000.0
        except Exception:
            return None

    # erst eine "passende" Zone suchen
    for z in zones:
        try:
            with open(os.path.join(base, z, "type")) as f:
                typ = f.read().strip().lower()
        except Exception:
            typ = ""
        if any(p in typ for p in pref):
            t = read(z)
            if t is not None:
                return round(t, 1)
    # Fallback: irgendeine Zone
    for z in sorted(zones):
        t = read(z)
        if t is not None:
            return round(t, 1)
    return None


# ── Disk ───────────────────────────────────────────────────────────────
def disk_percent(path="/"):
    """
    Belegung des Dateisystems unter `path`. Gibt (pct, used_gb, total_gb)
    zurueck, oder None. Auf dem Pi ist '/' die SD-Karte (laeuft voll/altert
    → die relevante Disk-Zahl).
    """
    try:
        st = os.statvfs(path)
        total = st.f_blocks * st.f_frsize
        free = st.f_bfree * st.f_frsize
        used = total - free
        if total <= 0:
            return None
        return (round(used / total * 100, 1), round(used / 1e9, 1), round(total / 1e9, 1))
    except Exception:
        return None


# ── GPU (nvidia-smi) ─────────────────────────────────────────────────────
def gpu_nvidia():
    """
    GPU-Auslastung + VRAM via nvidia-smi (nur am PC mit nvidia-GPU).
    Gibt ein Dict zurueck oder None (kein nvidia-smi / kein GPU / Timeout):
      { "util": %, "vram_pct": %, "vram_used_gb": x, "vram_total_gb": y, "temp": °C }
    """
    try:
        out = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=2,
        )
        if out.returncode != 0:
            return None
        # erste GPU-Zeile reicht (Single-GPU-System)
        line = out.stdout.strip().splitlines()[0]
        util, used_mb, total_mb, temp = [x.strip() for x in line.split(",")]
        used_mb, total_mb = float(used_mb), float(total_mb)
        return {
            "util": float(util),
            "vram_pct": round(used_mb / total_mb * 100, 1) if total_mb else None,
            "vram_used_gb": round(used_mb / 1024, 1),
            "vram_total_gb": round(total_mb / 1024, 1),
            "temp": float(temp),
        }
    except Exception:
        return None
