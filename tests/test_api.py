"""Black-box integration: authentication, shared catalog, picks, YAML names and fake generator."""
import base64
from http.cookiejar import CookieJar
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener
import zipfile

import yaml

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0));return s.getsockname()[1]


class Client:
    def __init__(self, port):
        self.base=f'http://127.0.0.1:{port}'
        self.open=build_opener(HTTPCookieProcessor(CookieJar()))
        self.csrf=None

    def request(self,method,path,body=None):
        headers={}
        if body is not None:
            headers['Content-Type']='application/json'
            body=json.dumps(body).encode()
        if method in ('POST','DELETE') and self.csrf:headers['X-CSRF-Token']=self.csrf
        req=Request(self.base+path,data=body,headers=headers,method=method)
        with self.open.open(req,timeout=8) as rsp:
            data=rsp.read()
            if 'application/json' in rsp.headers.get('Content-Type',''):
                return json.loads(data)
            return data

    def state(self):
        result=self.request('GET','/api/state');self.csrf=result['csrf'];return result


class APITests(unittest.TestCase):
    def test_shared_catalog_multiuser_bundle_and_generation(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td);port=free_port()
            env={**os.environ,'AP_PORT':str(port),'AP_BIND':'127.0.0.1','AP_JOIN_CODE':'test-join-code','AP_DATA_DIR':str(home/'data')}
            process=subprocess.Popen([sys.executable,str(ROOT/'server.py')],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            try:
                alice=Client(port); bob=Client(port)
                for _ in range(70):
                    try:
                        alice.request('GET','/');break
                    except URLError: time.sleep(.08)
                else:self.fail('Backend did not start')
                alice.request('POST','/api/auth/register',{'username':'Alice','password':'password-a'})
                a=alice.state();self.assertTrue(a['user']['admin'])
                doc=b'# config retained\nname: Vorlage\ngame: Hollow Knight\nHollow Knight:\n  death_link: false\n'
                b64=lambda name,payload:{'name':name,'data':base64.b64encode(payload).decode()}
                r=alice.request('POST','/api/games',{'title':'Hollow Knight','genre':'Metroidvania','description':'Shared','guide':'1. Install setup','yaml':b64('options.yaml',doc)})
                gid=r['game_id']
                round_id=alice.request('POST','/api/rounds',{'title':'Test World'})['id']
                alice.request('POST','/api/picks',{'round_id':round_id,'game_id':gid})
                bob.request('POST','/api/auth/register',{'username':'Bob','password':'password-b','join_code':'test-join-code'})
                state=bob.state();self.assertFalse(state['user']['admin']);self.assertEqual(gid,state['games'][0]['id'])
                bob.request('POST','/api/picks',{'round_id':round_id,'game_id':gid})
                binary=alice.request('GET',f'/api/rounds/{round_id}/bundle')
                with zipfile.ZipFile(io.BytesIO(binary)) as z:
                    paths=[n for n in z.namelist() if n.endswith('.yaml')]
                    self.assertEqual(2,len(paths))
                    names={yaml.safe_load(z.read(p))['name'] for p in paths}
                    self.assertEqual({'Alice','Bob'},names)
                    self.assertTrue(all('death_link: false' in z.read(p).decode() for p in paths))
                # Mock only the generator boundary; real Archipelago is not needed for CI.
                ap=home/'archipelago';ap.mkdir()
                (ap/'Generate.py').write_text('''\
import argparse
import pathlib
import zipfile
p=argparse.ArgumentParser()
p.add_argument('--player_files_path');p.add_argument('--outputpath');p.add_argument('--multi')
a=p.parse_args()
files=list(pathlib.Path(a.player_files_path).glob('*.yaml'))
assert len(files)==int(a.multi)
out=pathlib.Path(a.outputpath)
with zipfile.ZipFile(out/'AP_TEST.zip','w') as z:
    z.writestr('AP_TEST.archipelago', b'fake-for-test-only')
''',encoding='utf8')
                alice.request('POST','/api/settings',{'directory':str(ap)})
                build_id=alice.request('POST',f'/api/rounds/{round_id}/generate',{'approve_custom_worlds':False})['build_id']
                for _ in range(100):
                    resp=alice.request('GET',f'/api/builds/{build_id}/log')
                    if resp['status']!='generating':break
                    time.sleep(.07)
                self.assertEqual('success',resp['status'],resp)
                with zipfile.ZipFile(io.BytesIO(alice.request('GET',f'/api/builds/{build_id}/download'))) as z:
                    self.assertIn('AP_TEST.archipelago',z.namelist())
            finally:
                process.terminate()
                try:process.communicate(timeout=4)
                except subprocess.TimeoutExpired:process.kill();process.communicate(timeout=2)


if __name__ == '__main__': unittest.main()
