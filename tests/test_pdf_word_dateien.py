"""PDF und Word als Dateien (Skills pdf und word, 2026-10-08).

Die Dienste darunter: textbloecke (Markdown → Blöcke), pdf_schreiben (neues
PDF), pdf_datei (lesen, Tabellen, Formular, zusammenfügen — pypdf im
Kindprozess), word_datei (.docx lesen, anlegen, geänderte Kopie). Alle
Beispieldateien entstehen hier im Test; Fehlerfälle: kaputt, verschlüsselt,
leer/gescannt, altes .doc, zu groß.
"""
import io
import zipfile

import pytest

import pdf_datei
import pdf_schreiben
import textbloecke as tb
import word_datei


# ── Beispieldateien ─────────────────────────────────────────────────────

def _roh_pdf(objekte: list) -> bytes:
    """Ein PDF aus fertigen Objekten (1 = Katalog); für Fälle, die der
    eigene Schreiber nicht baut (Formular, leere Seite)."""
    out, lage = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objekte, 1):
        lage.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objekte) + 1)
    for o in lage:
        out += b"%010d 00000 n \n" % o
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objekte) + 1, x)
    return bytes(out)


def formular_pdf() -> bytes:
    return _roh_pdf([
        b"<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [4 0 R 5 0 R] >> >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Annots [4 0 R 5 0 R] >>",
        b"<< /Type /Annot /Subtype /Widget /FT /Tx /T (Name) /V (Sasha) "
        b"/Rect [10 10 100 30] /P 3 0 R >>",
        b"<< /Type /Annot /Subtype /Widget /FT /Btn /T (Einverstanden) /V /Off "
        b"/Rect [10 40 30 60] /P 3 0 R >>",
    ])


def scan_pdf() -> bytes:
    """Eine Seite ohne Text — so sieht ein Scan für einen Text-Leser aus."""
    return _roh_pdf([
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents 4 0 R >>",
        b"<< /Length 30 >>\nstream\n0.5 g 10 10 100 100 re f 0 g  \nendstream",
    ])


def text_pdf(*seiten: str) -> bytes:
    """Mehrseitig: jede Seite beginnt mit einer Überschrift (# Seite …)."""
    md = "\n\n".join(f"# {s}\n\n" + "Füllwort " * 900 for s in seiten)
    return pdf_schreiben.erzeugen("Probe", md)[0]


def verschluesselt(daten: bytes, passwort: str) -> bytes:
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter(clone_from=PdfReader(io.BytesIO(daten)))
    w.encrypt(passwort, owner_password="eigentuemer", algorithm="RC4-128")
    aus = io.BytesIO()
    w.write(aus)
    return aus.getvalue()


# ── textbloecke ─────────────────────────────────────────────────────────

def test_markdown_wird_zu_bloecken():
    md = ("# Titel\n\nEin **fetter** Satz\nüber zwei Zeilen.\n\n"
          "| A | B |\n|---|---|\n| 1 | 2 \\| 3 |\n\n"
          "- eins\n  - unter\n3. drei\n4. vier\n\n```\nx = 1\n```\n---\n")
    b = tb.bloecke(md)
    arten = [x.art for x in b]
    assert arten == [tb.UEBERSCHRIFT, tb.ABSATZ, tb.TABELLE, tb.LISTE, tb.CODE, tb.LINIE]
    assert b[1].text == "Ein **fetter** Satz über zwei Zeilen."
    assert b[2].kopf and b[2].zeilen == [["A", "B"], ["1", "2 | 3"]]
    assert b[3].punkte == [(0, None, "eins"), (1, None, "unter"), (0, 3, "drei"), (0, 4, "vier")]
    assert tb.stuecke("a **b** [c](http://x)") == [("a ", False), ("b", True), (" c (http://x)", False)]


# ── PDF schreiben und lesen ─────────────────────────────────────────────

def test_neues_pdf_hat_umlaute_titel_und_seitenzahlen():
    roh, info = pdf_schreiben.erzeugen("Übersicht", "# Miete\n\nÄpfel, Öl, Süß — 650 €.")
    assert info == {"seiten": 1, "ersetzt": 0, "beispiele": []}
    r = pdf_datei.lesen(roh)
    assert r["seiten_gesamt"] == 1 and r["titel"] == "Übersicht"
    text = r["seiten"][0]["text"]
    assert "Miete" in text and "Äpfel, Öl, Süß — 650 €." in text and "Seite 1 von 1" in text


