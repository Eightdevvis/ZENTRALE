# Mini-PC: networks without the laptop

**Stand 2026-10-30:** Open. **Waits for Sasha** (credentials, home Wi-Fi).
Found 29.10. by Sasha: the mini only knows the Wi-Fi „Hotspot", which runs via
the laptop that is being retired.

- **eduroam on the mini:** the university CAT installer is copied to
  `~/Downloads/eduroam-uds.py` on the mini (from the laptop's home). Needs
  Sasha's university login, so Sasha runs it.
- **eduroam on the tablet** (Tab S7 FE): needed so Tailscale has internet at
  university.
- **Home Wi-Fi:** the mini needs a network that does not depend on the laptop
  (router or phone hotspot).
- **Optional, not built: own hotspot from the mini.** The Intel CNVi card
  allows `managed` + `AP` at the same time on one channel (`iw list`). Needs a
  second virtual interface (`ap0`) that survives reboots, plus a NetworkManager
  hotspot on it — and a firewall rule for VNC in zone `nm-shared`. Test
  together with Sasha; Tailscale covers the need until then.
