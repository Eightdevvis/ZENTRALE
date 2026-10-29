"""scripts/android_release_key.py — the phone app's release key in the vault:
backup/restore roundtrip, refusals, permissions, status, and what publish/bump
do first. Fake account key, temporary vault and key folder; never the network."""
import ast
import datetime
import gettext
import json
import os
import re
import stat
import sys
from types import SimpleNamespace

import pytest

import adapter_geheim
import i18n
import konto

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(ROOT, "scripts"))
import android_release_key as rk  # noqa: E402
import publish_phone_app as pub  # noqa: E402


def _keystore(password: str, name: str) -> bytes:
    """A small PKCS12 like the real one (EC instead of RSA 4096: fast)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import BestAvailableEncryption, pkcs12
    from cryptography.x509.oid import NameOID
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.datetime(2026, 10, 29, tzinfo=datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(1)
            .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=30))
            .sign(key, hashes.SHA256()))
    return pkcs12.serialize_key_and_certificates(b"zentrale", key, cert, None,
                                                 BestAvailableEncryption(password.encode()))


def _properties(password: str) -> str:
    return (f"storeFile=zentrale-release.jks\nstorePassword={password}\n"
            f"keyAlias=zentrale\nkeyPassword={password}\n")


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setenv("ZENTRALE_LANG", "en")


@pytest.fixture
def account(monkeypatch):
    from cryptography.fernet import Fernet
    k = Fernet.generate_key()
    monkeypatch.setattr(konto, "angemeldet", lambda: True)
    monkeypatch.setattr(konto, "konto_schluessel", lambda: k)
    return k


@pytest.fixture
def here(tmp_path, monkeypatch):
    """This computer's key folder (Gradle's location, via the env variable)."""
    props = tmp_path / "android" / "key.properties"
    monkeypatch.setenv(rk.PROPERTIES_ENV, str(props))
    return props


def _put_local(props, password="pw-one-1234", name="ZENTRALE"):
    props.parent.mkdir(mode=0o700, exist_ok=True)
    (props.parent / "zentrale-release.jks").write_bytes(_keystore(password, name))
    props.write_text(_properties(password))


def _vault_raw():
    with open(adapter_geheim.datei(), encoding="utf-8") as f:
        return json.load(f)["eintraege"]


def test_backup_restore_roundtrip_is_byte_identical(account, here, tmp_path):
    _put_local(here)
    jks = (here.parent / "zentrale-release.jks").read_bytes()
    assert rk.backup() == "stored"
    entry = _vault_raw()[rk.VAULT_ENTRY]
    assert entry["zu"] == "konto"
    raw = open(adapter_geheim.datei(), encoding="utf-8").read()
    assert "pw-one-1234" not in raw and "zentrale-release.jks" not in raw
    assert rk.backup() == "unchanged"

    other = tmp_path / "new-computer" / "android" / "key.properties"
    assert rk.restore(str(other)) == "restored"
    assert (other.parent / "zentrale-release.jks").read_bytes() == jks
    assert other.read_text() == here.read_text()
    assert stat.S_IMODE(os.stat(other).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(other.parent / "zentrale-release.jks").st_mode) == 0o600
    assert stat.S_IMODE(os.stat(other.parent).st_mode) == 0o700
    assert rk.restore(str(other)) == "unchanged"


def test_backup_needs_the_account(here, monkeypatch):
    _put_local(here)
    monkeypatch.setattr(konto, "angemeldet", lambda: False)
    with pytest.raises(rk.ReleaseKeyError, match="Not logged in"):
        rk.backup()
    assert rk.VAULT_ENTRY not in adapter_geheim.namen()
    assert rk.ensure() == "no_account"


def test_backup_refuses_a_different_vault_key_unless_forced(account, here, tmp_path):
    other = tmp_path / "other" / "key.properties"
    _put_local(other, "pw-two-5678", "OTHER")
    rk.backup(props_path=str(other))
    old_vault = rk.read_vault()
    _put_local(here)
    with pytest.raises(rk.ReleaseKeyError, match="DIFFERENT"):
        rk.backup()
    assert rk.same(rk.read_vault(), old_vault)
    assert rk.backup(force_replace=True) == "replaced"
    assert rk.same(rk.read_vault(), rk.read_local())
    previous = rk._decode(adapter_geheim.lesen(rk.PREVIOUS_ENTRY))
    assert rk.same(previous, old_vault)


def test_restore_refuses_a_different_local_key(account, here, tmp_path):
    other = tmp_path / "other" / "key.properties"
    _put_local(other, "pw-two-5678", "OTHER")
    rk.backup(props_path=str(other))
    _put_local(here)
    before = (here.parent / "zentrale-release.jks").read_bytes()
    with pytest.raises(rk.ReleaseKeyError, match="DIFFERENT"):
        rk.restore()
    assert (here.parent / "zentrale-release.jks").read_bytes() == before
    # a stray keystore without key.properties is never overwritten either
    (here).unlink()
    with pytest.raises(rk.ReleaseKeyError, match="incomplete"):
        rk.restore()


def test_unreadable_vault_entry_is_neither_used_nor_replaced(account, here, monkeypatch):
    _put_local(here)
    rk.backup()
    from cryptography.fernet import Fernet
    monkeypatch.setattr(konto, "konto_schluessel", lambda: Fernet.generate_key())
    with pytest.raises(rk.ReleaseKeyError, match="cannot decrypt"):
        rk.backup(force_replace=True)
    assert rk.status()["vault"] == "unreadable"


def test_status_compares_the_certificates(account, here, tmp_path):
    s = rk.status()
    assert (s["local"], s["vault"], s["same"]) == (False, False, None)
    _put_local(here)
    rk.backup()
    s = rk.status()
    assert s["local"] and s["vault"] and s["same"] is True
    assert re.fullmatch(r"([0-9A-F]{2}:){31}[0-9A-F]{2}", s["local_sha256"])
    assert s["local_sha256"] == s["vault_sha256"]


def test_ensure_restores_backs_up_and_stops_on_conflict(account, here, tmp_path):
    assert rk.ensure() == "missing"
    _put_local(here)
    assert rk.ensure() == "backed_up"
    assert rk.ensure() == "ok"
    for f in here.parent.iterdir():
        f.unlink()
    assert rk.ensure() == "restored"
    assert rk.ensure() == "ok"
    _put_local(here, "pw-two-5678", "OTHER")
    with pytest.raises(rk.ReleaseKeyError, match="DIFFERENT"):
        rk.ensure()


def test_bump_and_publish_ensure_the_key_first(account, here, tmp_path):
    other = tmp_path / "other" / "key.properties"
    _put_local(other, "pw-two-5678", "OTHER")
    rk.backup(props_path=str(other))
    _put_local(here)
    pubspec = tmp_path / "pubspec.yaml"
    pubspec.write_text("name: zen_mobile\nversion: 0.1.0+3\n")
    with pytest.raises(pub.PublishError, match="DIFFERENT"):
        pub.cmd_bump(SimpleNamespace(name=None, offline=True), None, str(pubspec))
    assert "0.1.0+3" in pubspec.read_text()
    with pytest.raises(pub.PublishError, match="DIFFERENT"):
        pub.cmd_publish(SimpleNamespace(apk=None, build=False, notes="", dry_run=True), None, str(pubspec))


def test_key_commands_never_print_secrets(account, here, tmp_path, capsys):
    _put_local(here)
    assert pub.main(["key", "backup"]) == 0
    target = tmp_path / "compare"
    assert pub.main(["key", "restore", "--to", str(target)]) == 0
    assert (target / "zentrale-release.jks").read_bytes() == (here.parent / "zentrale-release.jks").read_bytes()
    assert pub.main(["key", "status"]) == 0
    out = capsys.readouterr()
    assert "pw-one-1234" not in out.out + out.err
    assert "same key: yes" in out.out


def test_every_message_has_a_german_text():
    tree = ast.parse(open(rk.__file__, encoding="utf-8").read())
    msgids = [n.args[0].value for n in ast.walk(tree)
              if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "_"]
    assert len(msgids) > 10
    with open(os.path.join(i18n.LOCALE_DIR, "de", "LC_MESSAGES", "zentrale.mo"), "rb") as f:
        de = gettext.GNUTranslations(f)
    for m in msgids:
        assert de.gettext(m) != m, f"no German text for {m!r}"
        assert sorted(re.findall(r"\{(\w+)\}", de.gettext(m))) == sorted(re.findall(r"\{(\w+)\}", m))
