import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import monitor
from desktop.build import manifest
from radar import db, updates
from radar.csvio import export_csv, import_csv
from radar.export_filters import select_jobs
from radar.manual import add_manual_job
from radar.xlsxio import export_xlsx, import_xlsx


class DesktopUpdates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.manager = updates.Updates()
        self.remote = copy.deepcopy(self.manager.local)
        self.remote['version'] = 'V99.1'
        self.body = b'new stylesheet'
        self.name = 'web/assets/custom.css'
        self.remote['files'][self.name] = hashlib.sha256(self.body).hexdigest()
        self.urls = []

    def provider(self, url, limit):
        self.urls.append(url)
        if url.endswith('/main'):
            return json.dumps({'object': {'sha': 'a'*40}}).encode()
        if url.endswith(updates.MANIFEST):
            return json.dumps(self.remote).encode()
        if url.endswith('/' + self.name):
            return self.body
        self.fail(url)

    def test_manifest_and_history(self):
        self.assertEqual(updates.validate(self.manager.local), manifest())
        self.assertEqual(self.manager.history[0]['version'], self.manager.local['version'])
        self.assertTrue(all(r['changes'] for r in self.manager.history))

    def test_only_changed_file_is_downloaded_and_data_stays_intact(self):
        dbfile = self.home / 'data/jobs.sqlite'
        dbfile.parent.mkdir()
        dbfile.write_bytes(b'existing')
        with patch.object(updates, 'HOME', self.home), patch.dict(os.environ, RADAR_SUPERVISED='1'), patch.object(updates, 'fetch', self.provider):
            self.assertEqual(self.manager.check()['latest'], 'V99.1')
            self.manager.stage()
        stage = self.home/'versions'/(self.home/'pending').read_text()
        self.assertEqual((stage/self.name).read_bytes(), self.body)
        self.assertEqual((stage/'monitor.py').read_bytes(), (updates.ROOT/'monitor.py').read_bytes())
        self.assertEqual(dbfile.read_bytes(), b'existing')
        self.assertEqual(len(self.urls), 3)
        self.assertIn('/' + 'a'*40 + '/', self.urls[-1])

    def test_corrupt_download_cannot_be_activated(self):
        self.remote['files'][self.name] = '0'*64
        with patch.object(updates, 'HOME', self.home), patch.dict(os.environ, RADAR_SUPERVISED='1'), patch.object(updates, 'fetch', self.provider):
            self.manager.check()
            with self.assertRaisesRegex(ValueError, 'verificar'):
                self.manager.stage()
        self.assertFalse((self.home/'pending').exists())
        self.assertEqual(list((self.home/'versions').iterdir()), [])

    def test_offline_and_invalid_paths(self):
        with patch.object(updates, 'fetch', side_effect=OSError('offline')):
            self.assertIsNone(self.manager.check()['latest'])
            self.assertTrue(self.manager.status()['history'])
        self.remote['files']['radar/../config.json'] = 'a'*64
        with self.assertRaises(ValueError):
            updates.validate(self.remote)

    def test_opportunities_roundtrip_both_formats(self):
        cfg = monitor._runtime_defaults()
        with patch.object(db, 'DB_PATH', self.home/'base.db'):
            add_manual_job({'title':'Analista','company':'Exemplo','status':'Nova','saved':False},cfg)
            rows = select_jobs({'scope':'all'})
        for name, export, load in [('csv',export_csv,import_csv),('xlsx',export_xlsx,import_xlsx)]:
            with self.subTest(name=name), patch.object(db,'DB_PATH',self.home/(name+'.db')):
                payload = export(rows)
                self.assertEqual(load(payload,cfg)['inserted'],1)
                self.assertEqual(load(payload,cfg)['inserted'],0)
                self.assertEqual([(x['status'],x['saved']) for x in db.rows()], [('Nova',0)])

    def test_duplicate_tracking_urls_and_distinct_locations(self):
        one = dict(id='1',title='Suporte',company='Loja',location='POA',url='https://example.org/1',status='Nova')
        two = dict(one,id='2',location='Porto Alegre',url=one['url']+'?utm_source=board')
        three = dict(one,id='3',location='Recife',url='https://example.org/3')
        jobs = [one,two,three]
        self.assertEqual(len(select_jobs({'scope':'active'},jobs)),2)
        self.assertEqual(len(select_jobs({'scope':'all'},jobs)),3)
