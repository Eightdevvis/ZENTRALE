# tutor/ — der Sprach-Tutor (Persona-Portal).
#
# EIGENES PROJEKT, das in ZENTRALE mitwohnt. Dieser Ordner ist so geschnitten,
# dass er als Ganzes rausziehbar ist: Code, Prompts, Vokabeln und Laufzeit-Daten
# (tutor/data/) liegen hier drin, nichts davon in core/.
#
# ── Wie ZENTRALE hier reingreift ────────────────────────────────────────
# NUR über core/tutor_port.py. Kein Core-/UI-Modul importiert `tutor.*` direkt —
# der Port ist die einzige Naht, und er legt auch den sys.path-Bootstrap hin.
# Fehlt dieser Ordner komplett, läuft ZENTRALE normal weiter
# (tutor_port.present() → False).
#
# ── Was der Tutor vom „basic core" braucht (bewusst klein) ──────────────
#   ai.chat_stream(...)   – lokaler Ollama-Pfad (tutor/session.py, tutor/memory.py)
#   ai.is_available()     – Ollama-Ping für die Kapazitäts-Frage
#   ai_backends.status()  – nur tutor/memory.py, lazy + in try/except (degradiert
#                           still zu „diesen Turn nicht merken", wenn es fehlt)
#   state.push_log(...)   – nur Logging, lazy + in try/except
# Der Cloud-Pfad (tutor/openai_compat.py, tutor/cloud.py) braucht NICHTS aus
# ZENTRALE. Wächst diese Liste, wächst die Kopplung — also nicht wachsen lassen.
#
# ── Sandbox (Invariante, nie aufweichen) ────────────────────────────────
# Die Persona-Stores (tutor/data/persona_mem_<lang>.json) und Sashas Core-KI-
# Memory (data/ai_graph.json) fassen sich NIE an. Tool-Zugriffe laufen über die
# Allowlist in tutor/tools.py (_ALLOWED).
#
# ── Secrets ─────────────────────────────────────────────────────────────
# Hier liegt KEIN API-Key. Der Key-Store gehört dem Core (data/ai_config.json)
# und injiziert in os.environ; tutor/config.py hält nur Sprache/Provider/Modell.
