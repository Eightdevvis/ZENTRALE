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

  -- SEPIA statt Creme (2. Runde): die erste Fläche #eee7d3 las sich noch grau.
  -- Wärme (R−B) von 27 auf 44 gezogen, ohne ins Orange zu kippen; die ganze
  -- Palette ist auf diese Fläche neu gerechnet (alle Rollen ≥4.8:1).
  bg           = "#ece0c0",  -- Sepia-Papier (deutlich vom Terminal-Creme abgesetzt)
  bg_alt       = "#e2d4ae",  -- Karton: Floats/Pmenu/Statuszeile
  bg_dim       = "#e6dab6",  -- CursorLine
  bg_sel       = "#d8dcae",  -- Visual: Blattschatten
  bg_match     = "#d5e0a5",
  fg           = "#33291c",  -- Sepia-Tinte (warmes Dunkelbraun)
  fg_dim       = "#5f563f",  -- Operatoren/Klammern (5.5:1)
  fg_faint     = "#6e6551",  -- verblasster Bleistift (4.4:1 — Kommentare)
  line_nr      = "#94886b",
  line_nr_cur  = "#44661d",
  border       = "#c4b590",

  -- Botanische Tinte, nicht Pastell: alle Akzente sind gegen die Sepia-Fläche
  -- gerechnet (≥4.8:1). Sie sind bewusst leicht wärmer als in der Creme-Runde,
  -- damit nichts kalt gegen das Papier steht.
  accent       = "#2f5f7d",  -- Wasser-Indigo → Funktionen
  keyword      = "#8a3357",  -- Beere
  string       = "#44661d",  -- Blattgrün (olivstichig)
  number       = "#934726",  -- Terracotta
  type         = "#2f5a33",  -- Tannentiefe
  constant     = "#785222",  -- Rinde
  property     = "#3a664b",  -- Salbei
  special      = "#55652b",  -- Moos
  title        = "#2f5a33",

  error        = "#972920",  -- Rost
  warn         = "#765c14",  -- Pollen
  info         = "#2f5f7d",
  hint         = "#496346",
  ok           = "#44661d",

  search_bg    = "#e3cd8c", search_fg     = "#33291c",
  cursearch_bg = "#cbdc9a", cursearch_fg  = "#33291c",
  todo_bg      = "#8a3357", todo_fg       = "#f4ecd6",

  diff_add     = "#d5e2b2",
  diff_del     = "#eccdbe",
  diff_chg     = "#ded9bb",
  diff_txt     = "#c3d798",

  status_bg    = "#d9c9a2", status_fg     = "#3d3325",
  status_nc_bg = "#e2d4ae", status_nc_fg  = "#756a52",
  pmenu_sel_bg = "#cbdc9a", pmenu_sel_fg  = "#33291c",
}

-- Kommentare kursiv (beide Paletten) — im Papier-Modus das „Notiz"-Gefühl,
-- im Cyber-Modus die Absetzung vom Code. Terminal-Support ist unkritisch:
-- kann das Terminal kein Kursiv, ignoriert es das Attribut still.
M.cyber.comment_italic = true
M.paper.comment_italic = true

M.by_mode = { night = M.cyber, day = M.paper }

return M
