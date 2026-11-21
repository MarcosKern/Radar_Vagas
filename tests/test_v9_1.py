"""Regressão v9.1: exclusões sem falsos positivos por empresa, URL e candidatura."""
from test_support import configured as test_config
import unittest
import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import Request, urlopen
from pathlib import Path
from datetime import datetime, timezone
from radar.exclusion import exclusion_details
from radar.scoring import evaluate
import monitor

NOW = datetime.now(timezone.utc).isoformat()


def make_job(title, company='Senior Sistemas', **kwargs):
    data=dict(title=title, company=company, source='Gupy', description='Linux SQL Azure',
              location='Porto Alegre', mode='Híbrido', eligible='yes', level='', published=NOW)
    data.update(kwargs)
    return data


class CompanyNameSeniorityTests(unittest.TestCase):
    def setUp(self):
        self.cfg=test_config()

    def test_company_senior_does_not_exclude_junior(self):
        for title in ('Analista de Suporte Júnior - Senior Sistemas',
                      'Senior Sistemas - Analista de Suporte I',
                      'IT Support Analyst I | Senior Sistemas'):
            with self.subTest(title=title):
                self.assertIsNone(exclusion_details(make_job(title),self.cfg))

    def test_company_with_custom_exclusion_term_does_not_exclude_role(self):
        job=make_job('Analista de Suporte Júnior - Tech Lead Solutions','Tech Lead Solutions')
        self.assertIsNone(exclusion_details(job,self.cfg))

    def test_full_company_name_removed_with_legal_suffix(self):
        job=make_job('Analista de Suporte Júnior - Senior Sistemas','Senior Sistemas Ltda.')
        self.assertIsNone(exclusion_details(job,self.cfg))

    def test_exclusion_still_detects_explicit_level(self):
        for title in ('Analista de Suporte Pleno - Senior Sistemas',
                      'Senior Infrastructure Engineer - Senior Sistemas',
                      'Manager de TI - Senior Sistemas'):
            with self.subTest(title=title):
                self.assertIsNotNone(exclusion_details(make_job(title),self.cfg))

    def test_company_mention_in_description_is_not_level(self):
        cases=(
            'Buscamos um analista de suporte para atuar na Senior Sistemas',
            'Cargo de analista de suporte - Senior Sistemas',
            'Buscamos um analista junior para trabalhar com senior engineers',
        )
        for description in cases:
            with self.subTest(description=description):
                self.assertIsNone(exclusion_details(make_job('IT Support Analyst I',description=description),self.cfg))

    def test_explicit_level_from_description_is_still_excluded(self):
        job=make_job('Analista de Infraestrutura',description='Senioridade: Pleno. Azure e redes')
        self.assertEqual(exclusion_details(job,self.cfg)['category'],'pleno')

    def test_junior_job_score_is_not_penalized_by_company_name(self):
        job=make_job('Analista de Suporte Júnior - Senior Sistemas')
        self.assertIsNotNone(evaluate(job,self.cfg))


class JobUiV91Tests(unittest.TestCase):
    def test_filters_collapsed_and_old_fields_preserved(self):
        root=Path(__file__).parents[1]
        html=(root/'web/index.html').read_text(encoding='utf-8')
        for key in ('opportunityFiltersToggle','opportunityFiltersBody','searchInput',
                    'modeFilter','statusFilter','sourceFilter','viewFilter',
                    'sortFilter','hideProcessed','resetFilters'):
            self.assertIn(f'id="{key}"',html)
        self.assertIn('id="opportunityFiltersBody" hidden',html)
        self.assertIn('aria-expanded="false" aria-controls="opportunityFiltersBody"',html)

    def test_open_url_and_register_application_controls(self):
        root=Path(__file__).parents[1]
        js=(root/'web/assets/app.js').read_text(encoding='utf-8')
        for expected in ('function safeJobUrl(', 'Link da vaga', 'Abrir vaga',
                         'Registrar candidatura', 'function registerApplication(id)',
                         "data-action='apply'", "status:'Candidatada'", "saved:true"):
            # data-action is double-quoted inside the HTML string
            if expected == "data-action='apply'":
                expected='data-action="apply"'
            self.assertIn(expected,js)
        self.assertIn('ela NÃO envia sua inscrição ao site externo',js)



class PreviewCompanyHttpTests(unittest.TestCase):
    def test_preview_is_aware_of_company_name(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),monitor.Handler)
        worker=Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            endpoint=f'http://127.0.0.1:{server.server_port}/api/exclusions/preview'
            for title,expected in [('Analista de Suporte Júnior - Senior Sistemas',False),
                                   ('Analista de Suporte Pleno - Senior Sistemas',True)]:
                req=Request(endpoint,data=json.dumps({'title':title,'company':'Senior Sistemas'}).encode(),headers={'Content-Type':'application/json'},method='POST')
                with urlopen(req,timeout=3) as response:
                    self.assertEqual(json.load(response)['excluded'],expected)
        finally:
            server.shutdown();server.server_close()

if __name__=='__main__': unittest.main()
