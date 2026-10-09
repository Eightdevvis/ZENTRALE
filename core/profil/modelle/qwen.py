# core/profil/modelle/qwen.py
#
# Das Profil für qwen über die Cloud (qwen-plus & Co., DashScope, OpenAI-
# kompatibel). Gebaut und gemessen in der Nacht 09./10.10.2026 mit dem
# Prüfstand (memory/ki/modell_profile.md: was half, was nicht, Zahlen).
#
# Jede Strategie steht hier mit ihrem Grund. Was nicht half, steht NICHT
# hier, sondern in der Doku — sonst zahlt qwen für Text, der nichts bringt.

import re as _re

import nutzer_angaben

NAME = "qwen"
