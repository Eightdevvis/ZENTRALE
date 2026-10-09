# core/word_datei.py
#
# Word-Dateien (.docx): lesen (Text, Überschriften, Listen, Tabellen), neu
# anlegen aus Markdown, ändern (Text ersetzen, Abschnitte anhängen). Ändern
# liefert IMMER neue Bytes — das Original fasst niemand an; wohin die neue
# Datei kommt, entscheidet der Aufrufer (die Ablage).
#
# 2026-10-08, Skill word (memory/ki/pdf_word.md). Nur Standardbibliothek
# (zipfile + ElementTree): python-docx bräuchte lxml (kein reines Python), und
# eine .docx ist ein Zip mit XML darin. Die Fallen, an denen selbstgebaute
# Word-Werkzeuge sonst scheitern, und was hier dagegen steht:
#   - Text ist auf „Läufe" (w:r) verteilt, ein Wort kann mitten durch zwei
#     gehen → Ersetzen sucht im ganzen Absatz und verteilt zurück.
#   - Überschriften heißen im deutschen Word „berschrift1" (Stil-id), im
#     englischen „Heading1"; gleich ist nur der interne NAME („heading 1")
#     → immer über den Namen in styles.xml.
#   - ElementTree schreibt nur die Namensräume, die es benutzt sieht; Word
#     verlangt aber alle, die in mc:Ignorable genannt sind → die Erklärungen
#     des Originals werden am Wurzelelement wieder ergänzt.
#   - In numbering.xml stehen alle w:abstractNum VOR allen w:num.
#   - Gelöschter Text der Änderungsverfolgung (w:del) zählt nicht mit,
#     Ausweich-Inhalte (mc:Fallback) nicht doppelt.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import io
import re
import threading
import xml.etree.ElementTree as ET
import zipfile

import textbloecke as tb

MAX_BYTES = 30 * 1024 * 1024
MAX_ENTPACKT = 200 * 1024 * 1024     # gegen Zip-Bomben
MAX_TEIL = 60 * 1024 * 1024          # ein XML-Teil
MAX_EINTRAEGE = 5000

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"
XML_NS = "http://www.w3.org/XML/1998/namespace"
DOC_TYP = ("application/vnd.openxmlformats-officedocument."
           "wordprocessingml.document.main+xml")


def w(tag: str) -> str:
    return "{%s}%s" % (W, tag)


class Fehler(ValueError):
    """Etwas ging mit der Word-Datei nicht — der Text ist für Menschen."""


def ist_docx(daten: bytes) -> bool:
    """Zip mit word/document.xml darin (ohne die ganze Datei zu prüfen)."""
    if not daten or daten[:4] != b"PK\x03\x04":
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(daten)) as z:
            return any(n.startswith("word/") for n in z.namelist())
    except zipfile.BadZipFile:
        return False


# ── Paket öffnen und schreiben ──────────────────────────────────────────

_NS_SPERRE = threading.Lock()


def _namensraeume_merken(roh: bytes) -> dict:
    """Präfix → URI aus einem XML-Teil, und ElementTree bekannt machen
    (sonst schriebe es ns0:, ns1: …)."""
    gesehen = {}
    try:
        for _, (praefix, uri) in ET.iterparse(io.BytesIO(roh), events=("start-ns",)):
            if praefix and praefix not in gesehen:
                gesehen[praefix] = uri
                try:
                    ET.register_namespace(praefix, uri)
                except ValueError:
                    pass
    except ET.ParseError:
        pass
    return gesehen


