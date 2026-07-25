-- zentrale_theme — koppelt nvim an ZENTRALEs Tag/Nacht-Theme.
--
-- Quelle der Wahrheit ist DIESELBE Datei wie beim Terminal:
--   ~/.config/zentrale/theme  (ein Wort: auto | day | night)
--     auto  → nach Uhrzeit (05–21 Uhr hell, sonst dunkel) — identisch zu
--             tui/zentrale_tui.py resolved_theme(), monolith.html computeTheme()
--             und scripts/zentrale-term-theme.
--     day   → zentrale-paper  (Papier, pflanzliche Akzente)
--     night → zentrale-cyber  (echtes Schwarz, Neon)
--
-- Warum überhaupt etwas tun, wo nvim doch selbst den Terminal-Hintergrund
-- abfragt? nvim fragt per OSC 11 nur EINMAL beim Start. Ein SCHON LAUFENDES
-- nvim erfährt nichts davon, wenn ZENTRALE das Terminal live umfärbt — genau
-- diese Lücke schließt das hier. Zwei Wege, absichtlich redundant:
--   1. fs_event-Watcher auf der Theme-Datei → schaltet sofort um (die TUI
--      schreibt bei jedem 't' in die Datei).
--   2. Timer alle 60 s → fängt die 05/21-Rotation im auto-Modus, bei der sich
--      der DATEIINHALT gar nicht ändert (dieselbe Rolle wie der systemd-Timer
--      zentrale-term-theme.timer fürs Terminal).
-- Beides ist ein No-Op, solange der aufgelöste Modus derselbe bleibt.
--
-- Wird per ~/.config/nvim/plugin/zentrale_theme.lua eingehängt (schreibt
-- scripts/install_nvim_theme.sh) — Sashas init.lua bleibt unangetastet.

local palettes = require("zentrale_theme.palettes")
local highlights = require("zentrale_theme.highlights")

local M = {}

M.current = nil        -- aktuell angewendeter Modus ("day"/"night")
M.override = nil       -- Sitzungs-Override via :ZentraleTheme day|night
M._applying = false    -- Rekursions-Schutz (siehe apply())
M._file = nil          -- Pfad der Theme-Datei (in setup() gesetzt)

--- Pfad der Theme-Datei. ZENTRALE_THEME_FILE sticht (wie im Bash-Applier).
function M.theme_file()
  return M._file
    or vim.env.ZENTRALE_THEME_FILE
    or (vim.env.HOME .. "/.config/zentrale/theme")
end

--- Modus aus der Datei lesen und auflösen → "day" | "night".
--- Fehlende/kaputte Datei = auto (wie überall sonst im Projekt).
function M.resolve()
  if M.override then return M.override end
  local mode = "auto"
  local fh = io.open(M.theme_file(), "r")
  if fh then
    local raw = fh:read("l") or ""
    fh:close()
    raw = raw:gsub("%s", "")
    if raw == "day" or raw == "night" or raw == "auto" then mode = raw end
  end
  if mode ~= "auto" then return mode end
  local h = tonumber(os.date("%H")) or 12
  return (h >= 5 and h < 21) and "day" or "night"
end

