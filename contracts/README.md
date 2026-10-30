# contracts/ — one folder per contract and major

Every protocol and file format between ZENTRALE pieces is a **contract** with
a major version (memory/hub/building_kit_plan.md, section 2). Its test
vectors live here, once, and every implementation reads the same file: the
core (Python, `tests/`), the phone (Dart, `mobile/test/vectors.dart`) and
later the server (`server/test/`). No copies.

    contracts/<name>/<major>/<vector files>
    contracts/<name>/<major>/translate.json     (major ≥ 2 only)

| Contract | Major | Files | Made by | Checked by |
|---|---|---|---|---|
| `account-keys` | 1 | `konto_testvektoren.json` — password → keys (Argon2id, HKDF infos `…/v1`), Fernet wrapping, emergency key | by hand from the core | `tests/test_konto_schluessel.py`, `mobile/test/krypto_test.dart`, `mitte_test.dart` |
| `cloud-sync` | 1 | `mitte_testvektoren.json` — hidden names, `inhalt.enc`, file, envelope, `geheim.enc` entry | `scripts/handy_testvektoren.py` | `mobile/test/krypto_test.dart`, `mitte_test.dart` |
| `calendar-ics` | 1 | `kalender_testvektoren.json` (read, occurrences, new events), `kalender_aendern_testvektoren.json` (edit) | `scripts/handy_testvektoren.py`, `scripts/handy_aendern_testvektoren.py` | the phone's calendar tests |
| `calendar-colours` | 1 | `calendar_colour_vectors.json` | `scripts/calendar_colour_vectors.py` | `tests/test_calendar_colours.py` (current), `mobile/test/calendar_colours_test.dart` |
| `ports` | 1 | `ports.schema.json` (JSON Schema 2020-12: port, need, offer, manifest ports, registry, piece, wire, sketch, generation), `types.json` (the type registry), `port_vectors.json` — built-in manifests, item vectors, sketches that must compile or fail with pinned errors (doc: `memory/hub/port_types.md`) | registry and schema by hand; vectors `scripts/port_vectors.py` | `tests/test_port_types.py`, `tests/test_wiring_run.py`, `mobile/test/ports_test.dart` |

The read rule for the file formats (`format` fields: unknown major →
read-only, unknown fields preserved) is `core/formats.py`, tested per format
in `tests/test_formats.py`.

## A new major (rare — rule 4 says avoid them)

No major is ever switched off (support forever, plan 2.3). A new major N of
a contract ships with:

1. a folder `contracts/<name>/<N>/` with its vectors;
2. **one translator** to the previous major in `core/translators.py`
   (`register(name, N, up, down)`: pure functions N-1 → N and N → N-1);
3. `contracts/<name>/<N>/translate.json` with
   `{"cases": [{"old": <doc in N-1>, "new": <doc in N>}]}` — `up(old) == new`
   and `down(new) == old` for every case.

Old majors are reached through the chain (`translators.translate(doc, name,
1, 3)` runs 1 → 2 → 3). `tests/test_contracts.py` fails when a major ≥ 2 has
no translator or a case does not hold; the pattern is shown on a fixture
contract with three majors in `tests/daten/contracts_fixture/example/`.

## The old-release test

`tests/test_alte_fassung.py` installs a released tarball and HEAD as two
devices of one account and lets them sync; both must converge with nothing
lost. Released tarballs are rebuilt from git once and kept in the release
archive (`dist/releases/`, never committed). `server/scripts/paket_hochladen.mjs`
refuses to publish when that test is red.
