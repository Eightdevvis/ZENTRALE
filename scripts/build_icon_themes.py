#!/usr/bin/env python3
"""
build_icon_themes.py — baut die beiden ZENTRALE-Icon-Themes (cyber/paper).

WARUM ABGELEITET STATT HERUNTERGELADEN: Papirus liegt hier ohnehin und bringt
seine Ordner in 78 Farbvarianten mit (folder-cyan-*, folder-brown-* …). Statt
ein fremdes Set von ~200 MB zu ziehen, erben wir Papirus und legen NUR die
Ordner in der passenden Akzentfarbe darüber — als Symlinks, ein paar KB. Das
ist genau das, was `papirus-folders` tut, aber als EIGENES Theme im
Benutzerverzeichnis: das System-Papirus bleibt unangetastet (kein sudo), und
umschalten heißt einfach Theme-Name wechseln statt Dateien umzuschreiben.

  ZENTRALE-Cyber → Papirus-Dark  + cyane Ordner   (Nacht, passt zu zentrale-cyber)
  ZENTRALE-Paper → Papirus-Light + palebrown      (Tag, passt zu zentrale-paper)

Idempotent: baut jedes Mal frisch, überschreibt nur die eigenen Ziele unter
~/.local/share/icons/. Aufruf ohne Argumente reicht; --list zeigt, was entsteht.
"""
import argparse
import os
import re
import shutil
import sys

SYSTEM_ICONS = "/usr/share/icons"
USER_ICONS = os.path.expanduser("~/.local/share/icons")

# (Ziel-Theme, Quell-Theme, Akzent, Kommentar)
VARIANTS = [
    ("ZENTRALE-Cyber", "Papirus-Dark", "cyan",
     "Papirus-Dark mit cyanen Ordnern — Nachtseite der ZENTRALE (zentrale-cyber)"),
    ("ZENTRALE-Paper", "Papirus-Light", "palebrown",
     "Papirus-Light mit warmen Ordnern — Tagseite der ZENTRALE (zentrale-paper)"),
]

SIZE_RE = re.compile(r"^(\d+)x\1(@(\d+)x)?$")


def size_dirs(theme_dir):
    """Alle Größen-Verzeichnisse eines Themes → [(name, size, scale)]."""
    out = []
    for name in sorted(os.listdir(theme_dir)):
        m = SIZE_RE.match(name)
        if m and os.path.isdir(os.path.join(theme_dir, name, "places")):
            out.append((name, int(m.group(1)), int(m.group(3) or 1)))
    return out


def build(target, source, accent, comment, dry_run=False):
    src_root = os.path.join(SYSTEM_ICONS, source)
    if not os.path.isdir(src_root):
        print("  ÜBERSPRUNGEN: %s nicht installiert" % source)
        return False

    dst_root = os.path.join(USER_ICONS, target)
    dirs, links = [], 0

    if not dry_run and os.path.isdir(dst_root):
        shutil.rmtree(dst_root)          # frisch bauen, keine Altlasten

    for dirname, size, scale in size_dirs(src_root):
        src_places = os.path.join(src_root, dirname, "places")
        names = [n for n in os.listdir(src_places)
                 if n.startswith("folder-%s" % accent) and n.endswith(".svg")]
        if not names:
            continue
        dst_places = os.path.join(dst_root, dirname, "places")
        if not dry_run:
            os.makedirs(dst_places, exist_ok=True)
        for n in names:
            # folder-cyan.svg → folder.svg ; folder-cyan-code.svg → folder-code.svg
            rest = n[len("folder-%s" % accent):]
            dst_name = "folder%s" % rest if rest.startswith("-") else "folder.svg"
            if rest == ".svg":
                dst_name = "folder.svg"
            link = os.path.join(dst_places, dst_name)
            if not dry_run:
                if os.path.islink(link) or os.path.exists(link):
                    os.unlink(link)
                os.symlink(os.path.join(src_places, n), link)
            links += 1
        dirs.append((dirname, size, scale))

    # index.theme: erbt alles Übrige vom Quell-Theme (Apps, Geräte, Mimetypes …)
    lines = ["[Icon Theme]", "Name=%s" % target, "Comment=%s" % comment,
             "Inherits=%s,Papirus,hicolor" % source,
             "Directories=%s" % ",".join("%s/places" % d for d, _, _ in dirs), ""]
    for dirname, size, scale in dirs:
        lines += ["[%s/places]" % dirname, "Size=%d" % size]
        if scale != 1:
            lines.append("Scale=%d" % scale)
        lines += ["Context=Places", "Type=Fixed", ""]

    if not dry_run:
        with open(os.path.join(dst_root, "index.theme"), "w") as fh:
            fh.write("\n".join(lines))
    print("  %s ← %s + %s: %d Symlinks in %d Größen%s"
          % (target, source, accent, links, len(dirs), " (dry-run)" if dry_run else ""))
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="nur zeigen, nichts schreiben")
    args = ap.parse_args()

    if not args.list:
        os.makedirs(USER_ICONS, exist_ok=True)
    print("Icon-Themes nach %s:" % USER_ICONS)
    ok = [build(*v, dry_run=args.list) for v in VARIANTS]
    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(main())
