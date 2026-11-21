"""Durable, thread-safe execution event journal for the live dashboard.
Events reflect real backend operations, never a simulated timer.
"""
from __future__ import annotations
import copy
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from .paths import DATA_HOME
from pathlib import Path

PATH = DATA_HOME / 'data' / 'executions.json'
STEPS = {
    'scan': ['Validando configurações', 'Consultando fontes públicas', 'Classificando aderência',
             'Salvando e removendo duplicatas', 'Registrando histórico e alertas', 'Finalizando busca'],
    'ai': ['Validando limites e chave', 'Verificando modelo e cotas locais', 'Consultando Gemini',
           'Pesquisando anúncios nas fontes', 'Avaliando aderência', 'Salvando resultados'],
}
LEVELS={'info','success','warning','error'}


def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')


def safe(text):
    text = str(text)[:360]
    # Protect credentials even if a provider unexpectedly echoes an API key.
    text = re.sub(r'(?i)(?:AIza)[A-Za-z0-9_-]{20,}', '[CHAVE_OCULTA]', text)
    text = re.sub(r'(?i)(?:api[_ -]?key|authorization|bearer)\s*[:=]\s*\S+', '[CREDENCIAL_OCULTA]', text)
    return text


class ExecutionStore:
    def __init__(self,path=PATH):
        self.path=Path(path)
        self.lock=threading.RLock()
        try:
            doc=json.loads(self.path.read_text('utf-8'))
            self.items=doc if isinstance(doc,list) else []
        except (FileNotFoundError, ValueError, OSError):
            self.items=[]
        for row in self.items:
            if row.get('status')=='running':
                row['status']='interrupted'
                row['finished_at']=now()
                row.setdefault('logs',[]).append({'at':now(),'level':'warning','message':'Execução interrompida pelo encerramento do aplicativo.'})
        self._save()

    def _save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_name(self.path.name+'.tmp')
        tmp.write_text(json.dumps(self.items,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        os.replace(tmp,self.path)

    def _find(self,id):
        return next((r for r in self.items if r['id']==id),None)

    def start(self,kind):
        if kind not in STEPS:raise ValueError('Tipo de execução desconhecido')
        with self.lock:
            run={'id':uuid.uuid4().hex[:14],'type':kind,'status':'running',
                 'started_at':now(),'finished_at':None,'current_step':None,'progress':0,
                 'steps':[{'label':label,'status':'pending'} for label in STEPS[kind]],
                 'logs':[],'metrics':{'sources_done':0,'sources_total':0,'fetched':0,'new':0,'qualified':0,'auto_excluded':0},
                 'result':None}
            self.items.insert(0,run)
            self.items=self.items[:35]
            self._save()
            return run['id']

    def active(self,kind=None):
        with self.lock:
            return any(r['status']=='running' and (not kind or kind==r['type']) for r in self.items)

    def step(self,id,index):
        with self.lock:
            r=self._find(id)
            if not r or r['status']!='running':return
            r['current_step']=index
            if 0<=index<len(r['steps']):r['steps'][index]['status']='running'
            r['progress']=round(100*index/len(r['steps']))
            self._save()

    def end_step(self,id,index):
        with self.lock:
            r=self._find(id)
            if not r or r['status']!='running':return
            if 0<=index<len(r['steps']):r['steps'][index]['status']='success'
            r['progress']=round(100*(index+1)/len(r['steps']))
            self._save()

    def sources(self,id,completed,total,**counts):
        with self.lock:
            r=self._find(id)
            if not r or r['status']!='running':return
            r['metrics'].update({'sources_done':completed,'sources_total':total,**counts})
            r['progress']=round(100*(1+min(1,completed/max(1,total)))/len(r['steps']))
            self._save()

    def log(self,id,level,message,**metrics):
        with self.lock:
            r=self._find(id)
            if not r:return
            level=level if level in LEVELS else 'info'
            r['logs'].append({'at':now(),'level':level,'message':safe(message)})
            r['logs']=r['logs'][-200:]
            for k,v in metrics.items():
                if k in {'new','qualified','fetched','tokens','calls','retry_after','auto_excluded'}:
                    r['metrics'][k]=v
            self._save()

    def finish(self,id,result,success=True):
        with self.lock:
            r=self._find(id)
            if not r:return
            if success:
                r['status']='warning' if result.get('errors') else 'success'
                r['progress']=100
                for item in r['steps']:
                    if item['status']=='running':item['status']='success'
                r['logs'].append({'at':now(),'level':'success','message':'Busca concluída.'})
            else:
                r['status']='error'
                for item in r['steps']:
                    if item['status']=='running':item['status']='error'
                r['logs'].append({'at':now(),'level':'error','message':safe(result.get('message','Falha ao executar busca.'))})
            r['finished_at']=now()
            # Never persist API credentials or full job descriptions in the log snapshot.
            r['result']={k:v for k,v in (result or {}).items() if k in {'ok','new','fetched','qualified','message','tokens','model','retry_after','code','error_type','calls_today','auto_excluded'}}
            self._save()

    def snapshot(self,limit=12):
        with self.lock:
            return copy.deepcopy(self.items[:limit])
