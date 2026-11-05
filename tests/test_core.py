import io
import zipfile
import unittest
import yaml
from core import validate_yaml, render_yaml, make_bundle, InvalidInput, validate_apworld

SAMPLE = b'# Important options\nname: old_user # rename\ngame: Timespinner\nTimespinner:\n  start_with_jewelry_box: false\n'

class CoreTests(unittest.TestCase):
    def test_name_replacement_preserves_settings(self):
        result = render_yaml(SAMPLE, 'Marci')
        doc = yaml.safe_load(result)
        self.assertEqual('Marci', doc['name'])
        self.assertIn(b'Timespinner:\n  start_with_jewelry_box: false', result)
    def test_unsafe_slots_rejected(self):
        with self.assertRaises(InvalidInput):
            render_yaml(SAMPLE, 'Evil\nserver: true')
    def test_slot_name_length_and_reserved_name(self):
        for slot in ('A' * 17, 'Archipelago'):
            with self.subTest(slot=slot), self.assertRaises(InvalidInput):
                render_yaml(SAMPLE, slot)

    def test_missing_game_options_rejected(self):
        with self.assertRaises(InvalidInput):
            validate_yaml(b'name: Test\ngame: Hollow Knight\nOtherGame: {}')

    def test_weighted_game_rejected(self):
        with self.assertRaises(InvalidInput):
            validate_yaml(b'name: Test\ngame: {Timespinner: 50}')
    def test_custom_world_hash_conflict(self):
        def fake_apworld(text):
            data = io.BytesIO()
            with zipfile.ZipFile(data, 'w') as z:
                z.writestr('test/__init__.py', text)
            return data.getvalue()
        body1, body2 = fake_apworld('version 1'), fake_apworld('version 2')
        picks = [{'username':'Alice','title':'Test','game_id':'1','apworld_filename':'test.apworld'},
                 {'username':'Bob','title':'Test','game_id':'2','apworld_filename':'test.apworld'}]
        with self.assertRaisesRegex(InvalidInput, 'Unterschiedliche Versionen'):
            make_bundle(picks, lambda _: SAMPLE, lambda id: body1 if id == '1' else body2)

    def test_reused_game_produces_distinct_yaml_files(self):
        zipped = io.BytesIO()
        with zipfile.ZipFile(zipped, 'w') as z: z.writestr('test/__init__.py', '')
        body = zipped.getvalue()
        self.assertTrue(validate_apworld(body, 'test.apworld')[0])
        picks = [{'username':'Marci','title':'Timespinner','game_id':'1','apworld_filename':None},
                 {'username':'Titor','title':'Timespinner','game_id':'1','apworld_filename':None}]
        bundle, manifest=make_bundle(picks, lambda _: SAMPLE, lambda _: None)
        with zipfile.ZipFile(io.BytesIO(bundle)) as z:
            self.assertEqual('Marci', yaml.safe_load(z.read('Players/01_Marci.yaml'))['name'])
            self.assertEqual('Titor', yaml.safe_load(z.read('Players/02_Titor.yaml'))['name'])
        self.assertEqual(2,len(manifest['slots']))

if __name__ == '__main__': unittest.main()
