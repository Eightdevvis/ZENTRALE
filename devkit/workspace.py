"""The dev root of `zentrale dev`: profiles, local release tarballs, one fake cloud.

    <root>/                       ZENTRALE_DEV_ROOT, else ~/.local/state/zentrale-dev
      cloud/state.json            the fake cloud (devkit/fake_cloud.py), shared by all profiles
      cloud/port                  its fixed port on 127.0.0.1
      cloud/serve                 which local release GET /v1/paket offers
      releases/zentrale-<N>.tar.gz   local tarballs (built from the checkout, or put there)
      profiles/<name>/            one isolated ZENTRALE home each (devkit/profiles.py)

The cloud is not a daemon: every dev command that needs it starts it for its
own lifetime — unless another dev command (e.g. an open `dev shell`) already
serves the port; then that one is used. The state is a file, so both see the
same accounts.
"""

import contextlib
import os
import secrets
import socket
import sys

from devkit import guard
from devkit.fake_cloud import FalscheCloud, state_file

CHECKOUT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
OFFLINE_CLOUD = "http://127.0.0.1:9"     # nothing listens there: "offline"
FROM_CHECKOUT = ".from-checkout"          # beside a tarball built by build_release()


class Workspace:
    def __init__(self, root=None, checkout=CHECKOUT):
        root = root or os.environ.get("ZENTRALE_DEV_ROOT") or \
            os.path.join(guard.real_home(), ".local", "state", "zentrale-dev")
        self.checkout = checkout
        self.root = guard.check_root(os.path.abspath(os.path.expanduser(root)), checkout)
        self.profiles = os.path.join(self.root, "profiles")
        self.releases = os.path.join(self.root, "releases")
        self.cloud_dir = os.path.join(self.root, "cloud")
        self.cloud_state = os.path.join(self.cloud_dir, "state.json")
        for d in (self.profiles, self.releases, self.cloud_dir):
            os.makedirs(d, exist_ok=True)

    # ── Releases ───────────────────────────────────────────────────────
    def release_path(self, version) -> str:
        return os.path.join(self.releases, f"zentrale-{version}.tar.gz")

    def release_list(self) -> list:
        return sorted(n[len("zentrale-"):-len(".tar.gz")] for n in os.listdir(self.releases)
                      if n.startswith("zentrale-") and n.endswith(".tar.gz"))

    def current_release(self) -> str:
        sys.path.append(os.path.join(self.checkout, "scripts"))
        import paket_bauen
        return paket_bauen.fassung_bestimmen(self.checkout)

    def build_release(self, version) -> str:
        """Tarball <version> from the checkout as it is now, new files not yet
        committed included (scripts/paket_bauen.py, the same builder and positive
        list as a real release). Step 6 of the plan adds an archive of
        every released tarball; then old code comes from there."""
        sys.path.append(os.path.join(self.checkout, "scripts"))
        import paket_bauen
        path, _info = paket_bauen.bauen(version, root=self.checkout, ziel_ordner=self.releases, stufe=1,
                                        include_untracked=True)
        open(path + FROM_CHECKOUT, "w").close()
        return path

    def ensure_release(self, version) -> str:
        """A tarball someone put into releases/ is used as it is; one built from
        the checkout is rebuilt, so a profile always gets today's code."""
        path = self.release_path(version)
        if os.path.exists(path) and not os.path.exists(path + FROM_CHECKOUT):
            return path
        return self.build_release(version)

    def serve(self, version):
        """From now on the fake cloud offers this release as the newest."""
        self.ensure_release(version)
        with open(os.path.join(self.cloud_dir, "serve"), "w", encoding="utf-8") as f:
            f.write(version + "\n")

    def served(self):
        """→ (version, bytes) for the fake cloud's GET /v1/paket, or None."""
        try:
            with open(os.path.join(self.cloud_dir, "serve"), encoding="utf-8") as f:
                version = f.read().strip()
            with open(self.release_path(version), "rb") as f:
                return version, f.read()
        except OSError:
            return None

    # ── The fake cloud ─────────────────────────────────────────────────
    def port(self) -> int:
        path = os.path.join(self.cloud_dir, "port")
        try:
            with open(path, encoding="utf-8") as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            pass
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{port}\n")
        return port

    def cloud_url(self) -> str:
        return f"http://127.0.0.1:{self.port()}"

    @contextlib.contextmanager
    def cloud(self):
        """The fake cloud is up for the duration (ours, or another dev command's)."""
        try:
            c = FalscheCloud(datei=self.cloud_state, port=self.port())
        except OSError:                 # port taken: another dev command serves it
            yield None
            return
        c.zustand.paket = self.served
        try:
            yield c
        finally:
            c.stopp()

    def cloud_edit(self):
        """Change the cloud's state directly (locked; a running cloud sees it next request)."""
        return state_file(self.cloud_state)

    def new_invite_code(self) -> str:
        code = "ZB-DEV0-" + "-".join(secrets.token_hex(2).upper() for _ in range(3))
        with self.cloud_edit() as z:
            z.codes.add(code)
        return code

    def account_exists(self, name) -> bool:
        with self.cloud_edit() as z:
            return name in z.konten
