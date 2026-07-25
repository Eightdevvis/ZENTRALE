-- zentrale_theme.palettes — die zwei Paletten der nvim-Kopplung.
--
-- Beide Paletten haben EXAKT dieselben Schlüssel (semantische Rollen, nicht
-- Farbnamen) — highlights.lua mappt diese Rollen auf die nvim-Gruppen. Wer eine
-- Farbe ändern will, ändert sie nur hier; die Gruppen-Zuordnung bleibt gleich.
--
-- Bewusst KEIN Erben der Terminal-Palette: die nvim-Fläche soll sich sichtbar
-- vom umgebenden Terminal (Solarized) abheben — man soll erkennen, dass man IM
-- Editor ist. day-Papier #eee7d3 ist merklich tiefer als Terminal-Creme
-- #fdf6e3, night-Schwarz #000000 klar härter als Terminal-Petrol #002b36.

local M = {}

-- ── night: "cyber" — echtes Schwarz, Neon-Palette ─────────────────────────
-- Grundgedanke: Fläche völlig schwarz (kein Grau-Schleier), darauf wenige
-- gesättigte Neon-Töne. Kein bold auf den Neons (das kippt sonst ins Grelle);
-- bold bleibt Titeln/Statuszeile/MatchParen vorbehalten.
M.cyber = {
  name = "zentrale-cyber",
  background = "dark",

  bg           = "#000000",  -- echt schwarz, keine Aufhellung
  bg_alt       = "#05080a",  -- Floats/Pmenu/Statuszeile: gerade eben abgesetzt
  bg_dim       = "#070d10",  -- CursorLine
  bg_sel       = "#16333d",  -- Visual: Teal-Schatten
  bg_match     = "#003b46",  -- MatchParen
  fg           = "#ccf7ff",  -- Text: Weiß mit Cyan-Stich
  fg_dim       = "#7fb3bf",  -- UI-Text, Operatoren, Klammern
  fg_faint     = "#577c8a",  -- Kommentare (4.7:1 auf Schwarz — recessed, aber lesbar)
  line_nr      = "#31525f",
  line_nr_cur  = "#00f0ff",
  border       = "#123039",

  accent       = "#00f0ff",  -- Neon-Cyan  → Funktionen, Cursorzeile, Links
  keyword      = "#ff2bd6",  -- Neon-Magenta
  string       = "#00ff9c",  -- Neon-Spring
  number       = "#ff7a18",  -- Neon-Orange
  type         = "#ffe93d",  -- Neon-Gelb
  constant     = "#a56bff",  -- Neon-Violett
  property     = "#38bdff",  -- Neon-Azur
  special      = "#9dff1f",  -- Neon-Lime (Escapes, SpecialChar)
  title        = "#ff2bd6",

  error        = "#ff2f5e",
  warn         = "#ffe93d",
  info         = "#38bdff",
  hint         = "#a56bff",
  ok           = "#00ff9c",

  search_bg    = "#ff2bd6", search_fg     = "#000000",
  cursearch_bg = "#9dff1f", cursearch_fg  = "#000000",
  todo_bg      = "#ff2bd6", todo_fg       = "#000000",

  diff_add     = "#06251c",
  diff_del     = "#2a0812",
  diff_chg     = "#0b1c2e",
  diff_txt     = "#0d3a2c",

  status_bg    = "#08131a", status_fg     = "#00f0ff",
  status_nc_bg = "#05080a", status_nc_fg  = "#4b6a76",
  pmenu_sel_bg = "#10303a", pmenu_sel_fg  = "#00f0ff",
}

-- ── day: "paper" — Papier mit pflanzlicher Organik ────────────────────────
-- Grundgedanke: warmes, leicht vergilbtes Blatt; Akzente aus dem Garten
-- (Blattgrün, Tannentiefe, Rinde, Terracotta, Beere, Wasser, Pollen).
-- Kommentare wie verblasster Bleistift, kursiv.
M.paper = {
  name = "zentrale-paper",
  background = "light",

  bg           = "#eee7d3",  -- Papier (tiefer als Terminal-Creme → Blattkante sichtbar)
  bg_alt       = "#e5ddc4",  -- Karton: Floats/Pmenu/Statuszeile
  bg_dim       = "#e7dfc8",  -- CursorLine
  bg_sel       = "#d9e2c0",  -- Visual: Blattschatten
  bg_match     = "#cfe3ad",
  fg           = "#2e2b21",  -- Tinte (warmes Schwarz)
  fg_dim       = "#5f5b49",  -- Operatoren/Klammern (5.5:1)
  fg_faint     = "#706b59",  -- verblasster Bleistift (4.3:1 — Kommentare)
  line_nr      = "#968f7a",
  line_nr_cur  = "#3f6b27",
  border       = "#c9c0a4",

  -- Die Akzente sind gegenüber dem ersten Wurf ABGEDUNKELT (Farbton identisch):
  -- auf Papier lagen Blattgrün/Pollen/Moos bei 2.9–4.1:1, also unter der
  -- Lesbarkeitsschwelle. Jetzt alle ≥4.8:1 — botanische Tinte statt Pastell.
  accent       = "#326384",  -- Wasser-Indigo → Funktionen
  keyword      = "#8c3b60",  -- Beere
  string       = "#3f6b27",  -- Blattgrün
  number       = "#9a4a28",  -- Terracotta
  type         = "#2f5d3a",  -- Tannentiefe
  constant     = "#7a5733",  -- Rinde
  property     = "#3c6a4e",  -- Salbei
  special      = "#58692d",  -- Moos
  title        = "#2f5d3a",

  error        = "#9c2b22",  -- Rost
  warn         = "#7b6015",  -- Pollen
  info         = "#326384",
  hint         = "#4d6849",
  ok           = "#3f6b27",

  search_bg    = "#e8d79a", search_fg     = "#2e2b21",
  cursearch_bg = "#cfe3ad", cursearch_fg  = "#2e2b21",
  todo_bg      = "#8c3b60", todo_fg       = "#f7f2e2",

  diff_add     = "#d9e8c4",
  diff_del     = "#f0d6cd",
  diff_chg     = "#e2e2cf",
  diff_txt     = "#c8ddaa",

  status_bg    = "#ded5b8", status_fg     = "#3b3729",
  status_nc_bg = "#e5ddc4", status_nc_fg  = "#7a7460",
  pmenu_sel_bg = "#cfe3ad", pmenu_sel_fg  = "#2e2b21",
}

-- Kommentare kursiv (beide Paletten) — im Papier-Modus das „Notiz"-Gefühl,
-- im Cyber-Modus die Absetzung vom Code. Terminal-Support ist unkritisch:
-- kann das Terminal kein Kursiv, ignoriert es das Attribut still.
M.cyber.comment_italic = true
M.paper.comment_italic = true

M.by_mode = { night = M.cyber, day = M.paper }

return M
