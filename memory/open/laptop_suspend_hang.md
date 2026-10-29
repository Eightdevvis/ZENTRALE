# Laptop does not wake up after closing the lid

**Stand 2026-10-30:** Open, test running. **Waits for Sasha** (use the laptop
normally for a few days, then ask for the evaluation).

Laptop: MacBook Air 7,2 (`0RAMMachine`), Linux Mint 22.3, kernel
6.14.0-35-generic, i3, sleep mode `deep`.

## Symptom (Sasha, 29.10.)

Close the lid while it is running, open it later: screen stays black for
minutes, keys do nothing, but the laptop is clearly on — "it thinks it is
still closed". Only holding the power button (several times) turns it off,
then a full, slow reboot.

## Evidence

- The journal always ends at `PM: suspend entry (deep)`; the next boot reports
  an uncleanly shut down journal. No kernel panic in pstore, no driver error
  before the hang.
- In every good suspend the line `Filesystems sync: …` follows the entry; in
  the hung ones it is missing → points at storage (SSD) or the freeze stage.
- Hangs: 30.09. 09:07, 13.10. 09:10, then **26.10. 13:03, 27.10. 16:01,
  27.10. 18:59** — up from ~2 in 118 suspends to ~3 in 13.
- No kernel or package update since 18.10. The ZENTRALE timers from 24.10.
  (`zentrale-abgleich`, `zentrale-kalender-sync`) do not wake the system and the
  hangs started before them.
- Memory is chronically tight (zram 2/2 GB full, 1.3 GB in the swap file,
  earlyoom ~17–27 % available), but good suspends happen under the same load.

## Ruled out along the way (18.–22.10.)

Sasha says these are not the problem; kept here only so nobody re-investigates:
battery running empty (UPower hybrid sleep at 2 %, 7×), power key at the
lightdm greeter (logind default `poweroff`, xfce4-power-manager's inhibitor
does not apply there, 5×), possible loose charger contact on 16.10.

## Suspects — our own tweaks (Sasha: "wir haben was kaputt gemacht")

| Date | Change | Runs at suspend? |
|---|---|---|
| 11.06. | zram-tools, earlyoom | indirectly |
| **12.06.** | **TLP 1.6.1** (SATA `med_power_with_dipm`, runtime PM, USB autosuspend) | **yes, own sleep hook** |
| 28.07. | XFCE diet (`gui-diet`) | no |
| 02.08. | i3 instead of xfwm4 | no |
| 05.08. | lid via logind (`/etc/systemd/logind.conf.d/10-deckel.conf`) | triggers it |

Other suspect without our involvement: Broadcom `wl` Wi-Fi driver (known for
suspend hangs on MacBooks). Sasha does **not** want scripts (no sleep hook to
unload `wl`).

## Test running since 30.10.

- TLP off: `/etc/tlp.d/99-suspend-test-off.conf` (`TLP_ENABLE=0`),
  `tlp.service` disabled. Needs one reboot to reset the SSD link policy.
- **Check after the reboot:** if the SSD link policy is still
  `med_power_with_dipm`, the Ubuntu kernel sets it by itself, not TLP.
- **Evaluate:** count `PM: suspend entry` without a following `suspend exit`
  since the reboot. ~15 clean wake-ups = TLP is the cause → find the one TLP
  setting and turn only that off. Still hangs → TLP back on, next suspect
  (zram/earlyoom, then `s2idle` instead of `deep` as a test).
- **Undo:** delete the drop-in file, enable `tlp.service` again.
