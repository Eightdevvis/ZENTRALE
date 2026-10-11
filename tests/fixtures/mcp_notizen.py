#!/usr/bin/env python3
"""Ein winziger MCP-Server (stdio) für die Tests der Anbindungs-Pipe.

Ein Notiz-Speicher im Arbeitsspeicher: create_note, get_note, update_note,
delete_note, restore_note (Notiz mit bekannter id zurückholen), list_notes,
dazu purge_note (löscht ohne Wiederherstellen — Stufe „einmalig"). Spricht
Zeilen-JSON-RPC wie das Model Context Protocol: initialize, tools/list,
tools/call. Kein Paket, keine Datei, kein Netz.

Fehler wie bei echten Servern: ein unbekanntes Werkzeug ist ein JSON-RPC-Fehler,
ein fachlicher Fehler (Notiz gibt es nicht) ein Ergebnis mit isError. Startet
man ihn mit NOTIZEN_FEHLER=1, verfälscht get_note den Titel (großgeschrieben) —
so prüft ein Test, dass die Schutzschicht zurücknimmt, was nicht stimmt.
"""
import json
import os
import sys

NOTIZEN = {}
NAECHSTE = [1]
VERFAELSCHEN = os.environ.get("NOTIZEN_FEHLER") == "1"


def schema(felder, pflicht=()):
    return {"type": "object", "properties": felder, "required": list(pflicht)}


TITEL = {"type": "string"}
TEXT = {"type": "string"}
TAGS = {"type": "array", "items": {"type": "string"}}
ID = {"type": "string"}

WERKZEUGE = [
    {"name": "create_note", "description": "Legt eine Notiz an.",
     "inputSchema": schema({"title": TITEL, "text": TEXT, "tags": TAGS}, ["title"])},
    {"name": "get_note", "description": "Liest eine Notiz.",
     "inputSchema": schema({"id": ID}, ["id"]), "annotations": {"readOnlyHint": True}},
    {"name": "update_note", "description": "Ändert eine Notiz.",
     "inputSchema": schema({"id": ID, "title": TITEL, "text": TEXT, "tags": TAGS}, ["id"])},
    {"name": "delete_note", "description": "Löscht eine Notiz.",
     "inputSchema": schema({"id": ID}, ["id"]), "annotations": {"destructiveHint": True}},
    {"name": "restore_note", "description": "Holt eine gelöschte Notiz mit ihrer id zurück.",
     "inputSchema": schema({"id": ID, "title": TITEL, "text": TEXT, "tags": TAGS}, ["id", "title"])},
    {"name": "purge_note", "description": "Löscht endgültig.",
     "inputSchema": schema({"id": ID}, ["id"]), "annotations": {"destructiveHint": True}},
    {"name": "list_notes", "description": "Alle Notizen.",
     "inputSchema": schema({"suche": {"type": "string"}}), "annotations": {"readOnlyHint": True}},
]


def fehler(text):
    return {"content": [{"type": "text", "text": text}], "isError": True}


def ergebnis(daten):
    return {"content": [{"type": "text", "text": json.dumps(daten, ensure_ascii=False)}],
            "structuredContent": daten, "isError": False}


def aufrufen(name, a):
    if name == "create_note":
        nid = f"n{NAECHSTE[0]}"
        NAECHSTE[0] += 1
        NOTIZEN[nid] = {"id": nid, "title": a["title"], "text": a.get("text", ""), "tags": a.get("tags", [])}
        return ergebnis({"id": nid})
    if name == "restore_note":
        NOTIZEN[a["id"]] = {"id": a["id"], "title": a["title"], "text": a.get("text", ""),
                            "tags": a.get("tags", [])}
        return ergebnis({"id": a["id"]})
    if name in ("get_note", "update_note", "delete_note", "purge_note"):
        n = NOTIZEN.get(a["id"])
        if n is None:
            return fehler(f"Note not found: {a['id']}")
        if name == "get_note":
            n = dict(n)
            if VERFAELSCHEN:
                n["title"] = n["title"].upper()
            return ergebnis(n)
        if name == "update_note":
            for k in ("title", "text", "tags"):
                if k in a:
                    n[k] = a[k]
            return ergebnis({"id": n["id"]})
        del NOTIZEN[a["id"]]
        return ergebnis({"deleted": a["id"]})
    if name == "list_notes":
        such = (a.get("suche") or "").lower()
        return ergebnis({"notes": [n for n in NOTIZEN.values() if such in n["title"].lower()]})
    return None


def antworten(msg):
    methode, mid = msg.get("method"), msg.get("id")
    if mid is None:
        return None                         # Benachrichtigung
    if methode == "initialize":
        res = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
               "serverInfo": {"name": "notizen-fake", "version": "0"}}
    elif methode == "tools/list":
        res = {"tools": WERKZEUGE}
    elif methode == "tools/call":
        p = msg.get("params") or {}
        res = aufrufen(p.get("name"), p.get("arguments") or {})
        if res is None:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"Unknown tool: {p.get('name')}"}}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "Method not found"}}
    return {"jsonrpc": "2.0", "id": mid, "result": res}


def main():
    for zeile in sys.stdin:
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            msg = json.loads(zeile)
        except ValueError:
            continue
        a = antworten(msg)
        if a is not None:
            sys.stdout.write(json.dumps(a, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