class Paket:
    """Alle Teile der .docx im Speicher; geändert wird nur die Kopie."""

    def __init__(self, daten: bytes):
        if not daten:
            raise Fehler("Die Datei ist leer.")
        if len(daten) > MAX_BYTES:
            raise Fehler(f"Zu groß — höchstens {MAX_BYTES // 1024 // 1024} MB.")
        if daten[:4] == b"\xd0\xcf\x11\xe0":
            raise Fehler("Das ist eine alte Word-Datei (.doc) oder eine mit Passwort "
                         "geschützte — beides kann ich nicht öffnen. In Word als .docx "
                         "speichern (ohne Passwort) hilft.")
        try:
            z = zipfile.ZipFile(io.BytesIO(daten))
        except zipfile.BadZipFile:
            raise Fehler("Die Datei ist keine lesbare Word-Datei (.docx).")
        with z:
            infos = z.infolist()
            if len(infos) > MAX_EINTRAEGE or sum(i.file_size for i in infos) > MAX_ENTPACKT:
                raise Fehler("Die Datei ist ungewöhnlich gebaut (entpackt riesig) — abgebrochen.")
            self.reihenfolge = [i.filename for i in infos]
            try:
                self.teile = {i.filename: z.read(i) for i in infos}
            except (zipfile.BadZipFile, OSError, RuntimeError):
                raise Fehler("Die Datei ist beschädigt.")
        self._xml = {}
        self.haupt = self._haupt_teil()
        if self.haupt not in self.teile:
            raise Fehler("Das ist keine Word-Datei (kein Dokument darin).")

    # ── Teile ──
    def xml(self, name: str):
        if name not in self._xml:
            roh = self.teile.get(name)
            if roh is None:
                return None
            if len(roh) > MAX_TEIL:
                raise Fehler("Ein Teil der Datei ist zu groß — abgebrochen.")
            _namensraeume_merken(roh)
            try:
                self._xml[name] = ET.fromstring(roh)
            except ET.ParseError:
                raise Fehler("Die Datei ist beschädigt (XML nicht lesbar).")
        return self._xml[name]

    def _haupt_teil(self) -> str:
        rels = self.xml("_rels/.rels")
        if rels is not None:
            for rel in rels:
                if rel.get("Type", "").endswith("/officeDocument"):
                    return rel.get("Target", "").lstrip("/")
        return "word/document.xml"

    def _rels_name(self, teil: str) -> str:
        ordner, _, datei = teil.rpartition("/")
        return f"{ordner}/_rels/{datei}.rels" if ordner else f"_rels/{datei}.rels"

    def verweise(self, teil: str) -> list:
        """[(typ-ende, ziel-teil)] eines Teils (styles, numbering, header …)."""
        rels = self.xml(self._rels_name(teil))
        if rels is None:
            return []
        basis = teil.rpartition("/")[0]
        raus = []
        for rel in rels:
            if rel.get("TargetMode") == "External":
                continue
            ziel = rel.get("Target", "")
            ziel = ziel.lstrip("/") if ziel.startswith("/") else (
                f"{basis}/{ziel}" if basis else ziel)
            teile = []
            for t in ziel.split("/"):          # ../ auflösen
                if t == "..":
                    teile and teile.pop()
                elif t and t != ".":
                    teile.append(t)
            raus.append((rel.get("Type", "").rsplit("/", 1)[-1], "/".join(teile)))
        return raus

    def teil_von(self, typ: str) -> str | None:
        for t, ziel in self.verweise(self.haupt):
            if t == typ and ziel in self.teile:
                return ziel
        return None

    def teil_anlegen(self, typ: str, name: str, inhalt: bytes, inhaltstyp: str) -> str:
        """Neuen Teil samt Verweis vom Dokument und Inhaltstyp."""
        self.teile[name] = inhalt
        self._xml.pop(name, None)
        self.reihenfolge.append(name)
        rels_name = self._rels_name(self.haupt)
        rels = self.xml(rels_name)
        if rels is None:
            rels = ET.Element("{%s}Relationships" % PR)
            self._xml[rels_name] = rels
            self.reihenfolge.append(rels_name)
        ids = {r.get("Id") for r in rels}
        n = 1
        while f"rIdZ{n}" in ids:
            n += 1
        ET.SubElement(rels, "{%s}Relationship" % PR, {
            "Id": f"rIdZ{n}",
            "Type": f"http://schemas.openxmlformats.org/officeDocument/2006/relationships/{typ}",
            "Target": name.rpartition("/")[2] if name.rpartition("/")[0] ==
            self.haupt.rpartition("/")[0] else "/" + name})
        ct = self.xml("[Content_Types].xml")
        if ct is not None:
            ET.SubElement(ct, "{%s}Override" % CT,
                          {"PartName": "/" + name, "ContentType": inhaltstyp})
        return name

    # ── Schreiben ──
    def _serialisieren(self, name: str, root) -> bytes:
        if name.endswith(".rels") or name == "[Content_Types].xml":
            text = _flach(root)
        else:
            text = ET.tostring(root, encoding="unicode")
            text = _erklaerungen_ergaenzen(text, self.teile.get(name, b""))
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
                + text).encode("utf-8")

    def bytes(self, geaendert: set) -> bytes:
        aus = io.BytesIO()
        with zipfile.ZipFile(aus, "w", zipfile.ZIP_DEFLATED) as z:
            gesehen = set()
            # [Content_Types].xml zuerst, wie Word es schreibt
            namen = sorted(self.reihenfolge, key=lambda n: n != "[Content_Types].xml")
            for name in namen:
                if name in gesehen:
                    continue
                gesehen.add(name)
                if name in geaendert and name in self._xml:
                    inhalt = self._serialisieren(name, self._xml[name])
                else:
                    inhalt = self.teile[name]
                z.writestr(name, inhalt)
        return aus.getvalue()


