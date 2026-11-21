"""Valida exclusões configuráveis, correspondências sem falsos positivos e UI."""
from test_support import configured as test_config
import json
import tempfile
import unittest
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch
from urllib.request import Request, urlopen

import monitor
from radar.exclusion import DEFAULT_EXCLUDED, exclusion_details, exclusion_reason
from radar.scoring import evaluate

DATE=datetime.now(timezone.utc).isoformat()


def job(title,**extra):
    data={'title':title,'company':'Acme','description':'Linux Azure SQL troubleshooting','level':'',
          'mode':'Híbrido','location':'Porto Alegre, RS','source':'Gupy','published':DATE,'eligible':'yes'}
    data.update(extra)
    return data

class SeniorityRulesTests(unittest.TestCase):
    def setUp(self):self.cfg=test_config()

    def test_default_senior_and_pleno_filtered_before_score(self):
        for title in ['Senior Cloud Engineer','Analista de Suporte Pleno','Infrastructure Engineer Sr.',
                      'Mid-level IT Support','DevOps Tech Lead','Staff Engineer','IT Manager',
                      'Cloud Architect','Principal Engineer','Head of DevOps']:
            with self.subTest(title=title):
                self.assertIsNotNone(exclusion_details(job(title),self.cfg))
                self.assertIsNone(evaluate(job(title),self.cfg))

    def test_junior_and_analyst_i_are_allowed(self):
        for title in ['Analista de Suporte Júnior','Junior Cloud Analyst','IT Support Analyst I',
                      'Analista de Infraestrutura I','DevOps Entry-level']:
            with self.subTest(title=title):
                self.assertIsNone(exclusion_details(job(title),self.cfg))
                self.assertIsNotNone(evaluate(job(title),self.cfg))

    def test_mentions_senior_team_do_not_block_junior_role(self):
        examples=[
            'We are looking for a Junior Analyst who will work with senior engineers in a team.',
            'Join a team with senior engineers and learn Linux.',
            'Atuar em equipe com profissionais plenos e seniores.',
            'Participate in mentoring sessions with the technical lead.',
            'Benefits: support from a staff engineer.'
        ]
        for d in examples:
            with self.subTest(d=d):
                self.assertIsNone(exclusion_details(job('Junior IT Support Analyst',description=d),self.cfg))

    def test_explicit_description_level_is_detected(self):
        for description in ['Senioridade: Pleno. Linux AWS',
                            'Experience level: senior. Linux',
                            'Nível do cargo: gerente. Azure',
                            'Buscamos um Senior Cloud Engineer para apoiar Linux']:
            with self.subTest(description=description):
                detail=exclusion_details(job('IT Support Engineer',description=description),self.cfg)
                self.assertIsNotNone(detail)
                self.assertEqual(detail['where'],'Descrição explícita')

    def test_level_field_is_detected(self):
        match=exclusion_details(job('IT Support Engineer',level='Mid-level'),self.cfg)
        self.assertEqual(match['where'],'Senioridade')
        self.assertEqual(match['category'],'pleno')

    def test_word_boundary_prevents_fragment_matches(self):
        self.assertIsNone(exclusion_details(job('SRAM Firmware Tester',description='Linux'),self.cfg))
        self.assertIsNone(exclusion_details(job('Managerial Training Support',description='Linux'),self.cfg))
        self.assertIsNone(exclusion_details(job('Junior Assistant',description='Linux'),self.cfg))

    def test_toggle_levels_independently(self):
        self.cfg['exclude_seniority']['pleno']=False
        self.assertIsNone(exclusion_details(job('Analista de Infraestrutura Pleno'),self.cfg))
        self.assertIsNotNone(evaluate(job('Analista de Infraestrutura Pleno'),self.cfg))
        self.cfg['exclude_seniority']['intern']=True
        self.assertEqual(exclusion_details(job('Estagiário de Suporte'),self.cfg)['category'],'intern')

    def test_custom_terms_case_accent_and_remove(self):
        self.cfg['exclude_custom_terms']=['Analista III','Direção Técnica']
        self.assertEqual(exclusion_details(job('Analista III Suporte'),self.cfg)['category'],'custom')
        self.assertIsNotNone(exclusion_details(job('DIRECAO TECNICA INFRAESTRUTURA'),self.cfg))
        self.cfg['exclude_custom_terms']=[]
        self.assertIsNone(exclusion_details(job('Analista III Suporte'),self.cfg))

    def test_manual_job_bypasses_automatic_exclusion(self):
        self.assertIsNone(exclusion_details(job('Senior IT Analyst',source='Manual'),self.cfg))

    def test_reasons_are_explainable(self):
        self.assertIn('Pleno',exclusion_reason(job('Analista de Suporte Pleno'),self.cfg))
        self.assertIn('título',exclusion_reason(job('Analista de Suporte Pleno'),self.cfg))