def test_lange_tabelle_laeuft_ueber_seiten_und_wiederholt_den_kopf():
    zeilen = "\n".join(f"| Posten {i} | {i},00 € |" for i in range(120))
    roh, info = pdf_schreiben.erzeugen("T", "| Was | Betrag |\n|---|---|\n" + zeilen)
    assert info["seiten"] >= 2
    seiten = pdf_datei.lesen(roh)["seiten"]
    assert all("Was" in s["text"] and "Betrag" in s["text"] for s in seiten)
    assert "Posten 119" in seiten[-1]["text"]


def test_fremde_zeichen_werden_gezaehlt_pfeile_umschrieben():
    roh, info = pdf_schreiben.erzeugen("T", "A → B, 你好 😀")
    assert info["ersetzt"] == 3 and info["beispiele"] == ["你", "好", "😀"]
    assert "A -> B" in pdf_datei.lesen(roh)["seiten"][0]["text"]


def test_leerer_inhalt_ergibt_kein_pdf():
    with pytest.raises(ValueError):
        pdf_schreiben.erzeugen("T", "  \n ")


def test_seitenangaben():
    assert pdf_datei.seiten_auswahl("1-3, 7", 10) == [1, 2, 3, 7]
    assert pdf_datei.seiten_auswahl("8-", 10) == [8, 9, 10]
    assert pdf_datei.seiten_auswahl("", 3) == [1, 2, 3]
    assert pdf_datei.seiten_text([1, 2, 3, 7, 9, 10]) == "1-3, 7, 9-10"
    for falsch in ("0", "5-3", "11", "a"):
        with pytest.raises(pdf_datei.Fehler):
            pdf_datei.seiten_auswahl(falsch, 10)


def test_mehrseitig_lesen_mit_seitenzahlen():
    roh = text_pdf("Anfang", "Mitte", "Schluss")
    r = pdf_datei.lesen(roh, "2-3")
    assert r["seiten_gesamt"] >= 3
    assert [s["nr"] for s in r["seiten"]] == list(range(2, r["seiten_gesamt"] + 1))[:2]
    with pytest.raises(pdf_datei.Fehler, match="gibt es nicht"):
        pdf_datei.lesen(roh, "99")


def test_tabellen_werden_aus_den_spalten_erkannt():
    roh, _ = pdf_schreiben.erzeugen("R", "| Posten | Menge | Preis |\n|---|---|---|\n"
                                         "| Äpfel | 3 | 2,50 € |\n| Birnen | 10 | 4,00 € |")
    t = pdf_datei.lesen(roh, None, "tabellen")["seiten"][0]["tabellen"]
    assert t and t[0][0] == ["Posten", "Menge", "Preis"]
    assert ["Birnen", "10", "4,00 €"] in t[0]


def test_tabellen_raten_mit_luecken():
    text = "Name      Note   Punkte\n\nAnna      1,3    92\nBen              71\nfliesstext ohne spalten"
    t = pdf_datei.tabellen_aus_layout(text)
    assert t == [[["Name", "Note", "Punkte"], ["Anna", "1,3", "92"], ["Ben", "", "71"]]]


def test_formularfelder_werden_gelesen():
    r = pdf_datei.lesen(formular_pdf(), was="formular")
    assert r["felder"] == 2
    felder = {f["name"]: f for f in r["formular"]}
    assert felder["Name"]["art"] == "text" and felder["Name"]["wert"] == "Sasha"
    assert felder["Einverstanden"]["art"] == "knopf" and felder["Einverstanden"]["wert"] == "Off"


def test_scan_ohne_text_wird_ehrlich_gemeldet():
    r = pdf_datei.lesen(scan_pdf())
    assert r["seiten"][0]["text"].strip() == ""
    text, fehler = pdf_datei.text_alle(scan_pdf())
    assert text == "" and "gescannt" in fehler


def test_verschluesselt_mit_passwort_geht_nicht_ohne_geht():
    roh = text_pdf("Geheim")
    with pytest.raises(pdf_datei.Fehler, match="Passwort"):
        pdf_datei.lesen(verschluesselt(roh, "geheim"))
    offen = pdf_datei.lesen(verschluesselt(roh, ""))
    assert offen["gesperrt_offen"] and "Geheim" in offen["seiten"][0]["text"]


@pytest.mark.parametrize("daten", [b"", b"kein pdf", b"%PDF-1.7\nnur Muell\x00\xff" * 20])
def test_kaputt_oder_leer_ist_ein_klarer_fehler(daten):
    with pytest.raises(pdf_datei.Fehler):
        pdf_datei.lesen(daten)


def test_zu_lange_arbeit_wird_abgebrochen(monkeypatch):
    monkeypatch.setattr(pdf_datei, "ZEIT_S", 0.001)
    with pytest.raises(pdf_datei.Fehler, match="zu lange"):
        pdf_datei.info(text_pdf("x"))


