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
#   kern.fahrzeug/fahren  – die EINE Straße zu allen Modellen (lokal + Cloud),
#   providers             – die eine Anbieter-Liste; beides NUR über
#                           tutor/anbieter.py (seit 2026-10-08, vorher eigene
#                           Liste + eigene Cloud-Schleifen hier im Tutor)
#   ai_backends           – Ollama-Ping und status() (Kapazitäts-Frage)
#   state.push_log(...)   – nur Logging, lazy + in try/except
# Erlaubt ist genau das, was in memory/system/bauplan_kern.md unter „Türen"
# steht (der Test tests/test_kern_bauplan.py wacht darüber).

# ── Sprache = Ordner (tutor/langs/<code>/) ──────────────────────────────
# Der Tutor ist ein FRAMEWORK, kein Chinesisch-Tutor. Alles, was eine Sprache
# ausmacht, liegt in ihrem Paket: Prompt (in der ZIELSPRACHE), Tool-Beschriftung,
# Register-Leiter, Landes-Seeds. tools.py/session.py sind sprach-NEUTRAL und
# lösen pro Aufruf über die aktive Sprache auf (session.active_lang()).
# Eine Sprache dazubauen = einen Ordner anlegen. Siehe tutor/langs/__init__.py.
#
# ── Sandbox (Invariante, nie aufweichen) ────────────────────────────────
# Die Persona-Stores (tutor/data/<lang>/persona_mem.json) und Sashas Core-KI-
# Memory (data/ai_graph.json) fassen sich NIE an. Tool-Zugriffe laufen über die
# Allowlist in tutor/tools.py (_ALLOWED).
#
# ── Secrets ─────────────────────────────────────────────────────────────
# Hier liegt KEIN API-Key. Der Key-Store gehört dem Core (data/ai_config.json)
# und injiziert in os.environ; tutor/config.py hält nur Provider/Modell/Regler.
