"""V0.14: filtro real do servidor, formatos de vagas e backup portátil."""
from __future__ import annotations
import csv
import io
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer

import monitor
from radar import db
from radar.csvio import export_csv,import_csv,parse_csv
from radar.xlsxio import export_xlsx,parse_xlsx
from radar.export_filters import parse_options,select_jobs,export_preview


def job(id,status='Nova',company='Alfa',mode='Remoto',date='2026-11-17',ignored=0):
    return dict(id=id,title='Analista de TI',company=company,location='Porto Alegre',
        status=status,source='Manual',mode=mode,ignored=ignored,saved=0,
        score=72,applied_at=date if status not in ('Nova','Salva') else '',
        first_seen=date, published=date,notes='',url='https://example.com/'+id,
        skills=[],recruiter='',contract_type='',level='',salary='',followup='',
        description='',xlsx_details='',last_seen=date,eligible='yes')

class ExportSelectionTests(unittest.TestCase):
    def setUp(self):
        self.items=[job('new','Nova'),job('saved','Salva'),job('appl','Candidatada'),
                    job('interview','Entrevista','Beta'),job('rejected','Rejeitada','Beta',ignored=1),
                    job('proposal','Proposta','Alfa','Híbrido')]
    def test_default_exports_only_applications_and_keeps_rejected(self):
        selected=select_jobs({},self.items)
        self.assertEqual(set(x['id'] for x in selected),{'appl','interview','rejected','proposal'})
        self.assertEqual(export_preview({},self.items)['count'],4)
    def test_all_scope_is_explicit(self):
        self.assertEqual(len(select_jobs({'scope':'all'},self.items)),6)
        self.assertEqual(len(select_jobs({'scope':'blocked'},self.items)),1)
        self.assertEqual(len(select_jobs({'scope':'all','include_blocked':'false'},self.items)),5)
    def test_seniority_exclusions_do_not_block_company_senior_sistemas(self):
        config=monitor.config()
        junior=job('one','Nova','Senior Sistemas')
        junior.update(title='Analista de Suporte Júnior',source='Gupy')
        pleno=job('two','Nova','Senior Sistemas')
        pleno.update(title='Analista de Suporte Pleno',source='Gupy')
        selected=select_jobs({'scope':'active'},[junior,pleno],cfg=config)
        self.assertEqual([x['id'] for x in selected],['one'])

    def test_filters_combined(self):
        a=select_jobs({'scope':'applications','company':'Beta','status':'Entrevista'},self.items)
        self.assertEqual([x['id'] for x in a],['interview'])
        a=select_jobs({'scope':'applications','mode':'Híbrido'},self.items)
        self.assertEqual([x['id'] for x in a],['proposal'])
        a=select_jobs({'scope':'applications','date_field':'applied_at','date_from':'2026-11-18'},self.items)
        self.assertEqual(a,[])
    def test_reject_invalid_filter(self):
        for vals in ({'scope':'nonsense'},{'status':'nonsense'},
                     {'date_from':'2026-12-30','date_to':'2026-11-01'},
                     {'include_blocked':'sure'}, {'date_from':'abc'}):
            with self.assertRaises(ValueError):parse_options(vals)
    def test_same_export_selection_for_csv_and_xlsx(self):
        selected=select_jobs({'scope':'applications','company':'Beta'},self.items)
        csv_rows=list(csv.reader(io.StringIO(export_csv(selected).decode('utf-8-sig')),delimiter=';'))
        self.assertEqual(len(csv_rows)-1,2)
        data=export_xlsx(selected)
        self.assertIsNone(zipfile.ZipFile(io.BytesIO(data)).testzip())
        parsed,_=parse_xlsx(data)
        self.assertEqual(len(parsed),2)
    def test_csv_formula_injection_escaped(self):
        items=[job('one','Candidatada')]
        items[0]['company']='=HYPERLINK("a","b")'
        data=export_csv(items).decode('utf-8-sig')
        self.assertIn("'=HYPERLINK",data)

class ImportBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old_db=db.DB_PATH;db.DB_PATH=Path(self.tmp.name)/'test.sqlite'
        self.old_config=monitor.CONFIG
        self.config_path=Path(self.tmp.name)/'config.json'
        self.config_path.write_text(json.dumps(monitor.config()),encoding='utf-8')
        monitor.CONFIG=self.config_path
    def tearDown(self):
        db.DB_PATH=self.old_db;monitor.CONFIG=self.old_config;self.tmp.cleanup()
    def test_ignore_explicit_nova_csv(self):
        doc='Vaga;Empresa;Status;Anotações\nAnalista Nova;Acme;Nova;Não importar\nAnalista Enviada;Acme;Candidatada;Interessante\n'.encode()
        result=import_csv(doc,monitor.config())
        self.assertEqual((result['inserted'],result['skipped_nova']),(1,1))
        self.assertEqual([x['title'] for x in db.rows()],['Analista Enviada'])
    def test_missing_optional_status_imports_as_opportunity(self):
        doc='Cargo;Empresa\nAnalista de Suporte;Gamma\n'.encode()
        result=import_csv(doc,monitor.config())
        self.assertEqual(result['inserted'],1)
        self.assertEqual(db.rows()[0]['status'],'Nova')
    def test_reimport_does_not_downgrade_applications_or_notes(self):
        a='Vaga;Empresa;Status;Anotações\nEngenheiro de TI;Beta;Proposta;Lembrete\n'.encode()
        import_csv(a,monitor.config())
        b='Vaga;Empresa;Status;Anotações\nEngenheiro de TI;Beta;Candidatada;Sobrescrever\n'.encode()
        result=import_csv(b,monitor.config())
        self.assertEqual(result['updated'],1)
        j=db.rows()[0]
        self.assertEqual(j['status'],'Proposta')
        self.assertEqual(j['notes'],'Lembrete')
    def test_settings_json_excludes_keys_and_db(self):
        backup=monitor.portable_settings()
        self.assertEqual(backup['schema_version'],1)
        self.assertNotIn('gemini_key',json.dumps(backup))
        self.assertNotIn('jobs',backup['settings'])
        self.assertIn('resume_template',backup['settings'])
    def test_backup_roundtrip_and_reject_unknown_without_mutation(self):
        p=monitor.portable_settings()
        p['settings']['max_age_days']=23
        report=monitor.import_portable_settings(p)
        self.assertEqual(report['imported_count'],len(p['settings']))
        self.assertEqual(monitor.config()['max_age_days'],23)
        p['settings']['key']='DELIBERATELY_NOT_VALID'
        with self.assertRaises(ValueError):monitor.import_portable_settings(p)
        self.assertEqual(monitor.config()['max_age_days'],23)

class InterfaceContractTests(unittest.TestCase):
    def test_export_modal_and_json_backup_are_wired(self):
        root=Path(__file__).resolve().parents[1]
        ui=(root/'web/index.html').read_text('utf-8')
        js=(root/'web/assets/app.js').read_text('utf-8')
        for ident in ('exportDialog','exportScope','exportStatus','exportCompany',
                      'exportMode','exportDateField','exportDateFrom','exportDateTo',
                      'exportPreviewCount','exportCsvBtn','exportXlsxBtn',
                      'exportSettingsJsonBtn','settingsImportForm'):
            self.assertIn('id="'+ident+'"',ui)
        self.assertIn('data-config-tab="backup"',ui)
        for func in ('openExportFilters','importSettingsJson','updateExportPreview','downloadFilteredExport'):
            self.assertIn('function '+func,js)

class HTTPIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old_db=db.DB_PATH
        db.DB_PATH=Path(self.tmp.name)/'test.sqlite'
        import_csv('Vaga;Empresa;Status\nAnalista A;Firma;Candidatada\nAnalista B;Firma;Nova\n'.encode(),monitor.config())
        self.srv=ThreadingHTTPServer(('127.0.0.1',0),monitor.Handler)
        self.thread=threading.Thread(target=self.srv.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.srv.server_port}'
    def tearDown(self):
        self.srv.shutdown();self.srv.server_close();self.thread.join(2)
        db.DB_PATH=self.old_db;self.tmp.cleanup()
    def test_preview_matches_export_and_skips_nova(self):
        result=json.loads(urlopen(self.base+'/api/export/preview').read())
        self.assertEqual(result['count'],1)
        csv_data=urlopen(self.base+'/api/export.csv').read().decode('utf-8-sig')
        self.assertEqual(len(list(csv.DictReader(io.StringIO(csv_data),delimiter=';'))),1)
        self.assertEqual(len(parse_xlsx(urlopen(self.base+'/api/export.xlsx').read())[0]),1)
    def test_invalid_preview_returns_http400(self):
        with self.assertRaises(HTTPError) as e:urlopen(self.base+'/api/export/preview?scope=invalid')
        self.assertEqual(e.exception.code,400)

if __name__=='__main__':unittest.main()