def _flach(root) -> str:
    """Verweise und Inhaltstypen: ein Wurzelelement mit flachen Kindern im
    Standard-Namensraum. ElementTree kann den Standard-Namensraum nicht
    neben Attributen ohne Präfix schreiben — also von Hand."""
    from xml.sax.saxutils import quoteattr
    uri, _, tag = root.tag[1:].partition("}")
    teile = [f'<{tag} xmlns="{uri}">']
    for k in root:
        ktag = k.tag.partition("}")[2] or k.tag
        attr = "".join(f" {a}={quoteattr(v)}" for a, v in k.attrib.items())
        teile.append(f"<{ktag}{attr}/>")
    teile.append(f"</{tag}>")
    return "".join(teile)


def _erklaerungen_ergaenzen(text: str, original: bytes) -> str:
    """Namensraum-Erklärungen des Original-Wurzelelements, die ElementTree
    weggelassen hat, wieder dazuschreiben (mc:Ignorable nennt Präfixe, die
    sonst nirgends vorkommen — Word meldet die Datei dann als beschädigt)."""
    m = re.search(rb"<[A-Za-z][^\s>/]*(\s[^>]*)?>", original.split(b"?>", 1)[-1])
    if not m:
        return text
    alt = dict(re.findall(r'xmlns:([A-Za-z0-9_.-]+)="([^"]*)"',
                          (m.group(1) or b"").decode("utf-8", "replace")))
    kopf = re.match(r"<[^\s>/]+", text)
    if not kopf:
        return text
    ende = text.index(">")
    vorhanden = set(re.findall(r'xmlns:([A-Za-z0-9_.-]+)=', text[:ende]))
    dazu = "".join(f' xmlns:{p}="{u}"' for p, u in alt.items() if p not in vorhanden)
    return text[:kopf.end()] + dazu + text[kopf.end():]


# ── Lesen ───────────────────────────────────────────────────────────────

# Was beim Text sammeln NICHT betreten wird: gelöschter Text, Ausweich-
# Inhalte, Feld-Befehle (das Ergebnis des Felds steht daneben), Grafiken mit
# Textfeldern darin (deren Absätze kämen sonst mitten in den Satz).
_UEBERSPRINGEN = {w("del"), w("instrText"), w("delText"), w("drawing"), w("pict"),
                  w("object"), w("rPr"), w("pPr"), "{%s}AlternateContent" % MC,
                  w("footnoteReference"), w("commentReference")}


def _absatz_teile(el, raus: list):
    for k in el:
        tag = k.tag
        if tag == w("t"):
            raus.append(k.text or "")
        elif tag == w("tab"):
            raus.append("\t")
        elif tag in (w("br"), w("cr")):
            raus.append("\n")
        elif tag == w("noBreakHyphen"):
            raus.append("-")
        elif tag not in _UEBERSPRINGEN:
            _absatz_teile(k, raus)


def absatz_text(p) -> str:
    raus = []
    _absatz_teile(p, raus)
    return "".join(raus)


class _Stile:
    def __init__(self, paket: Paket):
        self.stile = {}
        teil = paket.teil_von("styles")
        root = paket.xml(teil) if teil else None
        for s in (root if root is not None else []):
            if s.tag != w("style"):
                continue
            name = s.find(w("name"))
            basis = s.find(w("basedOn"))
            ebene = s.find(f"{w('pPr')}/{w('outlineLvl')}")
            self.stile[s.get(w("styleId"))] = {
                "name": (name.get(w("val")) if name is not None else "").lower(),
                "basis": basis.get(w("val")) if basis is not None else None,
                "ebene": int(ebene.get(w("val"))) if ebene is not None
                and str(ebene.get(w("val"))).isdigit() else None,
                "typ": s.get(w("type")),
            }

    def ebene(self, stil_id) -> int | None:
        """Überschrift-Ebene eines Absatz-Stils (0 = Titel), sonst None."""
        for _ in range(6):
            s = self.stile.get(stil_id)
            if s is None:
                return None
            if s["name"] == "title":
                return 0
            m = re.fullmatch(r"heading (\d)", s["name"])
            if m:
                return int(m.group(1))
            if s["ebene"] is not None and s["ebene"] < 9:
                return s["ebene"] + 1
            stil_id = s["basis"]
        return None

    def id_fuer(self, name: str, typ: str = "paragraph") -> str | None:
        for sid, s in self.stile.items():
            if s["name"] == name.lower() and (s["typ"] or "paragraph") == typ:
                return sid
        return None


