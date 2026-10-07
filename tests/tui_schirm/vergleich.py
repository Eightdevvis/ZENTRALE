"""Vergleicht zwei Mitschnitt-Ordner Zelle für Zelle (Zeichen + sichtbare Farbe).

Die Vordergrundfarbe eines Leerzeichens ist unsichtbar (außer bei reverse) und
hängt bei curses davon ab, was im Bild davor dort stand — sie wird ignoriert.
"""
import os, sys, re

SGR = re.compile(r"\x1b\[([0-9;]*)m")


def zellen(text):
    zeilen = []
    st = {"fg": None, "bg": None, "a": frozenset()}
    for zeile in text.split("\n"):
        out, i = [], 0
        for m in SGR.finditer(zeile + "\x1b[m"):
            for ch in zeile[i:m.start()]:
                rev = "7" in st["a"]
                fg = st["fg"] if (ch != " " or rev) else None
                out.append((ch, fg, st["bg"], st["a"]))
            i = m.end()
            codes = [c for c in m.group(1).split(";")] if m.group(1) else ["0"]
            j = 0
            while j < len(codes):
                c = codes[j]
                if c in ("0", ""):
                    st = {"fg": None, "bg": None, "a": frozenset()}
                elif c in ("38", "48") and j + 1 < len(codes):
                    if codes[j + 1] == "5":
                        val = codes[j + 2]; j += 2
                    else:
                        val = tuple(codes[j + 2:j + 5]); j += 4
                    st = dict(st, **{"fg" if c == "38" else "bg": val})
                elif c == "39":
                    st = dict(st, fg=None)
                elif c == "49":
                    st = dict(st, bg=None)
                elif c.isdigit() and 30 <= int(c) <= 37 or c.isdigit() and 90 <= int(c) <= 97:
                    st = dict(st, fg=c)
                elif c.isdigit() and (40 <= int(c) <= 47 or 100 <= int(c) <= 107):
                    st = dict(st, bg=c)
                elif c in ("22",):
                    st = dict(st, a=st["a"] - {"1", "2"})
                elif c in ("27",):
                    st = dict(st, a=st["a"] - {"7"})
                elif c in ("23", "24", "25"):
                    st = dict(st, a=st["a"] - {str(int(c) - 20)})
                else:
                    st = dict(st, a=st["a"] | {c})
                j += 1
        zeilen.append(out)
    return zeilen


def main():
    a, b = sys.argv[1], sys.argv[2]
    na, nb = set(os.listdir(a)), set(os.listdir(b))
    fehler = 0
    for n in sorted(na | nb):
        if n not in na or n not in nb:
            print("NUR IN", a if n in na else b, n); fehler += 1; continue
        ta, tb = open(os.path.join(a, n)).read(), open(os.path.join(b, n)).read()
        if ta == tb:
            continue
        za, zb = zellen(ta), zellen(tb)
        if za == zb:
            continue
        fehler += 1
        print("ANDERS", n)
        gezeigt = 0
        for y, (l1, l2) in enumerate(zip(za, zb)):
            if l1 != l2 and gezeigt < 6:
                gezeigt += 1
                s1 = "".join(c[0] for c in l1); s2 = "".join(c[0] for c in l2)
                if s1 != s2:
                    print("   %2d - %s\n      + %s" % (y, s1.rstrip()[:200], s2.rstrip()[:200]))
                else:
                    x = next(i for i, (p, q) in enumerate(zip(l1, l2)) if p != q)
                    print("   %2d Farbe ab Spalte %d: %r vs %r  [%s]" % (y, x, l1[x][1:], l2[x][1:], s1.strip()[:80]))
        if len(za) != len(zb):
            print("   Zeilenzahl", len(za), len(zb))
    print("GLEICH" if not fehler else "%d Unterschiede" % fehler)
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
