"""Smoke tests: instalação limpa sem banco, perfil ou config anterior."""
import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import monitor
from radar import db
from radar.resume import DEFAULT_PROFILE

class FreshInstall(unittest.TestCase):
    def test_no_config_is_required_to_open_app(self):
        with tempfile.TemporaryDirectory() as temp:
            config_file=Path(temp)/'config.json'
            with patch.object(monitor,'CONFIG',config_file):
                conf=monitor.config()
                self.assertFalse(config_file.exists())
                self.assertFalse(any(conf['sources'].values()))
                self.assertTrue(all(not value for value in conf['resume_profile'].values()))
                self.assertEqual(conf['gupy_queries'],[])
                self.assertEqual(conf['remote_queries'],[])
    def test_settings_json_restores_fresh_install(self):
        with tempfile.TemporaryDirectory() as temp:
            config_file=Path(temp)/'config.json'
            with patch.object(monitor,'CONFIG',config_file):
                snapshot=monitor.portable_settings()
                snapshot['settings']['ui_brand']='Radar de vagas TESTE'
                report=monitor.import_portable_settings(snapshot)
                self.assertTrue(config_file.is_file())
                self.assertEqual(monitor.config()['ui_brand'],'Radar de vagas TESTE')
                self.assertGreater(report['imported_count'],0)
    def test_profile_has_no_prefilled_personal_data(self):
        self.assertTrue(all(value=='' for value in DEFAULT_PROFILE.values()))
    def test_database_starts_empty_and_can_be_imported(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(db,'DB_PATH',Path(temp)/'jobs.sqlite'):
                self.assertEqual(db.rows(),[])
                self.assertTrue((Path(temp)/'jobs.sqlite').exists())

if __name__=='__main__':unittest.main()