class _Nummern:
    """Welche Liste wie zählt: numId → {ilvl: (format, start)}."""

    def __init__(self, paket: Paket):
        self.formate = {}
        teil = paket.teil_von("numbering")
        root = paket.xml(teil) if teil else None
        kinder = list(root) if root is not None else []
        abstrakt = {}
        for a in kinder:
            if a.tag == w("abstractNum"):
                abstrakt[a.get(w("abstractNumId"))] = {
                    lvl.get(w("ilvl")): (_wert(lvl, "numFmt", "bullet"),
                                         _zahl(_wert(lvl, "start", "1")))
                    for lvl in a.findall(w("lvl"))}
        for n in kinder:
            if n.tag == w("num"):
                ebenen = dict(abstrakt.get(_wert(n, "abstractNumId", ""), {}))
                for o in n.findall(w("lvlOverride")):
                    s = o.find(w("startOverride"))
                    ilvl = o.get(w("ilvl"))
                    if s is not None and ilvl in ebenen:
                        ebenen[ilvl] = (ebenen[ilvl][0], _zahl(s.get(w("val"))))
                self.formate[n.get(w("numId"))] = ebenen
        self.zaehler = {}

    def marke(self, num_id, ilvl) -> str:
        fmt, start = self.formate.get(num_id, {}).get(ilvl, ("bullet", 1))
        if fmt in ("bullet", "none"):
            return "-"
        n = self.zaehler.get((num_id, ilvl), start - 1) + 1
        self.zaehler[(num_id, ilvl)] = n
        return f"{n}."


def _wert(el, kind: str, vorgabe: str) -> str:
    k = el.find(w(kind))
    return k.get(w("val"), vorgabe) if k is not None else vorgabe


def _zahl(text, vorgabe: int = 1) -> int:
    return int(text) if str(text).isdigit() else vorgabe


def _zelle(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _tabelle_md(tbl) -> str:
    reihen = []
    for tr in tbl.findall(w("tr")):
        zellen = []
        for tc in tr.findall(w("tc")):
            texte = [absatz_text(p) for p in tc.iter(w("p"))]
            zellen.append(_zelle(" / ".join(t for t in texte if t.strip())))
            spanne = tc.find(f"{w('tcPr')}/{w('gridSpan')}")
            if spanne is not None and str(spanne.get(w("val"))).isdigit():
                zellen += [""] * (int(spanne.get(w("val"))) - 1)
        reihen.append(zellen)
    if not reihen:
        return ""
    breite = max(len(r) for r in reihen)
    reihen = [r + [""] * (breite - len(r)) for r in reihen]
    zeilen = ["| " + " | ".join(reihen[0]) + " |", "|" + "---|" * breite]
    zeilen += ["| " + " | ".join(r) + " |" for r in reihen[1:]]
    return "\n".join(zeilen)


def _koerper(el, stile, nummern, raus, zaehl):
    for k in el:
        if k.tag == w("p"):
            text = absatz_text(k).strip()
            ppr = k.find(w("pPr"))
            stil = ppr.find(w("pStyle")) if ppr is not None else None
            stil_id = stil.get(w("val")) if stil is not None else None
            ebene = stile.ebene(stil_id) if stil_id else None
            if ebene is None and ppr is not None and ppr.find(w("outlineLvl")) is not None:
                v = ppr.find(w("outlineLvl")).get(w("val"))
                ebene = int(v) + 1 if str(v).isdigit() and int(v) < 9 else None
            numpr = ppr.find(w("numPr")) if ppr is not None else None
            if not text:
                if raus and raus[-1] != "":
                    raus.append("")
                continue
            if ebene is not None:
                raus += ["", "#" * max(1, min(6, ebene)) + " " + text, ""]
                zaehl["ueberschriften"].append(text)
            elif numpr is not None:
                ilvl = numpr.find(w("ilvl"))
                num = numpr.find(w("numId"))
                ilvl = ilvl.get(w("val")) if ilvl is not None else "0"
                num = num.get(w("val")) if num is not None else None
                einzug = "  " * (int(ilvl) if str(ilvl).isdigit() else 0)
                raus.append(f"{einzug}{nummern.marke(num, ilvl)} {text}")
            else:
                raus += [text, ""]
            zaehl["absaetze"] += 1
        elif k.tag == w("tbl"):
            md = _tabelle_md(k)
            if md:
                raus += ["", md, ""]
                zaehl["tabellen"] += 1
        elif k.tag in (w("sdt"), w("sdtContent"), w("customXml"), w("ins"), w("smartTag")):
            _koerper(k, stile, nummern, raus, zaehl)


def lesen(daten: bytes) -> dict:
    """→ {text (Markdown: # Überschriften, - Listen, | Tabellen), absaetze,
    tabellen, ueberschriften, hinweise}."""
    with _NS_SPERRE:
        paket = Paket(daten)
        doc = paket.xml(paket.haupt)
        body = doc.find(w("body")) if doc is not None else None
        if body is None:
            raise Fehler("Das Dokument hat keinen Inhalt.")
        raus = []
        zaehl = {"absaetze": 0, "tabellen": 0, "ueberschriften": []}
        _koerper(body, _Stile(paket), _Nummern(paket), raus, zaehl)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(raus)).strip()
    hinweise = []
    if body.find(f".//{w('del')}") is not None or body.find(f".//{w('ins')}") is not None:
        hinweise.append("enthält Änderungsverfolgung: Eingefügtes ist drin, Gelöschtes nicht")
    if any(t in ("header", "footer") for t, _ in paket.verweise(paket.haupt)):
        hinweise.append("hat Kopf-/Fußzeilen (nicht mitgelesen)")
    if paket.teil_von("comments"):
        hinweise.append("hat Kommentare (nicht mitgelesen)")
    if body.find(f".//{w('drawing')}") is not None or body.find(f".//{w('pict')}") is not None:
        hinweise.append("enthält Bilder oder Textfelder (nicht mitgelesen)")
    return dict(zaehl, text=text, hinweise=hinweise)


