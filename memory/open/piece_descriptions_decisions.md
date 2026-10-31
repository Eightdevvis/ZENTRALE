# Piece descriptions — decisions for Sasha

**Stand 2026-10-31:** Open, **waits for Sasha**. Plan:
[piece_descriptions_plan.md](../hub/piece_descriptions_plan.md) (describe any
program or device as a piece; Schematix inventory on `i`). Nothing is built;
step 1 (format contract) can start once these are answered or the proposals
accepted.

| # | Question | Proposal |
|---|---|---|
| 1 | Which key gets the versions panel when `i` becomes the inventory? | `n` ("node"), plain letter, free today |
| 2 | Does `+` stay as a second key for the inventory? | yes, same modal |
| 3 | Name/icon edits per kind or per single piece? | per kind by default; name/icon also per piece; ports only per kind |
| 4 | Sync the derived descriptions too, or only Sasha's edits? | sync both, so a second node never describes (or pays the KI) again |
| 5 | Should downloaded files in `~/Downloads` appear in the inventory? | yes, executables and AppImages only, marked "file" |
| 6 | Same program from dpkg and Flatpak: one description or two? | two, linkable later by hand (`source.keys`) |
| 7 | Ask before each KI describe, or once per provider? | once per provider ("always" choice), the card always shows what leaves |
| 8 | Is the KI describer preinstalled? | no, a store package; without it "?" stays |
| 9 | Where do foreign programs land when dropped: documented or planned? | documented if installed on that node, planned otherwise |
| 10 | Name of the KI describer package? | `piece-describer-ai` |
