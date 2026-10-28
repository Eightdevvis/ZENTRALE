// Was das Handy aus der Mitte holt und was es bringen darf — die EINE Stelle
// dafür, Spiegel der Rechner-Seite (core/abgleich.eigene_datei,
// core/abgleich_vorschlaege) und der Doku (memory/betrieb/abgleich_fremde_knoten.md,
// „Format für fremde Knoten“).
//
// Hier liegt auch die Übersetzung der Pfade: die Mitte zählt ab dem
// ZENTRALE-Ordner („data/gespraeche/…“), die Ablage des Handys ab data/
// („gespraeche/…“).

const knotenName = 'handy';

/// Ablage-Pfad → Pfad in der Mitte.
String mittePfad(String ablagePfad) => 'data/$ablagePfad';

/// Pfad in der Mitte → Ablage-Pfad (null = liegt nicht unter data/).
String? ablagePfad(String mittePfad) =>
    mittePfad.startsWith('data/') ? mittePfad.substring(5) : null;

bool _kalenderDatei(String ap) {
  final t = ap.split('/');
  if (t.length != 3 || t[0] != 'kalender' || t[2].startsWith('.')) return false;
  return t[2].endsWith('.ics') || t[2] == 'color' || t[2] == 'displayname';
}

/// Holt das Handy diese Datei (Ablage-Pfad)? Gespräche, Kontextpaket,
/// Kalender (Termine + Namen/Farben der Ebenen), Zugangsdaten des Adapters
/// (je Eintrag mit dem Kontoschlüssel verschlüsselt — der Claude-Schlüssel).
bool holen(String ap) =>
    ap.startsWith('gespraeche/') ||
    ap == 'mobil/kontext.json' ||
    ap == 'adapter/geheim.enc' ||
    _kalenderDatei(ap);

/// Gehört die Datei allein diesem Knoten? (core/abgleich.eigene_datei)
bool eigene(String ap, [String knoten = knotenName]) {
  final t = ap.split('/');
  if (t.length == 3 && t[0] == 'gespraeche') {
    return t[2] == '$knoten.jsonl' || (t[1] == '_knoten' && t[2] == '$knoten.json');
  }
  return ap == 'rueckmeldungen/$knoten.jsonl';
}

/// Kopf eines Gesprächs (Vorschlag, solange die Mitte keinen hat).
bool istKopf(String ap) {
  final t = ap.split('/');
  return t.length == 3 && t[0] == 'gespraeche' && !t[1].startsWith('_') &&
      !t[1].startsWith('.') && t[2] == 'kopf.json';
}

/// Ein Termin (Vorschlag, solange es Pfad und UID nicht gibt).
bool istTermin(String ap) => _kalenderDatei(ap) && ap.endsWith('.ics');