# ── Schreiben: Markdown → Absätze und Tabellen ─────────────────────────

# Unsere Stile, über den NAMEN gesucht; fehlt einer im Dokument, kommt diese
# Fassung dazu. (id, name, typ, Inhalt)
_STILE = {
    "heading 1": ("Heading1", "paragraph",
                  '<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
                  '<w:pPr><w:keepNext/><w:spacing w:before="360" w:after="120"/>'
                  '<w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="36"/></w:rPr>'),
    "heading 2": ("Heading2", "paragraph",
                  '<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
                  '<w:pPr><w:keepNext/><w:spacing w:before="240" w:after="80"/>'
                  '<w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:sz w:val="28"/></w:rPr>'),
    "heading 3": ("Heading3", "paragraph",
                  '<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
                  '<w:pPr><w:keepNext/><w:spacing w:before="200" w:after="60"/>'
                  '<w:outlineLvl w:val="2"/></w:pPr><w:rPr><w:b/><w:sz w:val="24"/></w:rPr>'),
    "list paragraph": ("ListParagraph", "paragraph",
                       '<w:basedOn w:val="Normal"/><w:qFormat/>'
                       '<w:pPr><w:spacing w:after="40"/><w:ind w:left="720"/></w:pPr>'),
    "code": ("Code", "paragraph",
             '<w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="0"/>'
             '<w:shd w:val="clear" w:color="auto" w:fill="F0F0F0"/></w:pPr>'
             '<w:rPr><w:rFonts w:ascii="Courier New" w:hAnsi="Courier New" '
             'w:cs="Courier New"/><w:sz w:val="19"/></w:rPr>'),
    "table grid": ("TableGrid", "table",
                   '<w:basedOn w:val="TableNormal"/><w:pPr><w:spacing w:after="0"/></w:pPr>'
                   '<w:tblPr><w:tblBorders>'
                   + "".join(f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
                             for s in ("top", "left", "bottom", "right", "insideH", "insideV"))
                   + '</w:tblBorders><w:tblCellMar><w:left w:w="100" w:type="dxa"/>'
                   '<w:right w:w="100" w:type="dxa"/></w:tblCellMar></w:tblPr>'),
}

_NS_KOPF = f'xmlns:w="{W}" xmlns:r="{R}"'
_STILE_LEER = (f'<w:styles {_NS_KOPF}><w:docDefaults><w:rPrDefault><w:rPr>'
               '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri" '
               'w:eastAsia="Calibri"/><w:sz w:val="22"/><w:szCs w:val="22"/>'
               '<w:lang w:val="de-DE"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>'
               '<w:spacing w:after="160" w:line="276" w:lineRule="auto"/></w:pPr>'
               '</w:pPrDefault></w:docDefaults>'
               '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
               '<w:name w:val="Normal"/><w:qFormat/></w:style>'
               '<w:style w:type="table" w:default="1" w:styleId="TableNormal">'
               '<w:name w:val="Normal Table"/><w:tblPr><w:tblInd w:w="0" w:type="dxa"/>'
               '<w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="108" w:type="dxa"/>'
               '<w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/>'
               '</w:tblCellMar></w:tblPr></w:style></w:styles>')
_NUMMERN_LEER = f'<w:numbering {_NS_KOPF}></w:numbering>'
STILE_TYP = "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"
NUMMERN_TYP = "application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"
SATZSPIEGEL_TWIPS = 9638             # A4 minus 2 × 2 cm


