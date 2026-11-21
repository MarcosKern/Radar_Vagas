from test_support import configured as test_config
import unittest
import tempfile
import os
from datetime import datetime,timezone,timedelta
from radar.helpers import plain,norm,age_days,safe_url
from radar.scoring import evaluate
from radar.sources import parse_gupy,parse_himalayas,parse_jobicy,parse_remotive
from radar.db import job_identity
from monitor import config

CFG=test_config()
NOW=datetime.now(timezone.utc).isoformat()

class RadarTests(unittest.TestCase):
    def test_html_and_date(self):
        self.assertEqual(plain('<p>Linux <b>Azure</b></p>'),'Linux Azure')
        self.assertEqual(norm('São Leopoldo'),'sao leopoldo')
        self.assertIsNone(age_days('não existe'))
        self.assertEqual(safe_url('javascript:alert(1)'),'')
    def test_gupy_parse(self):
        data={'data':[{'id':42,'name':'Analista de Suporte Jr','careerPageName':'Acme','city':'Porto Alegre','state':'Rio Grande do Sul','workplaceType':'hybrid','publishedDate':NOW,'jobUrl':'https://acme.gupy.io/jobs/42','description':'Linux e SQL'}]}
        x=parse_gupy(data)[0]
        self.assertEqual(x['source'],'Gupy')
        self.assertIn('Porto Alegre',x['location'])
        self.assertIsNotNone(evaluate(x,CFG))
    def test_himalayas_brazil_restriction(self):
        d={'jobs':[{'guid':'https://himalayas.app/companies/test/jobs/a','title':'IT Support Engineer Junior','companyName':'Acme','pubDate':int(datetime.now(timezone.utc).timestamp()),'applicationLink':'https://himalayas.app/jobs/a','description':'Linux Azure','locationRestrictions':[{'alpha2':'US','name':'United States'}]}]}
        x=parse_himalayas(d)[0]
        self.assertEqual(x['eligible'],'no')
        self.assertIsNone(evaluate(x,CFG))
    def test_worldwide_himalayas(self):
        d={'jobs':[{'guid':'some-id','title':'IT Support Engineer Junior','companyName':'Acme','pubDate':int(datetime.now(timezone.utc).timestamp()),'applicationLink':'https://himalayas.app/jobs/a','description':'Linux Azure','locationRestrictions':[]}]}
        x=parse_himalayas(d)[0]
        self.assertEqual(x['eligible'],'yes')
        self.assertGreaterEqual(evaluate(x,CFG)[0],72)
    def test_jobicy(self):
        x=parse_jobicy({'jobs':[{'id':'abc','jobTitle':'Junior DevOps Engineer','companyName':'Acme','jobGeo':'Worldwide','pubDate':NOW,'url':'https://jobicy.com/jobs/abc','jobDescription':'Terraform Docker CI/CD'}]})[0]
        self.assertEqual(x['eligible'],'yes')
        self.assertIsNotNone(evaluate(x,CFG))
    def test_remotive_and_senior(self):
        x=parse_remotive({'jobs':[{'id':10,'title':'Senior Cloud Engineer','company_name':'Acme','candidate_required_location':'Worldwide','publication_date':NOW,'url':'https://remotive.com/job/10'}]})[0]
        self.assertIsNone(evaluate(x,CFG))
    def test_old_excluded(self):
        x={'title':'Analista de Infraestrutura Jr','description':'Linux Azure','company':'Acme','location':'Canoas, Rio Grande do Sul','mode':'Híbrido','eligible':'yes','published':(datetime.now(timezone.utc)-timedelta(days=22)).isoformat()}
        self.assertIsNone(evaluate(x,CFG))
    def test_identity_dedup(self):
        a={'title':'Analista de Suporte JR','company':'Empresa X'}
        b={'title':'Analista de Suporte JR','company':'Empresa X'}
        self.assertEqual(job_identity(a),job_identity(b))

if __name__=='__main__':unittest.main()

class DBTests(unittest.TestCase):
    def test_sqlite_pipeline_and_export(self):
        from pathlib import Path
        from radar import db
        from monitor import csv_text
        original=db.DB_PATH
        with tempfile.TemporaryDirectory() as p:
            try:
                db.DB_PATH=Path(p)/'jobs.sqlite'
                job={'source':'Gupy','external_id':'99','title':'Analista de Suporte Jr','company':'Empresa Teste','location':'Porto Alegre, Rio Grande do Sul','mode':'Híbrido','level':'Junior','published':NOW,'url':'https://teste.gupy.io/jobs/99','description':'Linux SQL Azure','salary':'','eligible':'yes'}
                e=evaluate(job,CFG)
                self.assertIsNotNone(e)
                self.assertEqual(db.save_jobs([(job,e[0],e[1],e[2])]),1)
                self.assertEqual(db.save_jobs([(job,e[0],e[1],e[2])]),0)
                ids=db.rows()
                self.assertEqual(len(ids),1)
                self.assertTrue(db.update_job(ids[0]['id'],status='Candidatada',notes='Teste offline',followup='2026-12-01',saved=True))
                self.assertEqual(db.rows()[0]['notes'],'Teste offline')
                self.assertEqual(db.rows()[0]['status'],'Candidatada')
                self.assertIn('Empresa Teste',csv_text())
                self.assertEqual(len(db.pending_alerts(0)),0)
            finally:db.DB_PATH=original
    def test_local_city_filter(self):
        from radar.scoring import local_allowed
        self.assertFalse(local_allowed({'location':'Pelotas, Rio Grande do Sul'},CFG))
        self.assertTrue(local_allowed({'location':'São Leopoldo, Rio Grande do Sul'},CFG))