def test_zusammenfuegen_und_seiten_herausnehmen():
    a = pdf_schreiben.erzeugen("A", "# Aaa eins")[0]
    b = text_pdf("Bbb")
    nb = pdf_datei.lesen(b)["seiten_gesamt"]
    neu, n = pdf_datei.zusammenfuegen([(b, "1"), (a, None)], "Mappe")
    assert n == 2
    r = pdf_datei.lesen(neu)
    assert r["titel"] == "Mappe" and "Bbb" in r["seiten"][0]["text"]
    assert "Aaa eins" in r["seiten"][1]["text"]
    ohne_erste, n = pdf_datei.zusammenfuegen([(b, f"2-{nb}")])
    assert n == nb - 1
    with pytest.raises(pdf_datei.Fehler):
        pdf_datei.zusammenfuegen([(a, "3")])
    with pytest.raises(pdf_datei.Fehler, match="Passwort"):
        pdf_datei.zusammenfuegen([(verschluesselt(a, "pw"), None)])


# ── Word ────────────────────────────────────────────────────────────────

_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def deutsches_docx(body: str, kopfzeile: str = "") -> bytes:
    """Wie aus einem deutschen Word: Stil-ids „Standard", „berschrift1",
    eine vorhandene Nummerierung, und mc:Ignorable nennt w14, das sonst
    nirgends vorkommt."""
    teile = {
        "[Content_Types].xml":
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>',
        "_rels/.rels":
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '</Relationships>',
        "word/_rels/document.xml.rels":
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
            + ('<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>'
               if kopfzeile else "") +
            '</Relationships>',
        "word/styles.xml":
            f'<w:styles {_W}>'
            '<w:style w:type="paragraph" w:default="1" w:styleId="Standard"><w:name w:val="Normal"/></w:style>'
            '<w:style w:type="paragraph" w:styleId="berschrift1"><w:name w:val="heading 1"/>'
            '<w:basedOn w:val="Standard"/></w:style></w:styles>',
        "word/numbering.xml":
            f'<w:numbering {_W}><w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0">'
            '<w:start w:val="1"/><w:numFmt w:val="decimal"/></w:lvl></w:abstractNum>'
            '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>',
        "word/document.xml":
            f'<w:document {_W} xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
            'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" mc:Ignorable="w14">'
            f'<w:body>{body}<w:sectPr/></w:body></w:document>',
    }
    if kopfzeile:
        teile["word/header1.xml"] = (f'<w:hdr {_W}><w:p><w:r><w:t>{kopfzeile}</w:t>'
                                     '</w:r></w:p></w:hdr>')
    aus = io.BytesIO()
    with zipfile.ZipFile(aus, "w") as z:
        for n, t in teile.items():
            z.writestr(n, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + t)
    return aus.getvalue()


def _p(text, stil=None, num=None):
    ppr = ""
    if stil or num:
        ppr = "<w:pPr>" + (f'<w:pStyle w:val="{stil}"/>' if stil else "") + (
            f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num}"/></w:numPr>' if num else "") + "</w:pPr>"
    return f"<w:p>{ppr}<w:r><w:t xml:space=\"preserve\">{text}</w:t></w:r></w:p>"


def test_word_neu_und_wieder_gelesen():
    md = ("# Bewerbung\n\nSehr geehrte **Frau Müller**,\n\n## Daten\n\n"
          "| Feld | Wert |\n|---|---|\n| Ort | Köln |\n\n- eins\n- zwei\n\n3. drei\n4. vier\n\n你好")
    roh = word_datei.erzeugen("Bewerbung", md)
    r = word_datei.lesen(roh)
    assert r["ueberschriften"] == ["Bewerbung", "Daten"] and r["tabellen"] == 1
    for stueck in ("# Bewerbung", "## Daten", "Sehr geehrte Frau Müller,", "| Ort | Köln |",
                   "- eins", "3. drei", "4. vier", "你好"):
        assert stueck in r["text"], stueck
    with zipfile.ZipFile(io.BytesIO(roh)) as z:
        assert "word/numbering.xml" in z.namelist()
        assert b"Bewerbung" in z.read("docProps/core.xml")


