"""Regressões: contador, filtros, blacklist, menu e Gemini na nuvem."""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import monitor
from radar import db, ai_search

ROOT=Path(__file__).resolve().parents[1]


class V5LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=(ROOT/'web/index.html').read_text('utf8')
        cls.js=(ROOT/'web/assets/app.js').read_text('utf8')

    def test_application_filters_have_inputs_and_js_binding(self):
        fields=('appliedSearch','appliedStatus','appliedCompany','appliedMode','appliedFollowup',
                'appliedFrom','appliedTo','appliedSort','appliedIncludeBlocked','appliedReset',
                'appliedFilterCount','applicationsCount')
        for field in fields:
            with self.subTest(field=field):
                self.assertIn(f'id="{field}"',self.html)
                self.assertIn(field,self.js)
        self.assertIn('function renderApplications()',self.js)
        self.assertIn('function resetApplicationFilters()',self.js)

    def test_block_and_restore_are_visible_and_independent(self):
        for element in ('page-bloqueados','blockedList','blockedCount','manageIgnore'):
            self.assertIn(f'id="{element}"',self.html)
        self.assertIn('data-action="block"',self.js)
        self.assertIn('data-action="restore"',self.js)
        self.assertIn('function renderBlocked()',self.js)

    def test_cloud_ai_button_and_key_entry(self):
        for field in ('scanBtn','aiSearchBtn','aiKeyStatus','cfgAiModel','aiRunList','cfgGeminiKey','saveAiKeyBtn','testAiKeyBtn','clearAiKeyBtn','cfgAiWebSearch'):
            self.assertIn(f'id="{field}"',self.html)
        self.assertNotIn('id="apiKey"',self.html)
        self.assertIn("api('ai/key'",self.js)
        self.assertIn('gemini-3.5-flash-lite',self.html)
        self.assertNotIn('gemini-2.5-flash-lite',self.html)

    def test_user_can_customize_navigation(self):
        for field in ('cfgBrand','menuCustomizer','brandTitle','sideNav'):
            self.assertIn(f'id="{field}"',self.html)
        for name in ('initMenuDraft','renderMenuCustomizer','renderNav','moveMenu'):
            self.assertIn('function '+name+'(',self.js)


class V5ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.conf=Path(self.tmp.name)/'config.json'
        self.conf.write_text(json.dumps(monitor.config()),'utf8')
        self.patch=patch.object(monitor,'CONFIG',self.conf)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_menu_customization_persists(self):
        menu=monitor.config()['ui_menu']
        self.assertEqual(len(menu),6)
        first=menu.pop(0);menu.insert(2,first)
        menu[0]['label']='Minhas vagas'
        settings=monitor.save_config({'ui_menu':menu,'ui_titles':{'candidaturas':'Processos seletivos'},'ui_brand':'RadarVagas personalizado'})
        self.assertEqual(settings['ui_menu'][0]['label'],'Minhas vagas')
        self.assertEqual(monitor.config()['ui_titles']['candidaturas'],'Processos seletivos')
        self.assertEqual(monitor.config()['ui_brand'],'RadarVagas personalizado')

    def test_cannot_hide_blocked_or_settings(self):
        for key in ('bloqueados','config'):
            menu=monitor.config()['ui_menu']
            next(x for x in menu if x['id']==key)['visible']=False
            with self.assertRaises(ValueError):monitor.save_config({'ui_menu':menu})

    def test_invalid_menu_rejected_without_wiping_config(self):
        original=monitor.config()
        with self.assertRaises(ValueError):monitor.save_config({'ui_menu':[{'id':'dashboard','label':'X','visible':True}]})
        self.assertEqual(monitor.config(),original)

    def test_invalid_cloud_model_rejected(self):
        with self.assertRaises(ValueError):monitor.save_config({'ai_model':'../../http://attacker.com?x=1'})

    def test_recruitee_bad_board_disabled_in_default(self):
        c=monitor.config()
        self.assertFalse(c['sources']['recruitee'])
        self.assertNotIn('helpjuice',str(c['recruitee_boards']).lower())


