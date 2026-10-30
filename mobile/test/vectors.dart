// Where the contract vectors live (contracts/README.md): one folder per
// contract and major at the repo root, shared by the core (Python), this app
// and the server — one file, no copies. Tests run with mobile/ as cwd.
const _folder = {
  'konto_testvektoren.json': 'account-keys/1',
  'mitte_testvektoren.json': 'cloud-sync/1',
  'kalender_testvektoren.json': 'calendar-ics/1',
  'kalender_aendern_testvektoren.json': 'calendar-ics/1',
  'calendar_colour_vectors.json': 'calendar-colours/1',
};

String vectorPath(String name) {
  final folder = _folder[name];
  if (folder == null) throw ArgumentError('unknown vector file $name');
  return '../contracts/$folder/$name';
}