def test_deutsches_word_ueberschriften_listen_und_aenderungsverfolgung():
    body = (_p("Kapitel", "berschrift1") + _p("erstens", num="1") + _p("zweitens", num="1")
            + '<w:p><w:r><w:t>Alt</w:t></w:r><w:del><w:r><w:delText>weg</w:delText></w:r></w:del>'
              '<w:ins><w:r><w:t>neu</w:t></w:r></w:ins></w:p>'
            + '<w:p><w:r><mc:AlternateContent xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006">'
              '<mc:Choice Requires="wps"><w:t>Kasten</w:t></mc:Choice><mc:Fallback><w:t>Kasten</w:t>'
              '</mc:Fallback></mc:AlternateContent></w:r><w:r><w:t>Danach</w:t></w:r></w:p>')
    r = word_datei.lesen(deutsches_docx(body))
    assert "# Kapitel" in r["text"] and "1. erstens" in r["text"] and "2. zweitens" in r["text"]
    assert "Altneu" in r["text"] and "weg" not in r["text"]
    assert "Kasten" not in r["text"] and "Danach" in r["text"]
    assert any("Änderungsverfolgung" in h for h in r["hinweise"])


def test_ersetzen_ueber_lauf_grenzen_und_in_der_kopfzeile():
    body = ('<w:p><w:r><w:t>Sehr geehrte Frau Mü</w:t></w:r><w:r><w:rPr><w:b/></w:rPr>'
            '<w:t>ller,</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>Frau</w:t></w:r><w:r><w:tab/></w:r><w:r><w:t>Müller</w:t></w:r></w:p>')
    original = deutsches_docx(body, kopfzeile="Brief an Frau Müller")
    vorher = bytes(original)
    neu, bericht = word_datei.aendern(original, [("Frau Müller", "Herrn Kurz"), ("fehlt", "x")])
    assert original == vorher                       # das Original bleibt
    assert bericht["ersetzt"] == [("Frau Müller", 2, 0), ("fehlt", 0, 0)]
    r = word_datei.lesen(neu)
    assert "Sehr geehrte Herrn Kurz," in r["text"] and "Frau\tMüller" in r["text"]
    with zipfile.ZipFile(io.BytesIO(neu)) as z:
        assert "Herrn Kurz" in z.read("word/header1.xml").decode()
    # über einen Tab hinweg wird ausgelassen und gemeldet
    _, b = word_datei.aendern(original, [("Frau\tMüller", "x")])
    assert b["ersetzt"][0][1] == 0


def test_anhaengen_nimmt_die_stile_des_dokuments_und_haelt_die_form():
    neu, b = word_datei.aendern(deutsches_docx(_p("Text")),
                                anhaengen="# Neu\n\n## Unter\n\n- a\n- b\n\n| x | y |\n|---|---|\n| 1 | 2 |")
    assert b["angehaengt"] >= 5
    with zipfile.ZipFile(io.BytesIO(neu)) as z:
        doc = z.read("word/document.xml").decode()
        stile = z.read("word/styles.xml").decode()
        nummern = z.read("word/numbering.xml").decode()
    assert 'w:val="berschrift1"' in doc                         # vorhandener Stil
    assert 'w:styleId="Heading2"' in stile and '<w:basedOn w:val="Standard"' in stile
    assert 'xmlns:w14=' in doc.split(">", 2)[1]                # für mc:Ignorable
    assert nummern.rindex("<w:abstractNum ") < nummern.index("<w:num ")
    r = word_datei.lesen(neu)
    assert "# Neu" in r["text"] and "## Unter" in r["text"] and "- a" in r["text"]
    assert r["text"].index("Text") < r["text"].index("# Neu")


@pytest.mark.parametrize("daten,muster", [
    (b"\xd0\xcf\x11\xe0" + b"\x00" * 100, ".doc"),
    (b"PK\x03\x04kaputt", "keine lesbare"),
    (b"", "leer"),
])
def test_word_fehlerfaelle(daten, muster):
    with pytest.raises(word_datei.Fehler, match=muster):
        word_datei.lesen(daten)


def test_zip_ohne_dokument_und_zip_bombe(monkeypatch):
    aus = io.BytesIO()
    with zipfile.ZipFile(aus, "w") as z:
        z.writestr("hallo.txt", "x")
    with pytest.raises(word_datei.Fehler, match="keine Word-Datei"):
        word_datei.lesen(aus.getvalue())
    monkeypatch.setattr(word_datei, "MAX_ENTPACKT", 500)
    with pytest.raises(word_datei.Fehler, match="entpackt"):
        word_datei.lesen(deutsches_docx(_p("x" * 1000)))


def test_aendern_ohne_auftrag_und_mit_leerem_suchtext():
    roh = deutsches_docx(_p("Text"))
    with pytest.raises(word_datei.Fehler):
        word_datei.aendern(roh)
    with pytest.raises(word_datei.Fehler, match="leerer Suchtext"):
        word_datei.aendern(roh, [("", "x")])
