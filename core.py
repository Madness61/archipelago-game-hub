"""Pure helpers for preparing Archipelago YAMLs and checking uploaded custom worlds."""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile

import yaml

MAX_YAML = 512 * 1024
MAX_APWORLD = 20 * 1024 * 1024
MAX_COVER = 3 * 1024 * 1024
# Archipelago Generate.py truncates slot names to 16 characters. Avoid silent collisions.
SLOT_PATTERN = re.compile(r'^[\w .-]{1,16}$', re.UNICODE)


class InvalidInput(ValueError):
    pass


def validate_yaml(contents: bytes) -> tuple[str, str]:
    if not contents or len(contents) > MAX_YAML:
        raise InvalidInput('Die YAML ist leer oder größer als 512 KB.')
    try:
        source = contents.decode('utf-8-sig')
        docs = list(yaml.safe_load_all(source))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise InvalidInput(f'Ungültige YAML: {exc}') from exc
    if len(docs) != 1 or not isinstance(docs[0], dict):
        raise InvalidInput('Bitte genau ein YAML-Dokument mit game: und name: verwenden.')
    doc = docs[0]
    game = doc.get('game')
    name = doc.get('name')
    if not isinstance(game, str) or not game.strip() or len(game) > 100:
        raise InvalidInput('game: muss ein konkreter Spielname sein (keine gewichtete Auswahl).')
    if not isinstance(name, str) or not name.strip():
        raise InvalidInput('Die Vorlage benötigt ein name:-Feld als Text.')
    if game not in doc or not isinstance(doc[game], dict):
        raise InvalidInput(f'Die YAML benötigt einen Abschnitt {game!r}: mit den Spieleinstellungen.')
    # We edit ONLY a simple, top-level name line, retaining the many settings and comments as-is.
    lines = source.splitlines(keepends=True)
    names = [i for i, line in enumerate(lines) if re.match(r'^name\s*:', line)]
    if len(names) != 1:
        raise InvalidInput('name: muss genau einmal als einfaches Feld auf oberster Ebene stehen.')
    return game.strip(), name.strip()


def render_yaml(contents: bytes, slot: str) -> bytes:
    validate_yaml(contents)
    if (not SLOT_PATTERN.fullmatch(slot) or slot.strip() != slot or not slot.strip()
            or slot.casefold() == 'archipelago'):
        raise InvalidInput('Slotname: 1–16 Zeichen; nur Buchstaben, Zahlen, Leerzeichen, _, -, .; nicht Archipelago.')
    source = contents.decode('utf-8-sig')
    # YAML double-quoted strings use JSON-compatible escaping for these slot names.
    result = re.sub(r'^name\s*:[^\r\n]*(?=\r?$)',
                    lambda _: 'name: ' + json.dumps(slot, ensure_ascii=False),
                    source, count=1, flags=re.MULTILINE)
    if yaml.safe_load(result)['name'] != slot:
        raise InvalidInput('Slotname konnte nicht ersetzt werden.')
    return result.encode('utf-8')


def validate_apworld(contents: bytes, filename: str) -> tuple[str, str]:
    if not re.fullmatch(r'[a-z0-9_]+\.apworld', filename):
        raise InvalidInput('.apworld muss einen kleingeschriebenen Dateinamen aus a-z, 0-9, _ haben.')
    if not contents or len(contents) > MAX_APWORLD:
        raise InvalidInput('APWorld ist leer oder größer als 20 MB.')
    folder = filename[:-8]
    try:
        with zipfile.ZipFile(io.BytesIO(contents)) as archive:
            entries = archive.infolist()
            if len(entries) > 5000 or sum(e.file_size for e in entries) > 150*1024*1024:
                raise InvalidInput('APWorld überschreitet die zulässigen Archivgrenzen.')
            for entry in entries:
                path = entry.filename
                if path.startswith('/') or '\\' in path or '..' in path.split('/'):
                    raise InvalidInput('Unsichere Datei-Pfade im APWorld-Archiv.')
                if entry.compress_size and entry.file_size / entry.compress_size > 1000:
                    raise InvalidInput('Ungewöhnlich stark komprimiertes APWorld-Archiv.')
            if folder + '/__init__.py' not in archive.namelist():
                raise InvalidInput(f'APWorld muss {folder}/__init__.py enthalten.')
            manifest = folder + '/archipelago.json'
            warning = '' if manifest in archive.namelist() else 'Kein archipelago.json vorhanden (mögliche ältere APWorld).'
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise InvalidInput('Datei ist kein gültiges APWorld-ZIP-Archiv.') from exc
    return hashlib.sha256(contents).hexdigest(), warning


def make_bundle(picks: list[dict], get_yaml, get_world) -> tuple[bytes, dict]:
    """picks: [{username, title, game_id, apworld_filename}]; fetch functions are storage-agnostic."""
    if not picks:
        raise InvalidInput('Mindestens ein Spieler muss ein Spiel gewählt haben.')
    slots = set()
    worlds = {}
    manifest = {'slots': [], 'apworlds': []}
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zipout:
        for idx, pick in enumerate(picks, 1):
            slot = pick['username']
            if slot.casefold() in slots:
                raise InvalidInput('Doppelter Slotname.')
            slots.add(slot.casefold())
            yamlbytes = render_yaml(get_yaml(pick['game_id']), slot)
            filename = f'Players/{idx:02d}_{re.sub(r"[^a-zA-Z0-9_.-]", "_", slot)}.yaml'
            zipout.writestr(filename, yamlbytes)
            manifest['slots'].append({'name': slot, 'title': pick['title'], 'filename': filename})
            world = pick.get('apworld_filename')
            if world:
                body = get_world(pick['game_id'])
                checksum, _ = validate_apworld(body, world)
                if world in worlds and worlds[world][0] != checksum:
                    raise InvalidInput(f'Unterschiedliche Versionen der APWorld {world} ausgewählt.')
                worlds[world] = (checksum, body)
        for name, (digest, body) in worlds.items():
            zipout.writestr('custom_worlds/' + name, body)
            manifest['apworlds'].append({'name': name, 'sha256': digest})
        zipout.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        zipout.writestr('README.txt',
             'ARCHIPELAGO RUN BUNDLE\n\nDas Players/-Verzeichnis enthaelt die automatisch pro Spieler umbenannten YAMLs.\n'
             'custom_worlds/ enthaelt gegebenenfalls APWorld-Dateien. Diese koennen Python-Code ausfuehren; nur gepruefte Quellen installieren.\n'
             'Fuehre den Archipelago-Generator aus und lade danach das AP_*.zip auf https://archipelago.gg/uploads hoch.\n')
    return out.getvalue(), manifest
