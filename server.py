#!/usr/bin/env python3
"""Archipelago Game Hub: shared catalogue, player picks, YAML builds and local generation.

Intentionally designed for localhost/trusted LAN. NOT a hardened public-hosting service.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import uuid
import zipfile

from core import (InvalidInput, MAX_APWORLD, MAX_COVER, MAX_YAML,
                  SLOT_PATTERN, make_bundle, validate_apworld, validate_yaml)

ROOT = Path(__file__).resolve().parent
# Optional local config: key=value in .env. Explicit environment variables take priority.
# Do not use this convenience loader for a publicly reachable deployment.
_env_file = ROOT / '.env'
if _env_file.is_file():
    for _line in _env_file.read_text(encoding='utf-8-sig').splitlines():
        _line = _line.strip()
        if not _line or _line.startswith('#') or '=' not in _line: continue
        _key, _value = _line.split('=', 1)
        _key = _key.strip()
        if re.fullmatch(r'[A-Z][A-Z0-9_]*', _key):
            os.environ.setdefault(_key, _value.strip().strip('\"').strip("'"))
DATA = Path(os.environ.get('AP_DATA_DIR', ROOT / 'data')).resolve()
UPLOADS = DATA / 'uploads'
BUILDS = DATA / 'builds'
WEB = ROOT / 'web'
DB_FILE = DATA / 'hub.sqlite3'
BIND = os.environ.get('AP_BIND', '127.0.0.1')
PORT = int(os.environ.get('AP_PORT', 8765))
JOIN_CODE = os.environ.get('AP_JOIN_CODE', '')
BODY_LIMIT = 36 * 1024 * 1024
LOCK = threading.RLock()
GENERATING = {'id': None}
for path in (DATA, UPLOADS, BUILDS): path.mkdir(parents=True, exist_ok=True)


class HubError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def fail(message, status=400): raise HubError(message, status)


def db():
    c = sqlite3.connect(DB_FILE, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c


def init_db():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(
          id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
          pass_hash TEXT NOT NULL, admin INTEGER NOT NULL, joined INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(
          token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          csrf TEXT NOT NULL, expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS games(
          id TEXT PRIMARY KEY, title TEXT NOT NULL, ap_game TEXT NOT NULL,
          description TEXT NOT NULL, guide TEXT NOT NULL, setup_url TEXT NOT NULL,
          mod_url TEXT NOT NULL, genre TEXT NOT NULL, world_filename TEXT,
          cover_type TEXT, warning TEXT NOT NULL, author_id TEXT NOT NULL REFERENCES users(id),
          created INTEGER NOT NULL, updated INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS rounds(
          id TEXT PRIMARY KEY, title TEXT NOT NULL, created INTEGER NOT NULL,
          owner_id TEXT NOT NULL REFERENCES users(id), room_url TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS picks(
          round_id TEXT NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
          user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          game_id TEXT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
          PRIMARY KEY(round_id,user_id));
        CREATE TABLE IF NOT EXISTS builds(
          id TEXT PRIMARY KEY, round_id TEXT NOT NULL REFERENCES rounds(id),
          created INTEGER NOT NULL, status TEXT NOT NULL, filename TEXT NOT NULL DEFAULT '',
          log TEXT NOT NULL DEFAULT '', manifest TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')


def asdict(row): return dict(row) if row is not None else None


def auth_password(password):
    salt = secrets.token_bytes(16)
    d = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 290000)
    return salt.hex() + ':' + d.hex()


def verify_password(stored, password):
    try:
        salt, digest = stored.split(':')
        d = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 290000)
        return hmac.compare_digest(d, bytes.fromhex(digest))
    except (ValueError, TypeError):
        return False


def new_session(user_id):
    token = secrets.token_urlsafe(35)
    with db() as c:
        c.execute('DELETE FROM sessions WHERE expires < ?', (int(time.time()),))
        c.execute('INSERT INTO sessions VALUES(?,?,?,?)',
                  (hashlib.sha256(token.encode()).hexdigest(), user_id,
                   secrets.token_urlsafe(25), int(time.time()) + 14*86400))
    return token


def session_from(headers):
    cookie = SimpleCookie()
    try: cookie.load(headers.get('Cookie', ''))
    except Exception: return None
    obj = cookie.get('ap_hub')
    if not obj: return None
    hashed = hashlib.sha256(obj.value.encode()).hexdigest()
    with db() as c:
        row = c.execute('''SELECT u.id,u.username,u.admin,s.csrf FROM sessions s
           JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?''',
           (hashed, int(time.time()))).fetchone()
    return asdict(row)


def unpack_file(value, kind, required=False):
    if not value:
        if required: fail(f'Bitte {kind} hochladen.')
        return None
    if not isinstance(value, dict): fail('Ungültiger Datei-Upload.')
    name = str(value.get('name','')).replace('\\','/').split('/')[-1]
    if not name or len(name) > 140 or any(ord(x) < 32 for x in name): fail('Ungültiger Dateiname.')
    try: body = base64.b64decode(value.get('data',''), validate=True)
    except (ValueError, TypeError): fail('Die Datei ist nicht gültig kodiert.')
    maximum = {'yaml': MAX_YAML, 'apworld': MAX_APWORLD, 'cover': MAX_COVER}[kind]
    if not body or len(body) > maximum: fail(f'{kind}-Datei fehlt oder ist zu groß.')
    return name, body


def validate_cover(name, contents):
    if name.lower().endswith('.png') and contents.startswith(b'\x89PNG\r\n\x1a\n'): return 'image/png'
    if name.lower().endswith(('.jpg','.jpeg')) and contents.startswith(b'\xff\xd8\xff'): return 'image/jpeg'
    if name.lower().endswith('.webp') and contents.startswith(b'RIFF') and contents[8:12] == b'WEBP': return 'image/webp'
    fail('Cover muss PNG, JPG oder WEBP sein.')


def valid_url(url, optional=True):
    url = str(url or '').strip()
    if not url and optional: return ''
    parsed = urlsplit(url)
    if parsed.scheme not in ('https','http') or not parsed.netloc or len(url) > 450:
        fail('Links müssen vollständige http(s)-URLs sein.')
    return url


def installation():
    with db() as c:
        config = c.execute('SELECT value FROM config WHERE key=?', ('ap_dir',)).fetchone()
    raw = os.environ.get('ARCHIPELAGO_DIR') or (config['value'] if config else '')
    if not raw and os.name == 'nt': raw = r'C:\ProgramData\Archipelago'
    p = Path(raw).expanduser().resolve() if raw else None
    return p if p and p.is_dir() else None


def generator_command(path):
    if not path: return None
    exe = path / 'ArchipelagoGenerate.exe'
    if exe.is_file(): return [str(exe)]
    script = path / 'Generate.py'
    if script.is_file(): return [sys.executable, str(script)]
    return None


def filedir(gameid): return UPLOADS / gameid


def selected(round_id):
    with db() as c:
        rows = c.execute('''SELECT p.game_id, u.username, g.title, g.ap_game,
                        g.world_filename, g.setup_url, g.mod_url, g.guide
            FROM picks p JOIN users u ON u.id=p.user_id
            JOIN games g ON g.id=p.game_id
            WHERE p.round_id=? ORDER BY lower(u.username)''', (round_id,)).fetchall()
    return [dict(r) for r in rows]


def get_bundle(round_id):
    picks = selected(round_id)
    return make_bundle(picks, lambda gameid: (filedir(gameid)/'options.yaml').read_bytes(),
                       lambda gameid: (filedir(gameid)/'world.apworld').read_bytes())


def job_generate(build_id, round_id, apdir, command, approved):
    build_folder = BUILDS / build_id
    try:
        bundle, manifest = get_bundle(round_id)
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            pdir = build_folder / 'Players'
            pdir.mkdir()
            for file in archive.namelist():
                if file.startswith('Players/') and file.endswith('.yaml'):
                    (pdir / Path(file).name).write_bytes(archive.read(file))
            worlds = [x for x in archive.namelist() if x.startswith('custom_worlds/') and x.endswith('.apworld')]
            if worlds and not approved:
                raise InvalidInput('Custom APWorlds müssen vom Host ausdrücklich freigegeben werden.')
            for world in worlds:
                name = Path(world).name
                payload = archive.read(world)
                validate_apworld(payload, name)
                cwdir = apdir / 'custom_worlds'
                cwdir.mkdir(exist_ok=True)
                destination = cwdir / name
                if destination.exists():
                    if hashlib.sha256(destination.read_bytes()).hexdigest() != hashlib.sha256(payload).hexdigest():
                        raise InvalidInput(f'Andere Version von {name} bereits im custom_worlds-Ordner. Bitte manuell abgleichen.')
                else:
                    destination.write_bytes(payload)
        process_args = [*command, '--player_files_path', str(pdir),
                        '--outputpath', str(build_folder), '--multi', str(len(manifest['slots']))]
        result = subprocess.run(process_args, cwd=apdir, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, errors='replace', timeout=900)
        log = (result.stdout or '')[-36000:]
        (build_folder / 'generation.log').write_text(log, encoding='utf-8')
        outputs = sorted(build_folder.glob('AP_*.zip'), key=lambda f:f.stat().st_mtime, reverse=True)
        if result.returncode or not outputs:
            raise InvalidInput('Archipelago-Generierung fehlgeschlagen.\n' + log[-8500:])
        with db() as c:
            c.execute('UPDATE builds SET status=?, filename=?, log=?, manifest=? WHERE id=?',
                      ('success',outputs[0].name,log,json.dumps(manifest,ensure_ascii=False),build_id))
    except Exception as exc:
        with db() as c:
            c.execute('UPDATE builds SET status=?, log=? WHERE id=?',('failed',str(exc)[-14000:],build_id))
    finally:
        with LOCK:
            if GENERATING['id']==build_id: GENERATING['id']=None


def state(sess):
    with db() as c:
        users = [dict(r) for r in c.execute('SELECT id,username,admin FROM users ORDER BY lower(username)')]
        games = [dict(r) for r in c.execute('SELECT * FROM games ORDER BY lower(title), updated DESC')]
        rounds = [dict(r) for r in c.execute('SELECT * FROM rounds ORDER BY created DESC LIMIT 20')]
        picks = [dict(r) for r in c.execute('SELECT * FROM picks')]
        builds = [dict(r) for r in c.execute('SELECT id,round_id,status,filename,created FROM builds ORDER BY created DESC LIMIT 20')]
    for g in games:
        folder = filedir(g['id'])
        yaml_file = folder / 'options.yaml'
        world_file = folder / 'world.apworld'
        g['has_yaml'] = yaml_file.is_file()
        g['yaml_size'] = yaml_file.stat().st_size if g['has_yaml'] else 0
        g['has_apworld'] = bool(g['world_filename'] and world_file.is_file())
        g['apworld_size'] = world_file.stat().st_size if g['has_apworld'] else 0
        g['has_cover'] = bool(g['cover_type'] and (folder / 'cover').is_file())
        g.pop('cover_type',None)
    ap = installation()
    return {'user':{'id':sess['id'],'username':sess['username'],'admin':bool(sess['admin'])},
            'csrf':sess['csrf'],'players':users,'games':games,'rounds':rounds,
            'picks':picks,'builds':builds,
            'config':{'archipelago_dir':str(ap) if ap else '',
                      'generator_available':bool(generator_command(ap)),
                      'group_code_required':bool(JOIN_CODE)},
            'generation_active':GENERATING['id']}


class Handler(BaseHTTPRequestHandler):
    server_version = 'ArchipelagoGameHub/0.2'

    def send_data(self, status=200, body=None, content_type='application/json; charset=utf-8', headers=None):
        if isinstance(body, (dict,list)):
            body=json.dumps(body,ensure_ascii=False).encode('utf-8')
        elif isinstance(body, str): body=body.encode('utf-8')
        elif body is None: body=b''
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store' if content_type.startswith('application/json') else 'private, max-age=120')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','same-origin')
        if headers:
            for k,v in headers.items(): self.send_header(k,v)
        self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError): pass

    def read_json(self):
        if not self.headers.get('Content-Type','').startswith('application/json'):
            fail('Bitte JSON senden.',415)
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length < 0 or length > BODY_LIMIT: fail('Anfrage zu groß.',413)
            raw=self.rfile.read(length)
            obj=json.loads(raw)
            if not isinstance(obj,dict): fail('Ungültiges JSON.')
            return obj
        except (ValueError, json.JSONDecodeError): fail('Ungültiges JSON.')

    def require_session(self, write=False, admin=False):
        sess=session_from(self.headers)
        if not sess: fail('Bitte zuerst anmelden.',401)
        if admin and not sess['admin']: fail('Nur der Host darf diese Aktion ausführen.',403)
        if write:
            expected=self.headers.get('X-CSRF-Token','')
            if not expected or not hmac.compare_digest(expected,sess['csrf']): fail('Ungültiger CSRF-Schutz.',403)
        return sess

    def check_origin(self):
        origin=self.headers.get('Origin')
        if origin and urlsplit(origin).netloc != self.headers.get('Host'):
            fail('Anfrage von einer fremden Website blockiert.',403)

    def auth(self, endpoint, data):
        if endpoint=='register':
            username=str(data.get('username','')).strip()
            password=str(data.get('password',''))
            if not SLOT_PATTERN.fullmatch(username) or username != username.strip() or not username or username.casefold() == 'archipelago':
                fail('Name muss 1–16 Zeichen haben: Buchstaben, Zahlen, Leerzeichen, _, -, . und darf nicht Archipelago heißen.')
            if len(password)<8 or len(password)>128: fail('Passwort muss 8–128 Zeichen haben.')
            with LOCK:
                with db() as c:
                    first=c.execute('SELECT count(*) AS n FROM users').fetchone()['n']==0
                    if not first and JOIN_CODE and not hmac.compare_digest(str(data.get('join_code','')), JOIN_CODE):
                        fail('Falscher Gruppencode.',403)
                    identifier=uuid.uuid4().hex
                    try:
                        c.execute('INSERT INTO users VALUES(?,?,?,?,?)',
                            (identifier,username,auth_password(password),int(first),int(time.time())))
                    except sqlite3.IntegrityError: fail('Name ist bereits vergeben.')
            token=new_session(identifier)
            self.send_data(200,{'ok':True},'application/json; charset=utf-8',
                {'Set-Cookie':f'ap_hub={token}; Path=/; HttpOnly; SameSite=Lax' + ('; Secure' if os.getenv('AP_SECURE_COOKIES')=='1' else '')})
            return
        if endpoint=='login':
            username=str(data.get('username',''))
            password=str(data.get('password',''))
            with db() as c:
                row=c.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
            if not row or not verify_password(row['pass_hash'], password): fail('Name oder Passwort falsch.',401)
            token=new_session(row['id'])
            self.send_data(200,{'ok':True},headers={'Set-Cookie':f'ap_hub={token}; Path=/; HttpOnly; SameSite=Lax' + ('; Secure' if os.getenv('AP_SECURE_COOKIES')=='1' else '')})
            return
        fail('Nicht gefunden.',404)

    def save_game(self, sess, data, old):
        title=str(data.get('title', old['title'] if old else '')).strip()
        description=str(data.get('description', old['description'] if old else '')).strip()
        guide=str(data.get('guide', old['guide'] if old else '')).strip()
        genre=str(data.get('genre', old['genre'] if old else '')).strip()
        setup_url=valid_url(data.get('setup_url', old['setup_url'] if old else ''))
        mod_url=valid_url(data.get('mod_url', old['mod_url'] if old else ''))
        if not (1<=len(title)<=90) or len(description)>400 or len(guide)>4000 or len(genre)>50:
            fail('Bitte die Textfelder kürzen (Titel 90, Text 400, Anleitung 4000 Zeichen).')
        upload_yaml=unpack_file(data.get('yaml'),'yaml',not bool(old))
        upload_world=unpack_file(data.get('apworld'),'apworld')
        upload_cover=unpack_file(data.get('cover'),'cover')
        if upload_yaml:
            if not upload_yaml[0].lower().endswith(('.yaml','.yml')): fail('YAML-Datei benötigt .yaml oder .yml.')
            ap_game, _ = validate_yaml(upload_yaml[1])
        else:
            ap_game=old['ap_game']
        world_name=old['world_filename'] if old else None
        warning=''
        if upload_world:
            world_name=upload_world[0]
            _,warning=validate_apworld(upload_world[1],world_name)
        if data.get('remove_apworld'): world_name=None
        cover_type=old['cover_type'] if old else None
        if upload_cover: cover_type=validate_cover(*upload_cover)
        if data.get('remove_cover'): cover_type=None
        game_id=old['id'] if old else uuid.uuid4().hex
        folder=filedir(game_id)
        folder.mkdir(parents=True, exist_ok=True)
        if upload_yaml: (folder/'options.yaml').write_bytes(upload_yaml[1])
        if upload_world: (folder/'world.apworld').write_bytes(upload_world[1])
        if data.get('remove_apworld'): (folder/'world.apworld').unlink(missing_ok=True)
        if upload_cover: (folder/'cover').write_bytes(upload_cover[1])
        if data.get('remove_cover'): (folder/'cover').unlink(missing_ok=True)
        stamp=int(time.time())
        with db() as c:
            if old:
                c.execute('''UPDATE games SET title=?,ap_game=?,description=?,guide=?,setup_url=?,
                  mod_url=?,genre=?,world_filename=?,cover_type=?,warning=?,updated=? WHERE id=?''',
                  (title,ap_game,description,guide,setup_url,mod_url,genre,world_name,cover_type,warning,stamp,game_id))
            else:
                c.execute('''INSERT INTO games VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (game_id,title,ap_game,description,guide,setup_url,mod_url,genre,
                   world_name,cover_type,warning,sess['id'],stamp,stamp))
        return {'ok':True,'game_id':game_id, 'warning':warning}

    def api(self, method, path):
        if path in ('/api/auth/register','/api/auth/login') and method=='POST':
            return self.auth(path.split('/')[-1],self.read_json())
        sess=self.require_session(method in ('POST','DELETE'))
        if path=='/api/state' and method=='GET': return self.send_data(200,state(sess))
        if path=='/api/auth/logout' and method=='POST':
            cookie=SimpleCookie();cookie.load(self.headers.get('Cookie',''))
            obj=cookie.get('ap_hub')
            if obj:
                with db() as c:c.execute('DELETE FROM sessions WHERE token_hash=?',
                    (hashlib.sha256(obj.value.encode()).hexdigest(),))
            return self.send_data(200,{'ok':True},headers={'Set-Cookie':'ap_hub=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax'})
        if path=='/api/games' and method=='POST':
            return self.send_data(200,self.save_game(sess,self.read_json(),None))
        m=re.fullmatch(r'/api/games/([a-f0-9]{32})',path)
        if m and method in ('POST','DELETE'):
            gid=m.group(1)
            with db() as c:game=c.execute('SELECT * FROM games WHERE id=?',(gid,)).fetchone()
            if not game: fail('Spiel nicht vorhanden.',404)
            if not sess['admin'] and sess['id']!=game['author_id']: fail('Nur Autor oder Host darf bearbeiten.',403)
            if method=='POST':return self.send_data(200,self.save_game(sess,self.read_json(),game))
            with db() as c:c.execute('DELETE FROM games WHERE id=?',(gid,))
            shutil.rmtree(filedir(gid),ignore_errors=True)
            return self.send_data(200,{'ok':True})
        m=re.fullmatch(r'/api/games/([a-f0-9]{32})/(yaml|apworld)',path)
        if m and method=='GET':
            gid, kind = m.groups()
            with db() as c:
                row=c.execute('SELECT world_filename FROM games WHERE id=?',(gid,)).fetchone()
            if not row: fail('Spiel nicht vorhanden.',404)
            if kind == 'apworld' and not row['world_filename']:
                fail('Für dieses Spiel wurde keine Custom APWorld hinterlegt.',404)
            filename = 'options.yaml' if kind == 'yaml' else row['world_filename']
            stored = filedir(gid) / ('options.yaml' if kind == 'yaml' else 'world.apworld')
            if not stored.is_file(): fail('Hochgeladene Datei fehlt auf dem Server.',404)
            return self.send_data(200,stored.read_bytes(),'application/octet-stream',
                                  {'Content-Disposition':f'attachment; filename="{filename}"'})
        m=re.fullmatch(r'/api/games/([a-f0-9]{32})/cover',path)
        if m and method=='GET':
            with db() as c:row=c.execute('SELECT cover_type FROM games WHERE id=?',(m.group(1),)).fetchone()
            if not row or not row['cover_type']: fail('Kein Cover.',404)
            return self.send_data(200,(filedir(m.group(1))/'cover').read_bytes(),row['cover_type'])
        if path=='/api/rounds' and method=='POST':
            if not sess['admin']: fail('Nur Host.',403)
            title=str(self.read_json().get('title','Neue Runde')).strip()[:85]
            rid=uuid.uuid4().hex
            with db() as c:c.execute('INSERT INTO rounds(id,title,created,owner_id) VALUES(?,?,?,?)',
                                    (rid,title or 'Neue Runde',int(time.time()),sess['id']))
            return self.send_data(200,{'ok':True,'id':rid})
        if path=='/api/picks' and method=='POST':
            payload=self.read_json()
            rid=str(payload.get('round_id','')); gid=str(payload.get('game_id',''))
            with db() as c:
                if not c.execute('SELECT id FROM rounds WHERE id=?',(rid,)).fetchone():fail('Runde nicht vorhanden.',404)
                if gid and not c.execute('SELECT id FROM games WHERE id=?',(gid,)).fetchone():fail('Spiel nicht vorhanden.',404)
                if gid:
                    c.execute('''INSERT INTO picks VALUES(?,?,?) ON CONFLICT(round_id,user_id)
                               DO UPDATE SET game_id=excluded.game_id''',(rid,sess['id'],gid))
                else:c.execute('DELETE FROM picks WHERE round_id=? AND user_id=?',(rid,sess['id']))
            return self.send_data(200,{'ok':True})
        m=re.fullmatch(r'/api/rounds/([a-f0-9]{32})/bundle',path)
        if m and method=='GET':
            with db() as c:
                if not c.execute('SELECT id FROM rounds WHERE id=?',(m.group(1),)).fetchone():fail('Runde nicht vorhanden.',404)
            output, _=get_bundle(m.group(1))
            return self.send_data(200,output,'application/zip',
                     {'Content-Disposition':'attachment; filename="Archipelago_Rundenpaket.zip"'})
        m=re.fullmatch(r'/api/rounds/([a-f0-9]{32})/generate',path)
        if m and method=='POST':
            if not sess['admin']: fail('Nur Host darf Seeds erzeugen.',403)
            payload=self.read_json()
            rid=m.group(1)
            with db() as c:
                if not c.execute('SELECT id FROM rounds WHERE id=?',(rid,)).fetchone(): fail('Runde fehlt.',404)
            apdir=installation();cmd=generator_command(apdir)
            if not cmd: fail('Archipelago-Generator fehlt. Host: Installationspfad eintragen.')
            bundle,manifest=get_bundle(rid)
            approved=payload.get('approve_custom_worlds') is True
            if manifest['apworlds'] and not approved:
                fail('Custom APWorlds benötigen vor der Generierung deine ausdrückliche Freigabe.')
            with LOCK:
                if GENERATING['id']:fail('Es läuft bereits eine Generierung.',409)
                bid=uuid.uuid4().hex
                (BUILDS/bid).mkdir(parents=True,exist_ok=True)
                with db() as c:c.execute('INSERT INTO builds(id,round_id,created,status) VALUES(?,?,?,?)',
                                        (bid,rid,int(time.time()),'generating'))
                GENERATING['id']=bid
                threading.Thread(target=job_generate,
                    args=(bid,rid,apdir,cmd,approved),daemon=True).start()
            return self.send_data(202,{'ok':True,'build_id':bid})
        m=re.fullmatch(r'/api/builds/([a-f0-9]{32})/(download|log)',path)
        if m and method=='GET':
            bid, action=m.group(1),m.group(2)
            with db() as c:build=c.execute('SELECT * FROM builds WHERE id=?',(bid,)).fetchone()
            if not build:fail('Build nicht vorhanden.',404)
            if action=='log':return self.send_data(200,{'status':build['status'],'log':build['log']})
            if build['status']!='success': fail('Seed noch nicht fertig.',409)
            archive=BUILDS/bid/build['filename']
            if not archive.is_file():fail('Seed-Datei fehlt.',404)
            return self.send_data(200,archive.read_bytes(),'application/zip',
                   {'Content-Disposition':f'attachment; filename="{build["filename"]}"'})
        m=re.fullmatch(r'/api/rounds/([a-f0-9]{32})/room',path)
        if m and method=='POST':
            if not sess['admin']:fail('Nur der Host kann Raum-Links setzen.',403)
            link=valid_url(self.read_json().get('url',''))
            host=urlsplit(link).hostname
            if host not in ('archipelago.gg','www.archipelago.gg'):
                fail('Bitte einen Raum-Link von archipelago.gg verwenden.')
            with db() as c:c.execute('UPDATE rounds SET room_url=? WHERE id=?',(link,m.group(1)))
            return self.send_data(200,{'ok':True})
        if path=='/api/settings' and method=='POST':
            if not sess['admin']:fail('Nur der Host.',403)
            folder=str(self.read_json().get('directory','')).strip()
            if folder:
                if not generator_command(Path(folder).expanduser().resolve()):
                    fail('Ordner enthält keinen ArchipelagoGenerate.exe oder Generate.py.')
            with db() as c:
                c.execute('''INSERT INTO config(key,value) VALUES('ap_dir',?)
                        ON CONFLICT(key) DO UPDATE SET value=excluded.value''',(folder,))
            return self.send_data(200,{'ok':True})
        fail('Unbekannte API-Route.',404)

    def handle_request(self,method):
        try:
            if method in ('POST','DELETE'):self.check_origin()
            path=urlsplit(self.path).path
            if path.startswith('/api/'):return self.api(method,path)
            if method!='GET':fail('Nicht gefunden.',404)
            known={'/':'index.html','/index.html':'index.html',
                   '/app.js':'app.js','/styles.css':'styles.css'}
            if path not in known:fail('Nicht gefunden.',404)
            p=WEB/known[path]
            kind='text/html; charset=utf-8' if p.suffix=='.html' else 'text/css; charset=utf-8' if p.suffix=='.css' else 'application/javascript; charset=utf-8'
            self.send_data(200,p.read_bytes(),kind)
        except (HubError,InvalidInput) as e:
            self.send_data(getattr(e,'status',400),{'error':str(e)})
        except Exception:
            traceback.print_exc()
            self.send_data(500,{'error':'Interner Fehler. Bitte Server-Log prüfen.'})

    def do_GET(self):self.handle_request('GET')
    def do_POST(self):self.handle_request('POST')
    def do_DELETE(self):self.handle_request('DELETE')


if __name__=='__main__':
    init_db()
    print(f'Archipelago Game Hub: http://localhost:{PORT}')
    print('Verzeichnis:',DATA)
    if BIND!='127.0.0.1': print('ACHTUNG: Nur in vertrauenswürdigen Netzwerken betreiben; kein öffentliches Hosting ohne Härtung.')
    httpd=ThreadingHTTPServer((BIND,PORT),Handler)
    try:httpd.serve_forever()
    except KeyboardInterrupt:pass
    finally:httpd.server_close()
