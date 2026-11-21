"""v7: log verdadeiro, Gemini gratuito e detecção por chave (sem custos de geração)."""
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import monitor
from radar import ai_search
from radar.executions import ExecutionStore

ROOT=Path(__file__).resolve().parents[1]


class FreeModelsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.key=patch.object(ai_search,'KEY_FILE',Path(self.tmp.name)/'gemini.key')
        self.cooldown=patch.object(ai_search,'COOLDOWN_FILE',Path(self.tmp.name)/'cooldown.json')
        self.env=patch.dict('os.environ',{'GEMINI_API_KEY':''})
        self.key.start();self.cooldown.start();self.env.start()
        ai_search._MODEL_CACHE.clear()

    def tearDown(self):
        ai_search._MODEL_CACHE.clear()
        self.env.stop();self.cooldown.stop();self.key.stop();self.tmp.cleanup()

    def test_select_contains_only_current_free_text_models(self):
        html=(ROOT/'web/index.html').read_text('utf-8')
        self.assertEqual(set(ai_search.SUPPORTED_MODELS),{'gemini-3.5-flash-lite','gemini-3.1-flash-lite'})
        self.assertIn('gemini-3.5-flash-lite',html)
        self.assertIn('gemini-3.1-flash-lite',html)
        self.assertNotIn('gemini-2.5-flash-lite',html)
        self.assertNotIn('gemini-2.5-flash\"',html)

    def test_no_key_shows_candidates_as_unverified(self):
        value=ai_search.available_free_models()
        self.assertFalse(value['verified'])
        self.assertFalse(value['configured'])
        self.assertEqual(len(value['models']),2)

    def test_available_models_filtered_by_key_and_free_allowlist(self):
        ai_search.save_key('FAKE_KEY_FOR_GEMINI_FREE_MODELS_TEST')
        data={'models':[
            {'name':'models/gemini-2.5-flash','supportedGenerationMethods':['generateContent']},
            {'name':'models/gemini-3.5-flash-lite','supportedGenerationMethods':['generateContent']},
            {'name':'models/gemini-3.1-flash-lite','supportedGenerationMethods':['countTokens']},
            {'name':'models/gemini-4-carbon','supportedGenerationMethods':['generateContent']},
        ]}
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):return None
            def read(self,limit):return json.dumps(data).encode('utf-8')
        with patch.object(ai_search.urllib.request,'urlopen',return_value=Response()) as get:
            result=ai_search.available_free_models()
            self.assertEqual(result['models'],[{'id':'gemini-3.5-flash-lite','label':ai_search.FREE_MODELS['gemini-3.5-flash-lite']}])
            ai_search.available_free_models()
            self.assertEqual(get.call_count,1)
            self.assertTrue(get.call_args.args[0].full_url.startswith('https://generativelanguage.googleapis.com/v1beta/models?'))
            self.assertNotIn('FAKE_KEY',str(result))

    def test_no_paid_grounding_allowed(self):
        ai_search.save_key('FAKE_KEY_FOR_GEMINI_FREE_MODELS_TEST')
        with self.assertRaisesRegex(ValueError,'não faz parte da API gratuita'):
            ai_search._request_model('gemini-3.5-flash-lite','teste',use_web=True)
        with self.assertRaisesRegex(ValueError,'não disponível para todos'):
            ai_search._request_model('gemini-2.5-flash-lite','teste')

    def test_quota_error_is_classified_and_cooldown_saved(self):
        from email.message import Message
        headers=Message();headers['Retry-After']='30'
        payload={'error':{'message':'Too many requests per minute','details':[]}}
        error=urllib.error.HTTPError('https://example.com',429,'Too Many Requests',headers,io.BytesIO(json.dumps(payload).encode('utf-8')))
        result=ai_search._classify_error(error)
        self.assertEqual(result.error_type,'rate_limit')
        self.assertEqual(result.retry_after,30)
        self.assertTrue(ai_search._cooldown())

    def test_old_config_migrates_without_mutating_original(self):
        conf=Path(self.tmp.name)/'config.json'
        old=monitor.config()
        old['ai_model']='gemini-2.5-flash-lite'
        old['ai_web_search']=True
        conf.write_text(json.dumps(old),encoding='utf-8')
        with patch.object(monitor,'CONFIG',conf):
            data=monitor.config()
            self.assertEqual(data['ai_model'],'gemini-3.5-flash-lite')
            self.assertFalse(data['ai_web_search'])
            self.assertEqual(json.loads(conf.read_text())['ai_model'],'gemini-2.5-flash-lite')
            with self.assertRaisesRegex(ValueError,'modelos Gemini suportados'):
                monitor.save_config({'ai_model':'gemini-2.5-flash-lite'})
            with self.assertRaisesRegex(ValueError,'não está disponível'):
                monitor.save_config({'ai_web_search':True})


