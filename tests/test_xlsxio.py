"""Compatibility with user's existing workbook and expanded optional columns."""
import tempfile, unittest, zipfile, io
from pathlib import Path
from radar import db
from radar.xlsxio import parse_xlsx,import_xlsx,export_xlsx,HEADERS,DETAIL_HEADERS,_as_rows
from monitor import config
ROOT=Path(__file__).resolve().parents[1]
ORIG=Path('/mnt/data/Vagas.xlsx')
class XlsxTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.old=db.DB_PATH;db.DB_PATH=Path(self.temp.name)/'test.sqlite'
 def tearDown(self):db.DB_PATH=self.old;self.temp.cleanup()
 def test_import_original_optional_columns_absent(self):
  if not ORIG.exists():self.skipTest('Fixture do usuário não está no pacote')
  items,issues=parse_xlsx(ORIG.read_bytes())
  self.assertEqual(len(items),21);self.assertFalse(issues)
  self.assertEqual(items[0]['status'],'Candidatada')
  self.assertFalse(items[0]['url'])
  report=import_xlsx(ORIG.read_bytes(),config())
  self.assertEqual(report['inserted'],21);self.assertEqual(len(db.rows()),21)
  self.assertTrue(any(r['company']=='C&A' for r in db.rows()))
 def test_import_twice_deduplicates_and_keeps_notes(self):
  if not ORIG.exists():self.skipTest('Fixture do usuário não está no pacote')
  r1=import_xlsx(ORIG.read_bytes(),config());j=db.rows()[0]
  db.update_job(j['id'],notes='Dados anotados')
  r2=import_xlsx(ORIG.read_bytes(),config())
  self.assertEqual(r2['inserted'],0);self.assertEqual(r2['updated'],21)
  self.assertEqual(next(x for x in db.rows() if x['id']==j['id'])['notes'],'Dados anotados')
 def test_export_keeps_two_sheets_and_roundtrip(self):
  if not ORIG.exists():self.skipTest('Fixture do usuário não está no pacote')
  import_xlsx(ORIG.read_bytes(),config())
  blob=export_xlsx();self.assertIsNone(zipfile.ZipFile(io.BytesIO(blob)).testzip())
  rows,errs=parse_xlsx(blob)
  self.assertEqual(len(rows),21);self.assertFalse(errs)
  self.assertEqual(rows[0]['mode'],db.rows()[0]['mode'])
 def test_original_details_preserved_in_export(self):
  if not ORIG.exists():self.skipTest('Fixture do usuário não está no pacote')
  items,issues=parse_xlsx(ORIG.read_bytes());self.assertFalse(issues)
  self.assertIn('configuração de LAN',items[0]['description'])
  import_xlsx(ORIG.read_bytes(),config())
  with zipfile.ZipFile(io.BytesIO(export_xlsx())) as zin:
   data=_as_rows(zin,'Detalhes das vagas')
  self.assertEqual(data[8][2], '• Aprender configuração de LAN\n• Gerenciamento de projetos de redes\n• Configuração de redes sem fio\n• Design de redes sem fio através do software Ekahau\n• Elaboração de documentação de projetos')
  self.assertIn('Network Manager DOO',data[8][9])
 def test_clean_template_has_extra_headers_but_no_jobs(self):
  template=ROOT/'templates'/'Vagas_template.xlsx'
  self.assertTrue(template.is_file())
  jobs,errs=parse_xlsx(template.read_bytes());self.assertEqual(jobs,[]);self.assertEqual(errs,[])