def _stil(paket: Paket, geaendert: set, name: str) -> str:
    """Die Stil-id zu einem Namen — fehlt der Stil, wird er angelegt."""
    teil = paket.teil_von("styles")
    if teil is None:
        teil = paket.teil_anlegen("styles", "word/styles.xml",
                                  _STILE_LEER.encode(), STILE_TYP)
        geaendert.add(paket._rels_name(paket.haupt))
        geaendert.add("[Content_Types].xml")
    root = paket.xml(teil)
    vorhanden = _Stile(paket).id_fuer(name, _STILE[name][1])
    if vorhanden:
        return vorhanden
    sid, typ, inhalt = _STILE[name]
    ids = {s.get(w("styleId")) for s in root}
    while sid in ids:
        sid += "Z"
    neu = ET.fromstring(f'<w:style {_NS_KOPF} w:type="{typ}" w:styleId="{sid}">'
                        f'<w:name w:val="{name}"/>{inhalt}</w:style>')
    # basedOn/next zeigen auf ids — im deutschen Word heißt „Normal" etwa
    # „Standard". Also über den Namen auflösen; gibt es ihn nicht: weglassen.
    stile = _Stile(paket)
    echte = {"Normal": stile.id_fuer("normal"),
             "TableNormal": stile.id_fuer("normal table", "table")}
    for tag in ("basedOn", "next"):
        el = neu.find(w(tag))
        if el is not None:
            ziel = echte.get(el.get(w("val")))
            if ziel:
                el.set(w("val"), ziel)
            else:
                neu.remove(el)
    root.append(neu)
    geaendert.add(teil)
    return sid


def _liste_anlegen(paket: Paket, geaendert: set, geordnet: bool, start: int) -> str:
    """Eine neue Nummerierung (je Liste eine, damit „1." neu beginnt)."""
    teil = paket.teil_von("numbering")
    if teil is None:
        teil = paket.teil_anlegen("numbering", "word/numbering.xml",
                                  _NUMMERN_LEER.encode(), NUMMERN_TYP)
        geaendert.add(paket._rels_name(paket.haupt))
        geaendert.add("[Content_Types].xml")
    root = paket.xml(teil)
    a_ids = [int(a.get(w("abstractNumId"))) for a in root.findall(w("abstractNum"))
             if str(a.get(w("abstractNumId"))).isdigit()]
    n_ids = [int(n.get(w("numId"))) for n in root.findall(w("num"))
             if str(n.get(w("numId"))).isdigit()]
    aid, nid = max(a_ids, default=0) + 1, max(n_ids, default=0) + 1
    ebenen = ""
    for i in range(3):
        if geordnet:
            fmt, text = "decimal", f"%{i + 1}."
        else:
            fmt, text = "bullet", ("•", "◦", "▪")[i]
        ebenen += (f'<w:lvl w:ilvl="{i}"><w:start w:val="{start if i == 0 else 1}"/>'
                   f'<w:numFmt w:val="{fmt}"/><w:lvlText w:val="{text}"/>'
                   f'<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="{720 * (i + 1)}" '
                   f'w:hanging="360"/></w:pPr></w:lvl>')
    abstrakt = ET.fromstring(f'<w:abstractNum {_NS_KOPF} w:abstractNumId="{aid}">'
                             f'<w:multiLevelType w:val="hybridMultilevel"/>{ebenen}'
                             f'</w:abstractNum>')
    num = ET.fromstring(f'<w:num {_NS_KOPF} w:numId="{nid}"><w:abstractNumId w:val="{aid}"/></w:num>')
    # Reihenfolge der Norm: alle abstractNum vor allen num
    erste_num = next((i for i, k in enumerate(root) if k.tag == w("num")), len(root))
    root.insert(erste_num, abstrakt)
    root.append(num)
    geaendert.add(teil)
    return str(nid)


def _lauf(eltern, text: str, fett: bool = False):
    r = ET.SubElement(eltern, w("r"))
    if fett:
        ET.SubElement(ET.SubElement(r, w("rPr")), w("b"))
    t = ET.SubElement(r, w("t"))
    t.text = text
    t.set("{%s}space" % XML_NS, "preserve")
    return r


def _absatz(stil: str | None = None, stuecke=(), fett_alles=False):
    p = ET.Element(w("p"))
    if stil:
        ppr = ET.SubElement(p, w("pPr"))
        ET.SubElement(ppr, w("pStyle"), {w("val"): stil})
    for text, fett in stuecke:
        _lauf(p, text, fett or fett_alles)
    return p


def _tabelle(paket, geaendert, block):
    stil = _stil(paket, geaendert, "table grid")
    spalten = len(block.zeilen[0])
    breite = SATZSPIEGEL_TWIPS // max(1, spalten)
    tbl = ET.Element(w("tbl"))
    tblpr = ET.SubElement(tbl, w("tblPr"))
    ET.SubElement(tblpr, w("tblStyle"), {w("val"): stil})
    ET.SubElement(tblpr, w("tblW"), {w("w"): "0", w("type"): "auto"})
    grid = ET.SubElement(tbl, w("tblGrid"))
    for _ in range(spalten):
        ET.SubElement(grid, w("gridCol"), {w("w"): str(breite)})
    for zi, reihe in enumerate(block.zeilen):
        tr = ET.SubElement(tbl, w("tr"))
        kopf = block.kopf and zi == 0
        if kopf:
            ET.SubElement(ET.SubElement(tr, w("trPr")), w("tblHeader"))
        for zelle in reihe:
            tc = ET.SubElement(tr, w("tc"))
            ET.SubElement(ET.SubElement(tc, w("tcPr")), w("tcW"),
                          {w("w"): str(breite), w("type"): "dxa"})
            tc.append(_absatz(None, tb.stuecke(zelle), fett_alles=kopf))
    return tbl


