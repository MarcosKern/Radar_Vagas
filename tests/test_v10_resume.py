"""Testes de regressão - currículos editáveis e alinhamento por vaga."""
from __future__ import annotations
import io
import json
import tempfile
import unittest
import zipfile
from http.server import ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen
from pathlib import Path
import monitor
from radar.resume import (generate_docx, normalize_profile, normalize_template,
                          tailored_data, DEFAULT_PROFILE, DEFAULT_TEMPLATE)

TEST_PROFILE={**DEFAULT_PROFILE,
 'full_name':'Profissional de Teste','email':'teste@example.invalid',
 'skills_pt':'Linux; SQL; Microsoft Azure; VPN; Terraform',
 'skills_en':'Linux; SQL; Microsoft Azure; VPN; Terraform',
 'experience_pt':'Empresa Teste | Analista TI | 2025 - Atual\n- Suporte Linux e SQL',
 'experience_en':'Example Company | IT Analyst | 2025 - Present\n- Supported Linux and SQL'}
JOB={'id':'vaga-teste','company':'Senior Sistemas','title':'Analista de Suporte Júnior',
     'description':'Ambiente Linux, SQL, Azure e VPN. Troubleshooting com comunicação em inglês.',
     'level':'Junior'}

class ResumeDocumentTests(unittest.TestCase):
    def test_pt_and_en_are_editable_docx(self):
        for lang,summary in [('pt','RESUMO PROFISSIONAL'),('en','PROFESSIONAL SUMMARY')]:
            data,_=generate_docx(JOB,profile=TEST_PROFILE,language=lang)
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names=z.namelist()
                self.assertIn('word/document.xml',names)
                xml=z.read('word/document.xml').decode('utf-8')
                self.assertIn(summary,xml)
                self.assertIn('Empresa Teste' if lang=='pt' else 'Example Company',xml)
                self.assertNotIn('Ingrid',xml)
                self.assertNotIn('Senior Sistemas',xml)
                self.assertIn('Profissional de Teste',xml)
    def test_order_is_justified_from_existing_skills(self):
        v=tailored_data(JOB,TEST_PROFILE,DEFAULT_TEMPLATE,'pt')
        self.assertIn('Linux',v['matched']);self.assertIn('SQL',v['matched'])
        self.assertIn('Microsoft Azure',v['matched']);self.assertIn('VPN',v['matched'])
        self.assertTrue(all(x in TEST_PROFILE['skills_pt'] for x in v['skills']))
    def test_no_description_does_not_hallucinate_skills(self):
        v=tailored_data({'title':'Analista de TI','description':''},TEST_PROFILE,DEFAULT_TEMPLATE,'pt')
        self.assertEqual(v['matched'],[])
        self.assertFalse(v['has_description'])
    def test_no_new_job_or_company_in_resume(self):
        malicious={'title':'Top Secret Brain Surgeon','description':'Must have 20 years surgical experience and advanced neuro surgery.'}
        doc,_=generate_docx(malicious,profile=TEST_PROFILE,language='en')
        xml=zipfile.ZipFile(io.BytesIO(doc)).read('word/document.xml').decode('utf-8')
        self.assertNotIn('Brain Surgeon',xml)
        self.assertNotIn('20 years surgical',xml)
    def test_profile_validation_and_customizations(self):
        with self.assertRaises(ValueError):normalize_profile({'made_up':'yes'})
        with self.assertRaises(ValueError):normalize_template({'font':'Comic Sans'})
        with self.assertRaises(ValueError):normalize_template({'accent':'red'})
        p=normalize_profile({'full_name':'Profissional de Teste'})
        data,_=generate_docx(JOB,profile=p,template={'accent':'#142C55','include_projects':False},language='pt')
        xml=zipfile.ZipFile(io.BytesIO(data)).read('word/document.xml').decode('utf-8')
        self.assertIn('Profissional de Teste',xml)
        self.assertNotIn('PROJETOS TÉCNICOS',xml)

class ResumeServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),monitor.Handler)
        cls.thread=Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_address[1]}'
        cls.patcher=patch.object(monitor,'rows',return_value=[JOB]);cls.patcher.start()
    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop();cls.server.shutdown();cls.server.server_close()
    def test_download_vacancy_resume(self):
        for lang in ('pt','en'):
            with urlopen(self.base+'/api/resume/docx?job=vaga-teste&lang='+lang) as response:
                self.assertEqual(response.status,200)
                self.assertIn('.docx',response.headers.get('Content-Disposition',''))
                self.assertEqual(response.headers.get('Content-Type'),'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
                self.assertTrue(zipfile.is_zipfile(io.BytesIO(response.read())))
    def test_download_blank_template(self):
        with urlopen(self.base+'/api/resume/template?lang=pt') as response:
            self.assertEqual(response.status,200)
            self.assertTrue(zipfile.is_zipfile(io.BytesIO(response.read())))
    def test_preview_shows_only_existing_matches(self):
        with urlopen(self.base+'/api/resume/match?job=vaga-teste&lang=en') as response:
            payload=json.load(response)
        self.assertTrue(payload['ok']);self.assertEqual(payload['matched'],[])
    def test_unknown_job_is_404(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base+'/api/resume/docx?job=missing&lang=en')
        self.assertEqual(error.exception.code,404)
    def test_bad_language_is_400(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base+'/api/resume/template?lang=xx')
        self.assertEqual(error.exception.code,400)
    def test_config_compatible_and_persistent(self):
        old=monitor.CONFIG
        with tempfile.TemporaryDirectory() as folder:
            f=Path(folder)/'config.json';f.write_text(json.dumps(monitor.config()),'utf8')
            with patch.object(monitor,'CONFIG',f):
                config=monitor.config()
                self.assertIn('resume_profile',config)
                new=monitor.save_config({'resume_profile':{'full_name':'Teste Personalizado','email':'teste@exemplo.com'},'resume_template':{'font':'Calibri','default_language':'en'}})
                self.assertEqual(new['resume_profile']['full_name'],'Teste Personalizado')
                self.assertEqual(monitor.config()['resume_template']['default_language'],'en')

class ResumeUiTests(unittest.TestCase):
    def test_ui_has_new_settings_and_responsive_action(self):
        root=Path(__file__).resolve().parents[1]
        html=(root/'web/index.html').read_text('utf8')
        js=(root/'web/assets/app.js').read_text('utf8')
        css=(root/'web/assets/custom.css').read_text('utf8')
        for selector in ('resumeDialog','resumeLanguage','resumeDownloadBtn','resumeFullName','resumeDefaultLanguage','resumeSaveSettings','resumeFieldsPt','resumeFieldsEn'):
            self.assertIn(f'id="{selector}"',html)
        self.assertIn('data-config-tab="resume"',html)
        self.assertIn('data-action="resume"',js)
        self.assertIn("if(action.dataset.action==='resume')",js)
        self.assertNotIn("document.addEventListener('pointermove'",js)
        self.assertIn('.resume-card-btn:hover',css)
        self.assertNotIn('followResumeCursor',js)

if __name__=='__main__':unittest.main()