class ExecutionEventTests(unittest.TestCase):
    def test_real_steps_logs_survive_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'executions.json'
            store=ExecutionStore(path)
            run=store.start('scan')
            store.step(run,0)
            store.log(run,'info','Verificando configurações')
            store.end_step(run,0)
            store.step(run,1)
            store.sources(run,2,4,fetched=16)
            snapshot=store.snapshot()[0]
            self.assertEqual(snapshot['progress'],round(100*(1+0.5)/6))
            self.assertEqual(snapshot['metrics']['fetched'],16)
            self.assertEqual(snapshot['steps'][0]['status'],'success')
            self.assertEqual(snapshot['steps'][1]['status'],'running')
            store.end_step(run,1)
            store.finish(run,{'ok':True,'new':3},True)
            persisted=ExecutionStore(path).snapshot()[0]
            self.assertEqual(persisted['status'],'success')
            self.assertEqual(persisted['result']['new'],3)
            self.assertEqual(persisted['progress'],100)

    def test_monitor_html_logs_and_event_listeners(self):
        html=(ROOT/'web/index.html').read_text('utf-8')
        js=(ROOT/'web/assets/app.js').read_text('utf-8')
        for tag in ('executionMonitor','executionSteps','executionLogs','executionProgressFill','executionBadge','toastStack'):
            self.assertIn(f'id="{tag}"',html)
        for fn in ('renderExecution','refreshExecutions','showToast'):
            self.assertIn('function '+fn+'(',js)
        self.assertIn("api('executions')",js)
        self.assertIn('refreshFreeModels()',js)


if __name__=='__main__':unittest.main()

class RealHTTPMonitorTests(unittest.TestCase):
    """API event stream uses actual backend execution, with no external traffic."""
    def test_scan_and_ai_execution_have_traceable_events(self):
        import threading
        import time
        from http.server import ThreadingHTTPServer
        from urllib.request import Request, urlopen
        from radar import db
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            cfg=monitor.config()
            cfg['sources']={key:(key=='gupy') for key in cfg['sources']}
            cfg['ai_daily_cap']=2
            conf=folder/'config.json';conf.write_text(json.dumps(cfg),encoding='utf-8')
            store=ExecutionStore(folder/'executions.json')
            mocks=[patch.object(monitor,'CONFIG',conf),patch.object(db,'DB_PATH',folder/'jobs.sqlite'),
                   patch.object(monitor,'EXECUTIONS',store),patch.object(monitor,'notify',return_value=0),
                   patch.object(monitor,'collect',return_value=[('Gupy',[],'')]),
                   patch.object(ai_search,'KEY_FILE',folder/'gemini.key'),
                   patch.dict('os.environ',{'GEMINI_API_KEY':''})]
            for m in mocks:m.start()
            monitor.STATE.update({'running':False,'ai_running':False,'last_result':None,'ai_last_result':None})
            srv=ThreadingHTTPServer(('127.0.0.1',0),monitor.Handler)
            worker=threading.Thread(target=srv.serve_forever,daemon=True);worker.start()
            base=f'http://127.0.0.1:{srv.server_port}/api/'
            def fetch(url,method='GET'):
                req=Request(base+url,method=method,headers={'Content-Type':'application/json'},data=(b'{}' if method=='POST' else None))
                with urlopen(req,timeout=4) as resp:return json.loads(resp.read())
            try:
                self.assertEqual(len(fetch('ai/models')['models']),2)
                scan=fetch('scan','POST');self.assertTrue(scan['id'])
                for _ in range(80):
                    job=next((x for x in fetch('executions')['executions'] if x['id']==scan['id']),None)
                    if job and job['status']!='running':break
                    time.sleep(.03)
                self.assertEqual(job['status'],'success')
                self.assertEqual(job['progress'],100)
                self.assertEqual(len(job['steps']),6)
                self.assertTrue(any('Gupy' in x['message'] for x in job['logs']))
                ai=fetch('ai/run','POST')
                for _ in range(80):
                    job=next((x for x in fetch('executions')['executions'] if x['id']==ai['id']),None)
                    if job and job['status']!='running':break
                    time.sleep(.03)
                self.assertEqual(job['status'],'error')
                self.assertTrue(any('chave' in x['message'].lower() for x in job['logs']))
            finally:
                srv.shutdown();srv.server_close();worker.join(timeout=2)
                for m in reversed(mocks):m.stop()
                monitor.STATE.update({'running':False,'ai_running':False,'last_result':None,'ai_last_result':None})