def _elemente(paket: Paket, geaendert: set, markdown: str) -> list:
    raus = []
    for b in tb.bloecke(markdown):
        if b.art == tb.UEBERSCHRIFT:
            raus.append(_absatz(_stil(paket, geaendert, f"heading {b.ebene}"),
                                tb.stuecke(b.text)))
        elif b.art == tb.ABSATZ:
            raus.append(_absatz(None, tb.stuecke(b.text)))
        elif b.art == tb.LISTE:
            stil = _stil(paket, geaendert, "list paragraph")
            start = next((n for _, n, _ in b.punkte if n is not None), 1)
            nid = _liste_anlegen(paket, geaendert, b.geordnet, start)
            for ebene, _, text in b.punkte:
                p = _absatz(stil, tb.stuecke(text))
                numpr = ET.SubElement(p.find(w("pPr")), w("numPr"))
                ET.SubElement(numpr, w("ilvl"), {w("val"): str(ebene)})
                ET.SubElement(numpr, w("numId"), {w("val"): nid})
                raus.append(p)
        elif b.art == tb.TABELLE:
            raus.append(_tabelle(paket, geaendert, b))
            raus.append(_absatz())     # Word will hinter einer Tabelle einen Absatz
        elif b.art == tb.CODE:
            stil = _stil(paket, geaendert, "code")
            for zeile in (b.text.split("\n") or [""]):
                raus.append(_absatz(stil, [(zeile.replace("\t", "    "), False)] if zeile else []))
        elif b.art == tb.LINIE:
            p = _absatz()
            ppr = ET.SubElement(p, w("pPr"))
            rand = ET.SubElement(ppr, w("pBdr"))
            ET.SubElement(rand, w("bottom"), {w("val"): "single", w("sz"): "6",
                                              w("space"): "1", w("color"): "999999"})
            raus.append(p)
    return raus


def _anhaengen(paket: Paket, geaendert: set, markdown: str) -> int:
    doc = paket.xml(paket.haupt)
    body = doc.find(w("body"))
    if body is None:
        body = ET.SubElement(doc, w("body"))
    neu = _elemente(paket, geaendert, markdown)
    sect = body.find(w("sectPr"))
    stelle = list(body).index(sect) if sect is not None and list(body)[-1] is sect else len(body)
    for i, el in enumerate(neu):
        body.insert(stelle + i, el)
    geaendert.add(paket.haupt)
    return len(neu)


# ── Ersetzen über Lauf-Grenzen ──────────────────────────────────────────

def _texte_im_absatz(p) -> list:
    """[(element|None, text)] in Lesereihenfolge; None = Tab/Umbruch (nicht
    änderbar — ein Treffer darüber hinweg wird ausgelassen)."""
    raus = []

    def gehen(el):
        for k in el:
            if k.tag == w("t"):
                raus.append((k, k.text or ""))
            elif k.tag in (w("tab"), w("br"), w("cr")):
                raus.append((None, "\t" if k.tag == w("tab") else "\n"))
            elif k.tag not in _UEBERSPRINGEN and k.tag != w("p"):
                gehen(k)
    gehen(p)
    return raus


def _ersetzen_im_absatz(p, alt: str, neu: str) -> tuple:
    """→ (ersetzt, ausgelassen)."""
    teile = _texte_im_absatz(p)
    ganz = "".join(t for _, t in teile)
    if alt not in ganz:
        return 0, 0
    # Lage jedes Zeichens: (teil-index, versatz)
    lage = [(i, j) for i, (_, t) in enumerate(teile) for j in range(len(t))]
    treffer, pos = [], 0
    while True:
        s = ganz.find(alt, pos)
        if s < 0:
            break
        treffer.append(s)
        pos = s + len(alt)
    ersetzt = ausgelassen = 0
    texte = [t for _, t in teile]
    for s in reversed(treffer):            # von hinten: Versätze bleiben gültig
        e = s + len(alt) - 1
        betroffen = sorted({lage[k][0] for k in range(s, e + 1)})
        if any(teile[i][0] is None for i in betroffen):
            ausgelassen += 1
            continue
        erstes, letztes = betroffen[0], betroffen[-1]
        a, b = lage[s][1], lage[e][1]
        if erstes == letztes:
            texte[erstes] = texte[erstes][:a] + neu + texte[erstes][b + 1:]
        else:
            texte[erstes] = texte[erstes][:a] + neu
            for i in betroffen[1:-1]:
                texte[i] = ""
            texte[letztes] = texte[letztes][b + 1:]
        ersetzt += 1
    for (el, alt_text), t in zip(teile, texte):
        if el is not None and t != alt_text:
            el.text = t
            el.set("{%s}space" % XML_NS, "preserve")
    return ersetzt, ausgelassen


