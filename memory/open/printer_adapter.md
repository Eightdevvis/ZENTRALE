# Printer: pluggable adapters, first device

**Stand 2026-10-29:** Open, **waits for Sasha** (printer network, go for the
blueprint). Agreed in chat 25.10.2026; nothing built yet. Leitbild scene
„Der Drucker gehört ihr" (`memory/leitbild.md`): HP printer/scanner as a tool
of the AI, local over IPP / eSCL, no HP cloud.

**Architecture Sasha agreed on:**

- **Core = broker only.** AI asks → core → adapter does it → core → answer
  back to AI. The core knows who docked, which interface they fulfil, and
  who may use it. It knows nothing about printers.
- **Interface** per device kind, fixed in the core, e.g. `print`: print
  document, printer status, list jobs. Every printer adapter fulfils exactly
  that, so apps and AI tools are written once, never per printer.
- **Adapter** docks onto the core (not built into it), brings its own
  manifest and connection schema. Today's `core/adapter_anschluss.schema.json`
  only allows `kalender-vdirsyncer` and `ki-anbieter`, too narrow
  (`core/adapter.py`, `memory/hub/adapter.md`). Core keeps only a generic
  frame; new adapter kinds plug in with little code (later the Schmied
  builds missing ones).
- **App „Printer"** ships a default adapter; a different printer swaps only
  the adapter.
- **AI tool** is its own store package, not given to the AI automatically.
  If adapter + AI are installed, the hub asks „download AI printer tool?".
  Don't build the store dialog now, just keep the packages separate.

**Shared frame (2026-10-31):** the screen guide needs the same device-adapter
frame and will be its first user; the printer comes second
([../ki/screen_guide_plan.md](../ki/screen_guide_plan.md), "Where each piece lives").

**Next steps:**

1. Rewrite `memory/hub/adapter.md` as blueprint (broker, interfaces,
   pluggable adapters, separate AI-tool packages).
2. Build: `print` interface, IPP adapter, AI tool behind `core/erlaubnis.py`,
   tested against a fake printer. Scanner (eSCL) later as second interface.

**Printer network (Sasha):** No home WLAN, only phone hotspot. The printer
today only shows its own Wi-Fi Direct (laptop then has no internet). Try:
laptop into printer WLAN, open its web page (HP usually `192.168.223.1`),
Network → Wireless setup wizard, join the hotspot. If the model can't join
other networks: LAN cable at the desktop PC. Plugging a cable into the laptop
only on demand doesn't fit the Leitbild (ZENTRALE prints on its own). Model
still unknown.
