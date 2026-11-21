"""Regressão do histórico individual de movimentações da v9.2."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from threading import Thread
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from urllib.error import HTTPError
from unittest.mock import patch

from radar import db
from radar.manual import add_manual_job, edit_manual_job, delete_manual_job
from radar.xlsxio import export_xlsx, import_xlsx
import monitor

ROOT=Path(__file__).resolve().parents[1]


def fixture(**kwargs):
    record=dict(title='Analista de Suporte Jr.',company='Senior Sistemas',
                url='https://example.org/vagas/123',location='Porto Alegre',
                mode='Híbrido',level='Júnior',description='Linux SQL',eligible='yes',
                status='Nova',published='',notes='')
    record.update(kwargs)
    return record


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.patch_db=patch.object(db,'DB_PATH',Path(self.tmp.name)/'history.sqlite')
        self.patch_db.start()
        self.cfg=monitor.config()

    def tearDown(self):
        self.patch_db.stop()
        self.tmp.cleanup()

    def test_application_then_transitions_are_atomic_ordered_and_dated(self):
        a=add_manual_job(fixture(),self.cfg)
        self.assertEqual(db.job_history(a),[])
        self.assertTrue(db.update_job(a,status='Candidatada'))
        self.assertTrue(db.update_job(a,status='Triagem'))
        self.assertTrue(db.update_job(a,status='Entrevista'))
        items=db.job_history(a)
        self.assertEqual([(i['previous_status'],i['new_status'],i['event_type']) for i in items],[
            ('Triagem','Entrevista','transition'),('Candidatada','Triagem','transition'),('Nova','Candidatada','application')])
        for item in items:
            self.assertIsNotNone(datetime.fromisoformat(item['occurred_at']).tzinfo)
        self.assertEqual(items[0]['source'],'Painel')

    def test_same_status_and_metadata_do_not_add_events(self):
        a=add_manual_job(fixture(status='Candidatada'),self.cfg)
        self.assertEqual(len(db.job_history(a)),1)
        db.update_job(a,status='Candidatada',notes='Mais informações')
        db.update_job(a,notes='Reunião amanhã',followup='2026-12-01')
        db.update_job(a,saved=True)
        self.assertEqual(len(db.job_history(a)),1)

    def test_manual_creation_and_edit_record_correct_events(self):
        a=add_manual_job(fixture(status='Candidatada'),self.cfg)
        events=db.job_history(a)
        self.assertEqual(events[0]['event_type'],'application')
        self.assertIsNone(events[0]['previous_status'])
        edit_manual_job(a,fixture(status='Triagem'),self.cfg)
        self.assertEqual(db.job_history(a)[0]['source'],'Edição de cadastro')
        self.assertEqual(len(db.job_history(a)),2)

    def test_import_tracks_initial_status_without_fabricating_progression(self):
        a=add_manual_job(fixture(status='Entrevista'),self.cfg,origin='Importação XLSX')
        history=db.job_history(a)
        self.assertEqual(len(history),1)
        self.assertEqual(history[0]['event_type'],'initial')
        self.assertIsNone(history[0]['previous_status'])
        self.assertEqual(history[0]['source'],'Importação XLSX')

    def test_previous_existing_job_without_history_is_not_backdated(self):
        a=add_manual_job(fixture(),self.cfg)
        with db.conn() as c:
            c.execute("UPDATE jobs SET status='Entrevista' WHERE id=?",(a,))
        self.assertEqual(db.job_history(a),[])
        db.update_job(a,status='Proposta')
        self.assertEqual([(e['previous_status'],e['new_status']) for e in db.job_history(a)], [('Entrevista','Proposta')])

    def test_history_separated_by_job_and_removed_with_manual_deletion(self):
        a=add_manual_job(fixture(),self.cfg)
        b=add_manual_job(fixture(title='Cloud Engineer',url='https://example.org/vagas/456'),self.cfg)
        db.update_job(a,status='Candidatada')
        db.update_job(b,status='Rejeitada')
        self.assertEqual(db.job_history(a)[0]['new_status'],'Candidatada')
        self.assertEqual(db.job_history(b)[0]['new_status'],'Rejeitada')
        self.assertTrue(delete_manual_job(a))
        self.assertIsNone(db.job_history(a))
        with db.conn() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM job_status_history WHERE job_id=?',(a,)).fetchone()[0],0)

    def test_scanning_does_not_touch_history(self):
        job=fixture(status='Candidatada')
        a=add_manual_job(job,self.cfg)
        source=dict(job,source='Gupy',external_id='xyz',published='',salary='')
        db.save_jobs([(source,85,['Aderente'],['Linux'])])
        self.assertEqual(len(db.job_history(a)),1)

    def test_api_returns_own_events_and_404(self):
        a=add_manual_job(fixture(status='Candidatada'),self.cfg)
        server=ThreadingHTTPServer(('127.0.0.1',0),monitor.Handler)
        worker=Thread(target=server.serve_forever,daemon=True)
        worker.start()
        try:
            url=f'http://127.0.0.1:{server.server_port}/api/jobs/{a}/history'
            with urlopen(url,timeout=5) as response:
                content=json.load(response)
            self.assertTrue(content['ok'])
            self.assertEqual(len(content['events']),1)
            self.assertEqual(content['events'][0]['new_status'],'Candidatada')
            with self.assertRaises(HTTPError) as err:
                urlopen(f'http://127.0.0.1:{server.server_port}/api/jobs/unknown/history',timeout=5)
            self.assertEqual(err.exception.code,404)
        finally:
            server.shutdown();server.server_close();worker.join(timeout=5)

    def test_manage_dialog_contains_read_only_timeline(self):
        html=(ROOT/'web'/'index.html').read_text('utf-8')
        js=(ROOT/'web'/'assets'/'app.js').read_text('utf-8')
        for element in ('manageHistoryTitle','manageHistoryCount','manageHistoryList'):
            self.assertIn(f'id="{element}"',html)
        self.assertIn('function loadManagedHistory(jobId)',js)
        self.assertIn('loadManagedHistory(j.id)',js)
        self.assertIn("'/history'",js)


if __name__=='__main__':
    unittest.main()