def _ersetzen(paket: Paket, geaendert: set, alt: str, neu: str) -> tuple:
    teile = [paket.haupt] + [z for t, z in paket.verweise(paket.haupt)
                             if t in ("header", "footer") and z in paket.teile]
    summe = auslass = 0
    for teil in teile:
        root = paket.xml(teil)
        if root is None:
            continue
        n_teil = 0
        for p in root.iter(w("p")):
            n, a = _ersetzen_im_absatz(p, alt, neu)
            n_teil += n
            auslass += a
        if n_teil:
            geaendert.add(teil)
            summe += n_teil
    return summe, auslass


def _titel_setzen(paket: Paket, geaendert: set, titel: str):
    teil = "docProps/core.xml"
    root = paket.xml(teil)
    if root is None:
        return
    dc = "http://purl.org/dc/elements/1.1/"
    el = root.find("{%s}title" % dc)
    if el is None:
        el = ET.SubElement(root, "{%s}title" % dc)
    el.text = titel
    geaendert.add(teil)


# ── Öffentlich: neu und ändern ──────────────────────────────────────────

def _leeres_dokument(titel: str) -> bytes:
    from xml.sax.saxutils import escape
    teile = {
        "[Content_Types].xml": (
            f'<Types xmlns="{CT}">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            f'<Override PartName="/word/document.xml" ContentType="{DOC_TYP}"/>'
            '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            '</Types>'),
        "_rels/.rels": (
            f'<Relationships xmlns="{PR}">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '</Relationships>'),
        "word/document.xml": (
            f'<w:document {_NS_KOPF}><w:body><w:sectPr>'
            '<w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" '
            'w:bottom="1134" w:left="1134" w:header="567" w:footer="567" w:gutter="0"/>'
            '</w:sectPr></w:body></w:document>'),
        "word/_rels/document.xml.rels": f'<Relationships xmlns="{PR}"></Relationships>',
        "docProps/core.xml": (
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/'
            'metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f'<dc:title>{escape(titel)}</dc:title><dc:creator>ZENTRALE</dc:creator>'
            '</cp:coreProperties>'),
    }
    aus = io.BytesIO()
    with zipfile.ZipFile(aus, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in teile.items():
            z.writestr(name, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n' + text)
    return aus.getvalue()


def erzeugen(titel: str, markdown: str) -> bytes:
    """Markdown → neue .docx (A4, Calibri 11, echte Überschriften-Stile,
    Listen, Tabellen mit Kopfzeile)."""
    if not str(markdown or "").strip():
        raise Fehler("Leerer Inhalt — keine Word-Datei erzeugt.")
    return aendern(_leeres_dokument(" ".join(str(titel or "").split())[:200]),
                   anhaengen=markdown)[0]


def aendern(daten: bytes, ersetzen=(), anhaengen: str = "", titel: str | None = None) -> tuple:
    """Eine geänderte KOPIE. ersetzen: [(alt, neu)], jeder Treffer im Text
    (auch über Lauf-Grenzen, auch in Kopf-/Fußzeilen); anhaengen: Markdown
    ans Ende. → (neue_bytes, {ersetzt: [(alt, anzahl, ausgelassen)],
    angehaengt: Zahl der neuen Absätze/Tabellen})."""
    ersetzen = [(str(a), str(n)) for a, n in (ersetzen or [])]
    if any(not a for a, _ in ersetzen):
        raise Fehler("Ein leerer Suchtext lässt sich nicht ersetzen.")
    if not ersetzen and not str(anhaengen or "").strip() and not titel:
        raise Fehler("Nichts zu ändern angegeben.")
    with _NS_SPERRE:
        paket = Paket(daten)
        geaendert = set()
        bericht = []
        for alt, neu in ersetzen:
            n, aus = _ersetzen(paket, geaendert, alt, neu)
            bericht.append((alt, n, aus))
        dazu = _anhaengen(paket, geaendert, anhaengen) if str(anhaengen or "").strip() else 0
        if titel:
            _titel_setzen(paket, geaendert, titel)
        return paket.bytes(geaendert), {"ersetzt": bericht, "angehaengt": dazu}