class ExclusionScanTests(unittest.TestCase):
    def test_scan_tracks_auto_exclusions_separately_from_manual_blocks(self):
        from radar.executions import ExecutionStore
        with tempfile.TemporaryDirectory() as temp:
            store=ExecutionStore(Path(temp)/'executions.json')
            recorded=[]
            def fake_collect(cfg,on_source_start=None):
                yield 'Gupy',[job('Senior IT Support Engineer'),job('Analista de Suporte Pleno'),job('Junior IT Support Analyst')],''
            def fake_save_jobs(qualified,stats):
                recorded.extend(qualified)
                stats['excluded']=0;stats['already_known']=0
                return len(qualified)
            with patch.object(monitor,'config',return_value=test_config()),patch.object(monitor,'EXECUTIONS',store),patch.object(monitor,'collect',fake_collect),patch.object(monitor,'save_jobs',fake_save_jobs),patch.object(monitor,'save_run',lambda *a,**k:None),patch.object(monitor,'notify',lambda n:0):
                result=monitor.scan()
            self.assertTrue(result['ok'])
            self.assertEqual(result['auto_excluded'],2)
            self.assertEqual(result['excluded'],0)
            self.assertEqual(result['qualified'],1)
            self.assertEqual(len(recorded),1)
            logs=' | '.join(e['message'] for e in store.snapshot()[0]['logs'])
            self.assertIn('descartadas automaticamente',logs)
            self.assertIn('Exclusão automática',logs)
            self.assertEqual(store.snapshot()[0]['metrics']['auto_excluded'],2)

class SettingsV8Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.p=Path(self.tmp.name)/'config.json'
        self.p.write_text(json.dumps(monitor.config()),'utf8')
        self.orig=monitor.CONFIG;monitor.CONFIG=self.p

    def tearDown(self):monitor.CONFIG=self.orig;self.tmp.cleanup()

    def test_persist_config(self):
        levels=dict(DEFAULT_EXCLUDED);levels['pleno']=False
        x=monitor.save_config({'exclude_seniority':levels,'exclude_custom_terms':['Analista III','  REMOTO EUA  ']})
        self.assertFalse(x['exclude_seniority']['pleno'])
        self.assertEqual(x['exclude_custom_terms'],['Analista III','REMOTO EUA'])

    def test_invalid_config_is_rejected_without_saving(self):
        baseline=self.p.read_text('utf8')
        for change in [ {'exclude_seniority':{'senior':True}},
                        {'exclude_seniority':{**DEFAULT_EXCLUDED,'senior':'false'}},
                        {'exclude_custom_terms':['']},
                        {'exclude_custom_terms':['a']},
                        {'exclude_custom_terms':['x'*66]} ]:
            with self.subTest(change=change):
                with self.assertRaises(ValueError):monitor.save_config(change)
                self.assertEqual(self.p.read_text('utf8'),baseline)

    def test_config_missing_fields_migrates_in_memory(self):
        data=json.loads(self.p.read_text('utf8'))
        del data['exclude_seniority'];del data['exclude_custom_terms']
        self.p.write_text(json.dumps(data),'utf8')
        result=monitor.config()
        self.assertEqual(result['exclude_seniority'],DEFAULT_EXCLUDED)
        self.assertEqual(result['exclude_custom_terms'],['Tech Lead','Head of','Coordinator'])

class PreviewV8Tests(unittest.TestCase):
    def test_http_preview_respects_unsaved_filters(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),monitor.Handler)
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            url=f'http://127.0.0.1:{server.server_port}/api/exclusions/preview'
            def request(payload):
                req=Request(url,json.dumps(payload).encode(),headers={'Content-Type':'application/json'},method='POST')
                with urlopen(req,timeout=2) as resp:return json.load(resp)
            self.assertTrue(request({'title':'Analista de Infraestrutura Pleno'})['excluded'])
            levels=dict(DEFAULT_EXCLUDED);levels['pleno']=False
            self.assertFalse(request({'title':'Analista de Infraestrutura Pleno','exclude_seniority':levels})['excluded'])
            self.assertFalse(request({'title':'IT Support Analyst I','description':'Works with senior colleagues'})['excluded'])
        finally:server.shutdown();server.server_close()

class UILayoutV8Tests(unittest.TestCase):
    def test_controls_exist_and_js_binds_save(self):
        root=Path(__file__).resolve().parents[1]
        html=(root/'web/index.html').read_text('utf8')
        js=(root/'web/assets/app.js').read_text('utf8')
        css=(root/'web/assets/custom.css').read_text('utf8')
        for key in ['excludeLevelGrid','excludedTerms','exclusionCustomInput','excludeTermsAdd','exclusionPreviewForm','exclusionPreviewResult','resetExclusions']:
            self.assertIn(f'id="{key}"',html)
        self.assertIn('exclude_seniority:{...exclusionDraft}',js)
        self.assertIn('exclude_custom_terms:[...exclusionCustomDraft]',js)
        self.assertIn('initExclusions()',js)
        self.assertIn('exclusion-layout',css)
        self.assertIn('@media(max-width:610px)',css)

if __name__=='__main__':unittest.main()
