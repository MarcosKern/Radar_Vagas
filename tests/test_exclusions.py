"""Regression tests for UI-driven ignored jobs and cross-source deduplication."""
from test_support import configured as test_config
import sqlite3
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone

from radar import db
from radar.helpers import canonical_job_url
from radar.manual import add_manual_job, edit_manual_job, delete_manual_job
from monitor import config

CFG=test_config()


def vacancy(**changes):
    item=dict(source='Gupy',external_id='job-42',title='Analista Suporte N2',
              company='Empresa Exemplo',location='Porto Alegre, RS',
              mode='Híbrido',level='Júnior',published=datetime.now(timezone.utc).isoformat(),
              url='https://empresa.example/jobs/42?utm_source=gupy',
              description='Linux Azure SQL',salary='',eligible='yes')
    item.update(changes)
    return item


def manual(**changes):
    item=dict(title='Analista Suporte N2',company='Empresa Exemplo',
              location='Porto Alegre, RS',url='https://empresa.example/jobs/42?utm_source=linkedin',
              mode='Híbrido',level='Júnior',published='2026-11-19',
              description='Linux Azure SQL',notes='Favorita',status='Salva')
    item.update(changes)
    return item


class ExclusionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.orig=db.DB_PATH
        db.DB_PATH=Path(self.temp.name)/'db.sqlite'

    def tearDown(self):
        db.DB_PATH=self.orig
        self.temp.cleanup()

    def test_ignored_excluded_from_future_scans_and_alerts(self):
        job=vacancy()
        self.assertEqual(db.save_jobs([(job,94,['good'],['Linux'])]),1)
        id=db.rows()[0]['id']
        self.assertTrue(db.set_job_ignored(id,True))
        row=db.rows()[0]
        self.assertEqual(row['ignored'],1)
        self.assertEqual(row['source'],'Gupy')
        stats={}
        # Same posting in a different source, with URL tracking variations.
        rerun=vacancy(source='Lever',external_id='another-id',
                      url='https://empresa.example/jobs/42/?utm_campaign=found&ref=remote')
        self.assertEqual(db.save_jobs([(rerun,99,['new'],['Azure'])],stats),0)
        self.assertEqual(stats['excluded'],1)
        self.assertEqual(len(db.rows()),1)
        self.assertEqual(db.pending_alerts(),[])

    def test_restore_job_allows_matching_post_again(self):
        db.save_jobs([(vacancy(),88,['test'],['Linux'])])
        id=db.rows()[0]['id']
        db.set_job_ignored(id,True)
        self.assertEqual(db.save_jobs([(vacancy(),88,['test'],['Linux'])]),0)
        self.assertTrue(db.set_job_ignored(id,False))
        self.assertEqual(db.rows()[0]['ignored'],0)
        stats={}
        self.assertEqual(db.save_jobs([(vacancy(),88,['test'],['Linux'])],stats),0)
        self.assertEqual(stats['already_known'],1)
        self.assertEqual(stats['excluded'],0)
        self.assertEqual(len(db.pending_alerts()),1)

    def test_manual_job_can_be_ignored_and_edited_without_losing_block(self):
        id=add_manual_job(manual(),CFG)
        db.set_job_ignored(id,True)
        self.assertEqual(db.save_jobs([(vacancy(),85,['test'],[])],{}),0)
        updated=manual(title='Cloud Support Analyst Jr',
                       url='https://empresa.example/jobs/99',notes='Nova observação')
        self.assertTrue(edit_manual_job(id,updated,CFG))
        j=db.rows()[0]
        self.assertEqual(j['ignored'],1)
        self.assertEqual(j['notes'],'Nova observação')
        # The old job no longer matches the exclusions after the manual edit.
        self.assertEqual(db.save_jobs([(vacancy(),82,['test'],[])],{}),1)
        self.assertEqual(len(db.rows()),2)
        self.assertTrue(delete_manual_job(id))
        self.assertEqual(len(db.rows()),1)
        with db.conn() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM job_exclusions').fetchone()[0],0)

    def test_known_jobs_dedup_by_normalized_url_even_location_differs(self):
        j=vacancy()
        db.save_jobs([(j,90,['a'],[])])
        alternate=vacancy(source='Remote OK',external_id='xyz',location='Brazil, Remote',
                          url='https://www.empresa.example/jobs/42/?fbclid=123&utm_medium=social')
        stats={}
        self.assertEqual(db.save_jobs([(alternate,88,['a'],[])],stats),0)
        self.assertEqual(stats['already_known'],1)
        self.assertEqual(len(db.rows()),1)

    def test_same_title_different_locations_not_overblocked(self):
        db.save_jobs([(vacancy(),90,['test'],[])])
        db.set_job_ignored(db.rows()[0]['id'],True)
        other=vacancy(location='Canoas, RS',url='https://empresa.example/jobs/99',external_id='99')
        self.assertEqual(db.save_jobs([(other,89,['test'],[])],{}),1)
        self.assertEqual(len([x for x in db.rows() if not x['ignored']]),1)

    def test_url_keeps_meaningful_identifiers(self):
        url='https://jobs.example.com/?id=ABC12&utm_source=newsletter&ref=link'
        self.assertEqual(canonical_job_url(url),'https://jobs.example.com?id=ABC12')
        self.assertNotEqual(canonical_job_url('https://jobs.example.com/?id=XYZ'),canonical_job_url(url))

    def test_database_migrates_previous_version_without_losing_data(self):
        # Simulate an existing installation with the v2.1 job schema but no ignore fields.
        with db.conn() as c:
            c.execute('DROP TABLE job_exclusions')
            # SQLite>=3.35 supports DROP COLUMN; test environment supports it.
            c.execute('ALTER TABLE jobs DROP COLUMN ignored')
            c.execute('ALTER TABLE jobs DROP COLUMN ignored_at')
            c.execute('ALTER TABLE runs DROP COLUMN excluded')
            c.execute('ALTER TABLE runs DROP COLUMN already_known')
        # Connection should migrate old file in place.
        with db.conn() as c:
            columns={r['name'] for r in c.execute('PRAGMA table_info(jobs)')}
            self.assertIn('ignored',columns)
            self.assertIn('ignored_at',columns)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM job_exclusions').fetchone()[0],0)

if __name__=='__main__':unittest.main()