class V6AICloudTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.dbpatch=patch.object(db,'DB_PATH',Path(self.tmp.name)/'jobs.sqlite')
        self.keypatch=patch.object(ai_search,'KEY_FILE',Path(self.tmp.name)/'gemini.key')
        self.envpatch=patch.dict('os.environ', {'GEMINI_API_KEY':''})
        self.dbpatch.start();self.keypatch.start();self.envpatch.start()

    def tearDown(self):
        self.envpatch.stop();self.keypatch.stop();self.dbpatch.stop()
        self.tmp.cleanup()

    def config(self):
        return {'ai_daily_cap':2,'ai_model':'gemini-3.5-flash-lite','ai_max_output_tokens':800,
                'ai_web_search':True,'max_queries_per_source':5,'gupy_queries':['Suporte técnico'],
                'remote_queries':['IT Support'],'sources':{'gupy':True,'himalayas':False}}

    def test_missing_key_is_actionable(self):
        with self.assertRaisesRegex(ValueError,'Cadastre a chave gratuita Gemini'):
            ai_search.run(self.config())

    def test_key_is_stored_separately_and_can_be_removed(self):
        key='THIS_IS_A_TEST_FAKE_GEMINI_KEY_123456'
        ai_search.save_key(key)
        self.assertEqual(ai_search.get_key(),key)
        self.assertTrue(ai_search.key_status()['configured'])
        self.assertNotIn(key,str(ai_search.key_status()))
        ai_search.delete_key()
        self.assertFalse(ai_search.key_status()['configured'])

    def test_invalid_key_is_rejected(self):
        for bad in ('short','bad with spaces', 'x'*301):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):ai_search.save_key(bad)

    def test_requests_are_verified_and_usage_is_saved(self):
        job={'source':'Gupy','external_id':'1','title':'Analista de Suporte Júnior',
             'company':'Empresa Teste','location':'Brasil','mode':'Remoto','level':'Júnior',
             'published':'2026-11-20','url':'https://example.com/vaga/123',
             'description':'Suporte Linux','salary':'','eligible':'yes'}
        ai_search.save_key('FAKE_GEMINI_KEY_FOR_UNIT_TESTS_123456')
        with patch.object(ai_search,'_request_model',return_value={'pt':['Suporte técnico júnior'],
                'en':['Junior IT Support'],'_tokens':123,'_grounded':True}) as chat,\
             patch.object(ai_search,'collect',return_value=[('Gupy',[job],'')]),\
             patch.object(ai_search,'evaluate',return_value=(83,['Aderente'],['Linux'],True)):
            result=ai_search.run(self.config())
        self.assertEqual(result['new'],1)
        self.assertEqual(result['tokens'],123)
        self.assertEqual(ai_search._requests_today(),{'calls':1,'tokens':123})
        self.assertEqual(len(db.ai_runs()),1)
        self.assertEqual(db.rows()[0]['url'],'https://example.com/vaga/123')
        self.assertEqual(db.rows()[0]['score'],83)
        self.assertFalse(result['grounded'])
        self.assertFalse(chat.call_args.args[3])

    def test_daily_limit_is_enforced(self):
        ai_search.save_key('FAKE_GEMINI_KEY_FOR_UNIT_TESTS_123456')
        with db.conn() as c:
            c.execute('INSERT INTO ai_usage(day,calls,tokens) VALUES(?,2,40)',(ai_search.date.today().isoformat(),))
        with self.assertRaisesRegex(ValueError,'Limite diário'):
            ai_search.run(self.config())

    def test_remote_gemini_api_payload_and_key_header(self):
        ai_search.save_key('FAKE_GEMINI_KEY_FOR_UNIT_TESTS_123456')
        from unittest.mock import MagicMock
        payload={'candidates':[{'content':{'parts':[{'text':'{"pt":["Infra Júnior"],"en":["IT Support"]}'}]},
                 'groundingMetadata':{'webSearchQueries':['IT Support Brazil']}}],
                 'usageMetadata':{'promptTokenCount':55,'candidatesTokenCount':40}}
        class HttpContext:
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def read(self,max_size):return json.dumps(payload).encode('utf-8')
        with patch.object(ai_search.urllib.request,'urlopen',return_value=HttpContext()) as urlopen:
            result=ai_search._request_model('gemini-3.5-flash-lite','Termos de TI',600,False)
        req=urlopen.call_args.args[0]
        self.assertEqual(req.get_header('X-goog-api-key'),'FAKE_GEMINI_KEY_FOR_UNIT_TESTS_123456')
        body=json.loads(req.data)
        self.assertNotIn('tools',body)
        self.assertTrue(result['_grounded'])
        self.assertEqual(result['_tokens'],95)
        self.assertNotIn('ollama',req.full_url.lower())

if __name__=='__main__':unittest.main()
