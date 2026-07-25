-- :checkhealth zentrale_theme — Diagnose der Theme-Kopplung.
-- Zeigt, WAS gerade gilt und WORAN es hängt, wenn die Farben nicht stimmen.

local M = {}

function M.check()
  local h = vim.health
  local t = require("zentrale_theme")
  h.start("ZENTRALE-Theme-Kopplung")

  local file = t.theme_file()
  local fh = io.open(file, "r")
  if fh then
    local raw = (fh:read("l") or ""):gsub("%s", "")
    fh:close()
    h.ok(("Theme-Datei %s → %q"):format(file, raw))
  else
    h.warn(("Theme-Datei %s fehlt — es gilt auto (nach Uhrzeit)"):format(file),
      { "Anlegen: printf 'auto\\n' > " .. file .. "  (oder die TUI einmal starten)" })
  end

  h.info(("aufgelöst: %s → colorscheme %s, background=%s"):format(
    tostring(t.current), tostring(vim.g.colors_name), vim.o.background))
  if t.override then
    h.warn(("Sitzungs-Override aktiv: %s — folgt ZENTRALE gerade NICHT"):format(t.override),
      { ":ZentraleTheme auto hebt den Override auf" })
  end

  -- Die zwei Mechanismen, die das Live-Umschalten tragen
  if t._handle then h.ok("fs_event-Watcher auf der Theme-Datei läuft (instant)")
  else h.warn("kein fs_event-Watcher — Umschalten kommt nur über den 60-s-Tick") end
  if t._timer then h.ok("Tick läuft (fängt die 05/21-Rotation im auto-Modus)")
  else h.error("kein Tick — im auto-Modus bleibt die 05/21-Rotation liegen") end

  -- Farbtiefe: der häufigste Grund für "das Theme sieht falsch aus"
  if not vim.o.termguicolors then
    h.error("termguicolors ist aus — die 24-bit-Paletten können nicht wirken",
      { ":set termguicolors  (setzt zentrale_theme normalerweise selbst)" })
  else
    local tc = t.truecolor_ok()
    if tc == false then
      h.error("tmux leitet keine 24-bit-Farben durch → Farben werden auf die "
        .. "256er-Palette gerundet und wirken flau (Papier-Creme #eee7d3 wird "
        .. "zu Grau #e4e4e4, Blattgrün zu #444444)", {
        'in ~/.tmux.conf:  set -as terminal-features ",*:RGB"',
        "danach tmux neu attachen — die Option greift erst beim Attach",
      })
    elseif tc == true then
      h.ok("tmux leitet 24-bit-Farben durch (RGB)")
    else
      h.info("kein tmux — Farbtiefe hängt direkt am Terminal")
    end
  end
end

return M
