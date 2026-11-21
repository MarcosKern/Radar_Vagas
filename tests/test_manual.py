"""Testes do cadastro pessoal: offline e sem dependências adicionais."""
from test_support import configured as test_config
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from radar import db
from radar.manual import add_manual_job,edit_manual_job,delete_manual_job,DuplicateJobError
from monitor import config

CFG = test_config()


def fixture(**overrides):
    j = dict(title='Analista de Infraestrutura Jr',company='Empresa de Teste',
             url='https://example.org/carreiras/123',location='Novo Hamburgo, RS',
             mode='Híbrido',description='Linux, Python, Azure e suporte técnico N2.',
             level='Júnior',published='2026-11-19',salary='R$ 4.500',eligible='yes',
             notes='Entrar em contato com RH',status='Salva',followup='2026-11-29',saved=True)
    j.update(overrides)
    return j


class ManualTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.original = db.DB_PATH
        db.DB_PATH=Path(self.t.name)/'test.sqlite'

    def tearDown(self):
        db.DB_PATH=self.original
        self.t.cleanup()

    def test_create_persists_all_fields_and_source(self):
        id = add_manual_job(fixture(),CFG)
        j = db.rows()[0]
        self.assertEqual(j['id'],id)
        self.assertEqual(j['source'],'Manual')
        self.assertEqual(j['company'],'Empresa de Teste')
        self.assertEqual(j['status'],'Salva')
        self.assertEqual(j['followup'],'2026-11-29')
        self.assertEqual(j['saved'],1)
        self.assertEqual(j['salary'],'R$ 4.500')
        self.assertGreater(j['score'],0)
        self.assertTrue(any('manual' in s.lower() for s in j['reasons']))

    def test_no_link_and_excluded_title_can_still_be_added(self):
        id=add_manual_job(fixture(title='Senior Project Manager',url='',mode='Não informado',location=''),CFG)
        self.assertEqual(db.rows()[0]['id'],id)
        self.assertEqual(db.rows()[0]['url'],'')

    def test_invalid_and_required_validation(self):
        for overrides in ({'url':'javascript:alert(1)'},{'title':''},{'published':'2026-11-99'},
                          {'status':'Desconhecido'},{'mode':'Anywhere'},{'followup':'2026-02-31'}):
            with self.subTest(overrides=overrides),self.assertRaises(ValueError):
                add_manual_job(fixture(**overrides),CFG)
        self.assertEqual(len(db.rows()),0)

    def test_duplicate_by_fingerprint_and_link(self):
        first=add_manual_job(fixture(),CFG)
        with self.assertRaises(DuplicateJobError) as ctx:
            add_manual_job(fixture(url='https://example.org/other'),CFG)
        self.assertEqual(ctx.exception.existing_id,first)
        with self.assertRaises(DuplicateJobError) as ctx:
            add_manual_job(fixture(title='Outro cargo',location='Porto Alegre',url='https://example.org/carreiras/123/'),CFG)
        self.assertEqual(ctx.exception.existing_id,first)

    def test_edit_preserves_identity_and_updates_score(self):
        id=add_manual_job(fixture(),CFG)
        updated=fixture(title='Cloud Engineer Junior',description='Azure Terraform Docker Linux CI/CD',
                        status='Candidatada',notes='Entrevista marcada',followup='2026-12-01')
        self.assertTrue(edit_manual_job(id,updated,CFG))
        j=db.rows()[0]
        self.assertEqual(j['id'],id)
        self.assertEqual(j['title'],'Cloud Engineer Junior')
        self.assertEqual(j['status'],'Candidatada')
        self.assertEqual(j['notes'],'Entrevista marcada')
        self.assertTrue(j['applied_at'])

    def test_auto_scan_does_not_duplicate_or_overwrite_manual(self):
        id=add_manual_job(fixture(notes='Nota pessoal'),CFG)
        source=dict(source='Gupy',external_id='xyz',title='Analista de Infraestrutura Jr',
                    company='Empresa de Teste',location='Novo Hamburgo, RS',mode='Híbrido',
                    level='Júnior',published=datetime.now(timezone.utc).isoformat(),
                    url='https://example.org/carreiras/987',description='Linux',salary='',eligible='yes')
        self.assertEqual(db.save_jobs([(source,90,['Teste externo'],['Linux'])]),0)
        self.assertEqual(len(db.rows()),1)
        self.assertEqual(db.rows()[0]['id'],id)
        self.assertEqual(db.rows()[0]['notes'],'Nota pessoal')

    def test_existing_auto_prevents_new_manual_duplicate(self):
        source=dict(source='Gupy',external_id='xyz',title='Analista de Infraestrutura Jr',
                    company='Empresa de Teste',location='Novo Hamburgo, RS',mode='Híbrido',
                    level='Júnior',published='',url='https://example.org/carreiras/987',
                    description='Linux',salary='',eligible='yes')
        db.save_jobs([(source,90,['Teste externo'],['Linux'])])
        with self.assertRaises(DuplicateJobError):add_manual_job(fixture(),CFG)
        self.assertEqual(len(db.rows()),1)

    def test_delete_manual_only(self):
        id=add_manual_job(fixture(),CFG)
        self.assertTrue(delete_manual_job(id))
        self.assertFalse(delete_manual_job(id))
        self.assertEqual(db.rows(),[])
        source=dict(source='Gupy',external_id='xyz',title='Analista de Infraestrutura Jr',
                    company='Empresa de Teste',location='Novo Hamburgo, RS',mode='Híbrido',
                    level='Júnior',published='',url='https://example.org/carreiras/987',
                    description='Linux',salary='',eligible='yes')
        db.save_jobs([(source,90,['Teste externo'],['Linux'])])
        self.assertFalse(delete_manual_job(db.rows()[0]['id']))
        self.assertEqual(len(db.rows()),1)


if __name__=='__main__':unittest.main()