--- Palette anwenden. Kein :colorscheme-Umweg — wir setzen die Gruppen direkt,
--- damit ein Wechsel mitten in der Sitzung ohne Neuladen sitzt.
--- @param mode string "day" | "night"
function M.load(mode)
  local p = palettes.by_mode[mode]
  if not p then return end

  -- Rekursions-Schutz: 'background' setzen lässt nvim das aktuelle Colorscheme
  -- NEU LADEN (unsere colors/*.lua rufen wieder hier rein). Ohne Flag drehte
  -- sich das im Kreis.
  if M._applying then return end
  M._applying = true

  local ok = pcall(function()
    if vim.fn.exists("syntax_on") == 1 then vim.cmd("syntax reset") end
    vim.cmd("highlight clear")
    -- 'background' VOR den Gruppen: der Wechsel setzt Highlights auf die
    -- Defaults zurück, danach gesetzte Gruppen würden sonst wieder weggewischt.
    if vim.o.background ~= p.background then vim.o.background = p.background end
    vim.g.colors_name = p.name
    -- Truecolor ist Pflicht: die Paletten sind 24-bit (Neon/Papier lassen sich
    -- mit 16 ANSI-Farben nicht darstellen).
    vim.o.termguicolors = true
    for group, attrs in pairs(highlights.build(p)) do
      vim.api.nvim_set_hl(0, group, attrs)
    end
  end)

  M._applying = false
  if ok then M.current = mode end
end

--- Datei lesen und anwenden — aber nur, wenn sich der aufgelöste Modus
--- wirklich geändert hat (sonst flackerte es bei jedem Timer-Tick).
--- @param force boolean? auch anwenden, wenn der Modus gleich bleibt
function M.refresh(force)
  local mode = M.resolve()
  if mode ~= M.current or force then M.load(mode) end
  return mode
end

--- Watcher auf die Theme-Datei (instant bei Moduswechsel in der TUI).
--- Nach JEDEM Event neu bewaffnet: schreibt jemand die Datei per rename/replace
--- statt truncate, ist der alte Watcher auf einem toten inode und stirbt still.
function M._watch()
  if M._handle then pcall(function() M._handle:stop() end) end
  local handle = vim.uv.new_fs_event()
  if not handle then return end
  M._handle = handle
  local ok = pcall(function()
    handle:start(M.theme_file(), {}, vim.schedule_wrap(function()
      M.refresh()
      vim.defer_fn(function() M._watch() end, 50)   -- neu bewaffnen
    end))
  end)
  if not ok then M._handle = nil end
end

--- Einhängen: sofort anwenden, Watcher + 60-s-Tick starten, :ZentraleTheme.
--- @param opts table? { file = "<pfad>", interval_ms = <tick> (nur Tests) }
function M.setup(opts)
  opts = opts or {}
  M._file = opts.file

  M.refresh(true)
  M._watch()

  if not M._timer then
    local timer = vim.uv.new_timer()
    if timer then
      M._timer = timer
      local every = opts.interval_ms or 60000
      timer:start(every, every, vim.schedule_wrap(function() M.refresh() end))
    end
  end

  -- ── Gegen nvims EIGENE Hintergrund-Erkennung verteidigen ────────────────
  -- nvim fragt beim Start per OSC 11 die Terminal-Hintergrundfarbe ab und setzt
  -- danach 'background'. Das passiert ERST bei/nach VimEnter — also NACH dieser
  -- Datei (plugin/ wird vorher gesourct). Und ein Wert-WECHSEL von 'background'
  -- löscht in nvim alle Highlights samt colors_name → unser Theme wäre beim
  -- Öffnen wieder weg. Zwei Netze, weil je eines allein Löcher hat:
  --   * OptionSet: greift bei jeder Änderung NACH dem Startup (die Antwort auf
  --     die OSC-11-Abfrage kann noch nach VimEnter eintrudeln) — feuert aber
  --     WÄHREND des Startups gar nicht.
  --   * VimEnter (einmal): fängt genau den Startup-Fall, den OptionSet verpasst.
  -- Ein Setzen auf denselben Wert ist in nvim ein No-Op (kein Wipe, kein Event),
  -- der Normalfall kostet also nichts.
  local aug = vim.api.nvim_create_augroup("zentrale_theme", { clear = true })
  vim.api.nvim_create_autocmd("OptionSet", {
    group = aug,
    pattern = "background",
    desc = "ZENTRALE-Theme nach fremdem 'background'-Wechsel neu auftragen",
    callback = function()
      if M._applying then return end   -- unser eigenes Setzen, kein Fremdeingriff
      M.refresh(true)
    end,
  })
  vim.api.nvim_create_autocmd("VimEnter", {
    group = aug,
    once = true,
    nested = true,
    desc = "ZENTRALE-Theme nach nvims Hintergrund-Erkennung neu auftragen",
    callback = function() M.refresh(true) end,
  })

  vim.api.nvim_create_user_command("ZentraleTheme", function(a)
    local arg = (a.args or ""):gsub("%s", "")
    if arg == "day" or arg == "night" then
      M.override = arg                -- nur diese Sitzung; die Datei bleibt heilig
      M.load(arg)
    elseif arg == "auto" or arg == "" then
      M.override = nil                -- wieder ZENTRALE folgen
      M.refresh(true)
    else
      vim.notify("ZentraleTheme: day | night | auto", vim.log.levels.WARN)
      return
    end
    vim.notify("nvim-Theme: " .. (M.current or "?")
      .. (M.override and " (Sitzungs-Override)" or " (folgt ZENTRALE)"))
  end, {
    nargs = "?",
    complete = function() return { "day", "night", "auto" } end,
    desc = "ZENTRALE-Theme neu einlesen bzw. für diese Sitzung erzwingen",
  })

  return M
end

return M
