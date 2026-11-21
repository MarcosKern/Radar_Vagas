#!/usr/bin/env python3
"""Radar de vagas — escaneamento, dashboard e controle de candidaturas.
Requisitos: apenas Python 3.11+. Sem scraping de LinkedIn ou credenciais embutidas.
"""
from __future__ import annotations
import argparse
import os
import csv
import io
import json
import sys
import time
import threading
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from radar.db import rows,runs,ai_runs,save_jobs,save_run,update_job,set_job_ignored,conn,DB_PATH,job_history,opportunity_groups
from radar.scoring import evaluate
from radar.exclusion import exclusion_details, DEFAULT_EXCLUDED, LEVEL_PRESETS, DEFAULT_TERMS
from radar.sources import collect
from radar.notifications import notify
from radar.manual import add_manual_job, edit_manual_job, delete_manual_job, DuplicateJobError
from radar.xlsxio import import_xlsx, export_xlsx, TEMPLATE
from radar.csvio import import_csv, export_csv
from radar.export_filters import parse_options, select_jobs, export_preview
from radar.ai_search import run as run_ai, _requests_today, key_status, save_key, delete_key, test_connection, available_free_models, SUPPORTED_MODELS
from radar.executions import ExecutionStore
from radar.resume import (DEFAULT_PROFILE,DEFAULT_TEMPLATE,normalize_profile,normalize_template,generate_docx)

from radar.paths import DATA_HOME
from radar.updates import APPLY_LOCK, Updates
import secrets

UPDATES = Updates()
UPDATE_TOKEN = secrets.token_urlsafe(32)
CONFIG=DATA_HOME/'config.json'
WEB=ROOT/'web'/'index.html'
SCAN_LOCK=threading.Lock()
STATE={'running':False,'last_result':None,'ai_running':False,'ai_last_result':None}
EXECUTIONS=ExecutionStore()
START_LOCK=threading.Lock()
SETTINGS_FORMAT='radar-de-vagas-settings'
SETTINGS_SCHEMA_VERSION=1
SETTINGS_APP_VERSION='V0.19'
SETTINGS_EDITABLE={'max_age_days','min_score','notify_score','include_remote','include_local','strict_brazil_eligibility','blocked_companies','sources','local_cities','gupy_queries','remote_queries','greenhouse_boards','lever_boards','ashby_boards','smartrecruiters_boards','workable_boards','recruitee_boards','max_queries_per_source','query_combinations','ai_model','ai_daily_cap','ai_max_output_tokens','ai_web_search','ui_brand','ui_menu','ui_titles','exclude_seniority','exclude_custom_terms','resume_profile','resume_template','profile_name','profile_role','profile_skills','role_terms','junior_terms','local_state','scan_limit_per_source','notes','ai_enabled'}


def _runtime_defaults():
    """Configuração técnica mínima em memória; nenhuma preferência do usuário é incluída no pacote.

    Um backup de configurações JSON ou o primeiro salvamento cria config.json.
    Fontes desativadas até a configuração explícita para evitar buscas acidentais.
    """
    menu=[('dashboard','Visão geral'),('vagas','Oportunidades'),
          ('candidaturas','Candidaturas'),('bloqueados','Bloqueados'),
          ('config','Fontes e filtros'),('relatorios','Histórico de buscas')]
    return {
        'profile_name':'','profile_role':'','profile_skills':[],
        'role_terms':[],'junior_terms':[], 'local_cities':[], 'local_state':'',
        'gupy_queries':[],'remote_queries':[], 'blocked_companies':[],
        'greenhouse_boards':[],'lever_boards':[],'ashby_boards':[],
        'smartrecruiters_boards':[],'workable_boards':[],'recruitee_boards':[],
        'sources':{name:False for name in ('gupy','himalayas','jobicy','remotive','remoteok',
                  'weworkremotely','greenhouse','lever','ashby','smartrecruiters',
                  'arbeitnow','workable','recruitee','adzuna')},
        'max_age_days':7, 'min_score':48, 'notify_score':72,
        'scan_limit_per_source':150,'max_queries_per_source':10,
        'include_remote':True,'include_local':True,
        'strict_brazil_eligibility':True,'query_combinations':False,
        'ai_model':SUPPORTED_MODELS[0],'ai_daily_cap':0,
        'ai_max_output_tokens':320,'ai_enabled':False,'ai_web_search':False,
        'ui_brand':'Radar de vagas',
        'ui_menu':[{'id':k,'label':label,'visible':True} for k,label in menu],
        'ui_titles':{'dashboard':'Visão geral','vagas':'Oportunidades',
                     'candidaturas':'Candidaturas','bloqueados':'Vagas bloqueadas',
                     'config':'Fontes e filtros','relatorios':'Histórico de buscas'},
        'exclude_seniority':dict(DEFAULT_EXCLUDED),'exclude_custom_terms':[],
        'resume_profile':{key:'' for key in DEFAULT_PROFILE},
        'resume_template':dict(DEFAULT_TEMPLATE), 'notes':'',
    }


def config():
    data=json.loads(CONFIG.read_text('utf8')) if CONFIG.exists() else _runtime_defaults()
    # Migração compatível com versões anteriores: nunca reutilizar modelos 2.5
    # em chaves novas sem acesso ou habilitar Grounding pago inadvertidamente.
    if data.get('ai_model') not in SUPPORTED_MODELS:data['ai_model']=SUPPORTED_MODELS[0]
    data['ai_web_search']=False
    # Substituído na v8 por filtros configuráveis com correspondência contextual.
    data.pop('exclude_title_terms',None)
    data.setdefault('exclude_seniority',dict(DEFAULT_EXCLUDED))
    data.setdefault('exclude_custom_terms',list(DEFAULT_TERMS))
    data['resume_profile']=normalize_profile(data.get('resume_profile') or {})
    data['resume_template']=normalize_template(data.get('resume_template') or {})
    return data

def save_config(changes,*,persist=True):
    data=config()
    editable=SETTINGS_EDITABLE

    for key,val in changes.items():
        if key not in editable:continue
        if key in ('max_age_days','min_score','notify_score','max_queries_per_source','ai_daily_cap','ai_max_output_tokens'):
            if not isinstance(val,int) or isinstance(val,bool) or val<0 or val>({'ai_max_output_tokens':3000,'max_queries_per_source':20,'ai_daily_cap':10}.get(key,100)):raise ValueError(f'Número inválido: {key}')
        if key in ('include_remote','include_local','strict_brazil_eligibility','query_combinations','ai_web_search') and not isinstance(val,bool):raise ValueError('Opção inválida')
        if key=='ai_web_search' and val:raise ValueError('Pesquisa Grounding não está disponível na API Gemini gratuita para esses modelos. Utilize as fontes públicas do RadarVagas.')
        if key in ('profile_name','profile_role','local_state','notes'):
            if not isinstance(val,str) or len(val)>1000:raise ValueError(f'Campo de perfil inválido: {key}')
        if key in ('profile_skills','role_terms','junior_terms'):
            if not isinstance(val,list) or len(val)>100 or any(not isinstance(v,str) or len(v)>120 for v in val):raise ValueError(f'Lista de perfil inválida: {key}')
        if key=='scan_limit_per_source':
            if type(val) is not int or not 1<=val<=2000:raise ValueError('Limite por fonte inválido')
        if key=='ai_enabled' and type(val) is not bool:raise ValueError('Opção de IA inválida')
        if key=='sources':
            if not isinstance(val,dict):raise ValueError('Fontes inválidas')
            val={x:bool(val.get(x,False)) for x in ('gupy','himalayas','jobicy','remotive','remoteok','weworkremotely','greenhouse','lever','ashby','smartrecruiters','arbeitnow','workable','recruitee','adzuna')}
        if key in ('blocked_companies','local_cities','gupy_queries','remote_queries','greenhouse_boards','lever_boards','ashby_boards','smartrecruiters_boards','workable_boards','recruitee_boards'):
            if not isinstance(val,list) or len(val)>40 or any(not isinstance(s,str) or len(s)>120 for s in val):raise ValueError('Lista inválida')
        if key=='exclude_seniority':
            if not isinstance(val,dict) or set(val)!=set(LEVEL_PRESETS) or any(type(v) is not bool for v in val.values()):
                raise ValueError('Selecione valores válidos para todas as categorias de senioridade')
        if key=='exclude_custom_terms':
            if not isinstance(val,list) or len(val)>40 or any(not isinstance(v,str) or not 2<=len(v.strip())<=65 or any(ord(ch)<32 for ch in v) for v in val):
                raise ValueError('A lista deve ter até 40 termos, com 2 a 65 caracteres por item')
            out=[]
            for item in val:
                term=item.strip()
                if term.casefold() not in {x.casefold() for x in out}:out.append(term)
            val=out
        if key=='ai_model':
            import re
            if val not in SUPPORTED_MODELS:raise ValueError('Selecione um dos modelos Gemini suportados')
        if key=='resume_profile':val=normalize_profile(val)
        if key=='resume_template':val=normalize_template(val)
        if key=='ui_brand':
            if not isinstance(val,str) or not 2<=len(val.strip())<=65:raise ValueError('Nome do aplicativo inválido')
            val=val.strip()
        if key=='ui_titles':
            if not isinstance(val,dict) or set(val)-{'dashboard','vagas','candidaturas','bloqueados','config','relatorios'}:raise ValueError('Títulos inválidos')
            if any(not isinstance(v,str) or not 2<=len(v.strip())<=65 for v in val.values()):raise ValueError('Texto de título inválido')
        if key=='ui_menu':
            ids={'dashboard','vagas','candidaturas','bloqueados','config','relatorios'}
            if not isinstance(val,list) or len(val)!=len(ids) or {v.get('id') for v in val if isinstance(v,dict)}!=ids:raise ValueError('Estrutura de menu inválida')
            if any(not isinstance(v,dict) or not isinstance(v.get('visible'),bool) or not isinstance(v.get('label'),str) or not 2<=len(v.get('label','').strip())<=38 for v in val):raise ValueError('Personalização de menu inválida')
            if not next(v for v in val if v['id']=='config')['visible']:raise ValueError('Menu de Configurações não pode ser ocultado')
            if not next(v for v in val if v['id']=='bloqueados')['visible']:raise ValueError('Menu Bloqueados deve permanecer acessível')
        data[key]=val
    if not data['include_remote'] and not data['include_local']:raise ValueError('Ative ao menos uma modalidade')
    if persist:
        tmp=CONFIG.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n','utf8')
        tmp.replace(CONFIG)
    return data


def portable_settings():
    """Somente preferências; não exporta banco, token Gemini ou dados de execução."""
    source=config()
    safe={key:source[key] for key in sorted(SETTINGS_EDITABLE) if key in source}
    return {'format':SETTINGS_FORMAT,'schema_version':SETTINGS_SCHEMA_VERSION,
            'app_version':SETTINGS_APP_VERSION,
            'exported_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'settings':safe,'excluded':['data/jobs.sqlite','data/gemini.key','execution_history']}

def import_portable_settings(payload):
    if not isinstance(payload,dict) or payload.get('format')!=SETTINGS_FORMAT:
        raise ValueError('Arquivo não é um backup de configurações do Radar de vagas.')
    if type(payload.get('schema_version')) is not int or payload['schema_version']!=SETTINGS_SCHEMA_VERSION:
        raise ValueError('Versão de esquema JSON não suportada.')
    changes=payload.get('settings')
    if not isinstance(changes,dict) or not changes:
        raise ValueError('O JSON não contém configurações para importar.')
    if any(key not in SETTINGS_EDITABLE for key in changes):
        raise ValueError('O JSON contém campos desconhecidos ou não permitidos.')
    # Valida todas as seções antes de gravar. Uma falha não altera config.json.
    checked=save_config(changes,persist=False)
    save_config(changes,persist=True)
    return {'imported_count':len(changes),'schema_version':SETTINGS_SCHEMA_VERSION,
            'restart_required':False,'settings':checked}

def _source_total(cfg):
    """Estimate enabled source groups, excluding remote-only feeds if disabled."""
    flags=cfg.get('sources',{})
    remote_only={'himalayas','jobicy','remotive','remoteok','weworkremotely'}
    return sum(1 for name, enabled in flags.items() if enabled and (cfg.get('include_remote',True) or name not in remote_only))


def scan(run_id=None):
    if not SCAN_LOCK.acquire(blocking=False):
        return {'ok':False,'message':'Busca em andamento'}
    if run_id is None:run_id=EXECUTIONS.start('scan')
    STATE['running']=True
    try:
        EXECUTIONS.step(run_id,0)
        cfg=config()
        enabled=_source_total(cfg)
        if enabled<1:raise ValueError('Nenhuma fonte habilitada nas configurações.')
        EXECUTIONS.log(run_id,'success',f'Configurações carregadas: {enabled} fonte(s) habilitada(s).')
        EXECUTIONS.end_step(run_id,0)
        EXECUTIONS.step(run_id,1)
        source_stats={};errors=[];fetched=0;collected=[];complete=0
        def on_source(name):
            EXECUTIONS.log(run_id,'info','Conectando à fonte '+name+'...')
        for name,items,error in collect(cfg,on_source_start=on_source):
            complete+=1
            source_stats[name]={'received':len(items),'error':error or None}
            fetched+=len(items)
            collected.extend(items)
            EXECUTIONS.sources(run_id,complete,max(enabled,complete),fetched=fetched)
            if error:
                errors.append(f'{name}: {error}')
                EXECUTIONS.log(run_id,'warning',f'{name}: {error}')
            else:
                EXECUTIONS.log(run_id,'success',f'{name}: {len(items)} anúncio(s) coletado(s).')
        EXECUTIONS.end_step(run_id,1)
        EXECUTIONS.step(run_id,2)
        qualified=[];auto_excluded=0;exclusion_groups={};examples=[]
        for item in collected:
            reason=exclusion_details(item,cfg)
            if reason:
                auto_excluded+=1
                name=reason['reason']
                exclusion_groups[name]=exclusion_groups.get(name,0)+1
                if len(examples)<4:examples.append(f"{str(item.get('title','Vaga'))[:65]} — {name} ({reason['where'].lower()})")
                continue
            evaluation=evaluate(item,cfg,skip_exclusion=True)
            if evaluation:
                score,reasons,skills,_=evaluation
                qualified.append((item,score,reasons,skills))
        if auto_excluded:
            summary=', '.join(f'{name}: {count}' for name,count in sorted(exclusion_groups.items(),key=lambda i:-i[1])[:5])
            EXECUTIONS.log(run_id,'warning',f'{auto_excluded} vagas descartadas automaticamente por senioridade/termos. {summary}',auto_excluded=auto_excluded)
            for example in examples:EXECUTIONS.log(run_id,'info','Exclusão automática: '+example)
        EXECUTIONS.log(run_id,'success',f'{len(qualified)} vaga(s) compatível(is) entre {fetched} anúncios.',qualified=len(qualified))
        EXECUTIONS.end_step(run_id,2)
        EXECUTIONS.step(run_id,3)
        scan_stats={}
        inserted=save_jobs(qualified,scan_stats)
        EXECUTIONS.log(run_id,'success',f'{inserted} nova(s), {scan_stats.get("already_known",0)} já conhecida(s), {scan_stats.get("excluded",0)} bloqueada(s).',new=inserted)
        EXECUTIONS.end_step(run_id,3)
        EXECUTIONS.step(run_id,4)
        save_run(fetched,inserted,len(qualified),source_stats,errors,excluded=scan_stats.get('excluded',0),already_known=scan_stats.get('already_known',0))
        alerts=notify(cfg.get('notify_score',72))
        EXECUTIONS.log(run_id,'info',f'Etapa de alertas finalizada: {alerts} alerta(s).')
        EXECUTIONS.end_step(run_id,4)
        EXECUTIONS.step(run_id,5)
        result={'ok':True,'fetched':fetched,'qualified':len(qualified),'new':inserted,'excluded':scan_stats.get('excluded',0),'already_known':scan_stats.get('already_known',0),'auto_excluded':auto_excluded,'exclusion_groups':exclusion_groups,'sources':source_stats,'errors':errors,'alerts':alerts,'updated_at':datetime.now(timezone.utc).isoformat()}
        STATE['last_result']=result
        EXECUTIONS.end_step(run_id,5)
        EXECUTIONS.finish(run_id,result,success=True)
        return result
    except Exception as e:
        result={'ok':False,'message':str(e)[:250]}
        STATE['last_result']=result
        EXECUTIONS.finish(run_id,result,success=False)
        return result
    finally:
        STATE['running']=False
        SCAN_LOCK.release()


def csv_text():
    return export_csv().decode('utf-8-sig')


def ai_worker(run_id):
    STATE['ai_running']=True
    try:
        result=run_ai(config(), tracker=EXECUTIONS, run_id=run_id)
        STATE['ai_last_result']=result
        EXECUTIONS.finish(run_id,result,success=bool(result.get('ok')))
    except Exception as e:
        STATE['ai_last_result']={'ok':False,'message':str(e)[:250]}
        EXECUTIONS.finish(run_id,STATE['ai_last_result'],success=False)
    finally:
        STATE['ai_running']=False

class Handler(BaseHTTPRequestHandler):
    server_version='RadarVagas/V0.19'
    def log_message(self, fmt,*args):
        if sys.stderr is not None and not self.path.startswith(('/api/state','/api/executions')):super().log_message(fmt,*args)
    def respond(self,data,status=200):
        b=json.dumps(data,ensure_ascii=False,default=str).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def do_GET(self):
        path=urlparse(self.path).path
        if path in ('/','/index.html'):
            b=WEB.read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
        elif path.startswith('/assets/'):
            # Static assets are packaged with the app; only explicit files are served.
            assets={
                '/assets/bootstrap.min.css':'text/css; charset=utf-8',
                '/assets/bootstrap.bundle.min.js':'text/javascript; charset=utf-8',
                '/assets/tailwind.css':'text/css; charset=utf-8',
                '/assets/custom.css':'text/css; charset=utf-8',
                '/assets/updates.js':'text/javascript; charset=utf-8',
                '/assets/app.js':'text/javascript; charset=utf-8',
                '/assets/favicon.svg':'image/svg+xml',
            }
            mime=assets.get(path)
            asset=ROOT/'web'/path.removeprefix('/')
            if not mime or not asset.is_file():
                self.respond({'error':'Arquivo estático não encontrado'},404);return
            b=asset.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type',mime)
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Length',str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif path in ('/api/resume/docx','/api/resume/template'):
            params=parse_qs(urlparse(self.path).query)
            language=params.get('lang',['pt'])[0]
            if language not in ('pt','en'):self.respond({'error':'Idioma não suportado'},400);return
            cfg=config()
            if path=='/api/resume/docx':
                job_id=params.get('job',[''])[0]
                if not job_id or len(job_id)>120:self.respond({'error':'Identificador inválido'},400);return
                job=next((j for j in rows() if str(j.get('id'))==job_id),None)
                if job is None:self.respond({'error':'Vaga não encontrada'},404);return
            else:job={'title':'','description':'','company':''}
            result,_=generate_docx(job,cfg['resume_profile'],cfg['resume_template'],language)
            import re,unicodedata
            target='Modelo' if path=='/api/resume/template' else str(job.get('company') or job.get('title') or 'Vaga')
            slug=unicodedata.normalize('NFKD',target).encode('ascii','ignore').decode('ascii')
            slug=re.sub(r'[^A-Za-z0-9]+','_',slug).strip('_')[:45] or 'Vaga'
            filename=f'Curriculo_{slug}_{language.upper()}.docx'
            self.send_response(200)
            self.send_header('Content-Type','application/vnd.openxmlformats-officedocument.wordprocessingml.document')
            self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Length',str(len(result)))
            self.end_headers();self.wfile.write(result);return
        elif path=='/api/resume/match':
            params=parse_qs(urlparse(self.path).query)
            job_id=params.get('job',[''])[0]
            language=params.get('lang',['pt'])[0]
            if language not in ('pt','en') or not job_id or len(job_id)>120:
                self.respond({'error':'Parâmetros inválidos'},400);return
            job=next((j for j in rows() if str(j.get('id'))==job_id),None)
            if job is None:self.respond({'error':'Vaga não encontrada'},404);return
            from radar.resume import tailored_data
            cfg=config();v=tailored_data(job,cfg['resume_profile'],cfg['resume_template'],language)
            self.respond({'ok':True,'matched':v['matched'],'has_description':v['has_description']});return
        elif path == '/api/updates/health':
            self.respond({'app':'Radar_Vagas', 'instance':os.getenv('RADAR_INSTANCE',''), 'version':SETTINGS_APP_VERSION})
        elif path == '/api/updates':
            if self.headers.get('Host','').split(':')[0] not in ('localhost','127.0.0.1'):
                self.respond({'error':'Host inválido'},403)
                return
            self.respond({**UPDATES.status(), 'token':UPDATE_TOKEN})
        elif path=='/api/ai/models':
            try:self.respond(available_free_models())
            except Exception as e:self.respond({'error':str(e)[:250]},503)
        elif path.startswith('/api/jobs/') and path.endswith('/history'):
            # Individual application timeline. Read-only and scoped to a single ID.
            job_id=path[len('/api/jobs/'):-len('/history')].strip('/')
            if not job_id or '/' in job_id or len(job_id)>100:
                self.respond({'error':'Identificador inválido'},400);return
            timeline=job_history(job_id)
            if timeline is None:self.respond({'error':'Vaga não encontrada'},404);return
            self.respond({'ok':True,'events':timeline});return
        elif path=='/api/executions':self.respond({'executions':EXECUTIONS.snapshot(12)})
        elif path=='/api/state':
            cfg=config();jobs=rows(limit=10000)
            for item,group in zip(jobs,opportunity_groups(jobs)):
                item['opportunity_group']=group
                details=exclusion_details(item,cfg)
                item['auto_excluded']=bool(details) and item.get('status') in ('Nova','Salva')
            self.respond({'jobs':jobs,'runs':runs(),'ai_runs':ai_runs(),'settings':cfg,'scan':STATE,'ai':{'cloud':key_status(),'usage':_requests_today()}})
        elif path=='/api/export/preview':
            try:self.respond({'ok':True,**export_preview(parse_qs(urlparse(self.path).query),cfg=config())})
            except ValueError as exc:self.respond({'error':str(exc)},400)
        elif path in ('/api/template.xlsx','/api/export.xlsx','/api/export.csv'):
            if path=='/api/template.xlsx':
                payload=TEMPLATE.read_bytes()
                filename='Vagas_template.xlsx'
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            else:
                try:
                    selected=select_jobs(parse_qs(urlparse(self.path).query),cfg=config())
                except ValueError as exc:
                    self.respond({'error':str(exc)},400);return
                if path.endswith('.xlsx'):
                    payload=export_xlsx(selected)
                    filename='Candidaturas_filtradas.xlsx'
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                else:
                    payload=export_csv(selected)
                    filename='Candidaturas_filtradas.csv'
                    mime='text/csv; charset=utf-8'
            self.send_response(200)
            self.send_header('Content-Type',mime)
            self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(payload)))
            self.end_headers();self.wfile.write(payload)
        elif path=='/api/settings/export.json':
            b=(json.dumps(portable_settings(),ensure_ascii=False,indent=2)+'\n').encode('utf-8')
            self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Disposition','attachment; filename="Radar_configuracoes_V0.19.json"')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
        else:self.respond({'error':'Não encontrado'},404)
    def do_DELETE(self):
        origin=self.headers.get('Origin','')
        if origin and urlparse(origin).hostname not in ('127.0.0.1','localhost'):
            self.respond({'error':'Origem não autorizada'},403);return
        path=urlparse(self.path).path
        if path.startswith('/api/manual/'):
            ok=delete_manual_job(path.rsplit('/',1)[-1])
            self.respond({'ok':ok},200 if ok else 404);return
        self.respond({'error':'Rota não encontrada'},404)

    def do_POST(self):
        origin=self.headers.get('Origin','')
        if origin and urlparse(origin).hostname not in ('127.0.0.1','localhost'):
            self.respond({'error':'Origem não autorizada'},403);return
        try:
            size=int(self.headers.get('Content-Length','0'))
            path=urlparse(self.path).path
            if path.startswith('/api/updates/'):
                if (self.headers.get('Host','').split(':')[0] not in ('localhost','127.0.0.1') or
                    not secrets.compare_digest(self.headers.get('X-Radar-Token',''), UPDATE_TOKEN)):
                    self.respond({'error':'Sessão de atualização inválida.'},403)
                    return
                if path == '/api/updates/check':
                    self.respond(UPDATES.check())
                    return
                if path == '/api/updates/apply':
                    if not APPLY_LOCK.acquire(blocking=False):
                        self.respond({'error':'Atualização em andamento.'},409)
                        return
                    try:
                        if STATE['running'] or STATE['ai_running']:
                            self.respond({'error':'Aguarde a conclusão da busca.'},409)
                            return
                        UPDATES.stage()
                        self.server.restart_requested = True
                        try:
                            self.respond({'ok':True})
                        finally:
                            threading.Thread(target=self.server.shutdown, daemon=True).start()
                    finally:
                        if not getattr(self.server,'restart_requested',False):
                            APPLY_LOCK.release()
                    return
            if path=='/api/import.xlsx':
                if size<1 or size>12_000_000:self.respond({'error':'O arquivo XLSX deve ter no máximo 12 MB'},413);return
                imported=import_xlsx(self.rfile.read(size),config())
                self.respond({'ok':True,**imported});return
            if path=='/api/import.csv':
                if size<1 or size>12_000_000:self.respond({'error':'O CSV deve ter até 12 MB'},413);return
                imported=import_csv(self.rfile.read(size),config())
                self.respond({'ok':True,**imported});return
            if path=='/api/settings/import.json':
                if size<1 or size>500_000:self.respond({'error':'JSON de configurações deve ter até 500 KB'},413);return
                payload=json.loads(self.rfile.read(size))
                self.respond({'ok':True,**import_portable_settings(payload)});return
            if size>100_000: self.respond({'error':'Conteúdo muito grande'},413);return
            body=json.loads(self.rfile.read(size) or b'{}')
            if not isinstance(body,dict):raise ValueError('JSON inválido')
            if path=='/api/ai/key':
                if body.get('clear') is True:
                    self.respond({'ok':True,'cloud':delete_key()});return
                saved=save_key(body.get('key'))
                self.respond({'ok':True,**saved});return
            if path=='/api/ai/test':
                if not key_status()['configured']:
                    self.respond({'error':'Configure sua chave Gemini primeiro.'},400);return
                self.respond(test_connection(config()));return
            if path=='/api/ai/run':
                if STATE['ai_running'] or EXECUTIONS.active('ai'):self.respond({'error':'Busca IA em andamento'},409);return
                with START_LOCK:
                    if STATE['ai_running'] or EXECUTIONS.active('ai'):
                        self.respond({'error':'Busca IA em andamento'},409);return
                    run_id=EXECUTIONS.start('ai')
                    STATE['ai_last_result']=None
                    STATE['ai_running']=True
                threading.Thread(target=ai_worker,args=(run_id,),daemon=True).start()
                self.respond({'ok':True,'id':run_id,'message':'Busca Gemini iniciada na nuvem'});return
            if path=='/api/manual':
                created_id=add_manual_job(body,config())
                self.respond({'ok':True,'id':created_id,'message':'Vaga cadastrada na lista de monitoramento'},201);return
            if path.startswith('/api/manual/'):
                edited=edit_manual_job(path.rsplit('/',1)[-1],body,config())
                self.respond({'ok':edited},200 if edited else 404);return
            if path=='/api/scan':
                with START_LOCK:
                    if STATE['running'] or EXECUTIONS.active('scan'):
                        self.respond({'ok':False,'message':'Busca em andamento'},409);return
                    run_id=EXECUTIONS.start('scan')
                    STATE['running']=True
                threading.Thread(target=scan,args=(run_id,),daemon=True).start()
                self.respond({'ok':True,'id':run_id,'message':'Busca iniciada'});return
            if path.startswith('/api/jobs/'):
                job_id=path.rsplit('/',1)[-1]
                if 'ignored' in body and type(body['ignored']) is not bool:
                    raise ValueError('Exclusão inválida')
                fields={k:body[k] for k in ('status','notes','followup','saved','contract_type','recruiter') if k in body}
                if not fields and 'ignored' not in body:
                    raise ValueError('Nenhuma alteração informada')
                found=update_job(job_id,**fields) if fields else True
                if 'ignored' in body:
                    ignored_updated=set_job_ignored(job_id,body['ignored'])
                    found=ignored_updated and found
                self.respond({'ok':found},200 if found else 404);return
            if path=='/api/exclusions/preview':
                title=str(body.get('title') or '')[:180].strip()
                level=str(body.get('level') or '')[:100].strip()
                description=str(body.get('description') or '')[:3000]
                if not title:raise ValueError('Informe um título para testar o filtro')
                current=config()
                if isinstance(body.get('exclude_seniority'),dict):current['exclude_seniority']=body['exclude_seniority']
                if isinstance(body.get('exclude_custom_terms'),list):current['exclude_custom_terms']=body['exclude_custom_terms']
                details=exclusion_details({'title':title,'company':str(body.get('company') or '')[:150],'level':level,'description':description,'source':'Preview'},current)
                self.respond({'ok':True,'excluded':bool(details),'reason':details});return
            if path=='/api/settings':
                self.respond({'ok':True,'settings':save_config(body)});return
            self.respond({'error':'Rota não encontrada'},404)
        except DuplicateJobError as e:self.respond({'error':str(e),'existing_id':e.existing_id},409)
        except (ValueError,TypeError,json.JSONDecodeError) as e:self.respond({'error':str(e)},400)
        except Exception as e:self.respond({'error':str(e)[:250]},500)


def main():
    p=argparse.ArgumentParser(description='Radar de vagas | buscas reais, SQLite e dashboard')
    sub=p.add_subparsers(dest='command')
    sub.add_parser('scan',help='Consulta fontes públicas e registra as oportunidades')
    srv=sub.add_parser('serve',help='Abre painel local na porta 8765')
    srv.add_argument('--port',type=int,default=8765)
    sub.add_parser('export',help='Exporta CSV para data/radarvagas.csv')
    args=p.parse_args()
    if args.command=='scan':
        result=scan()
        print(json.dumps(result,indent=2,ensure_ascii=False));sys.exit(0 if result.get('ok') and not result.get('errors') else 1)
    elif args.command=='export':
        path=DATA_HOME/'data'/'Vagas_exportadas.csv';path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(export_csv(select_jobs({})));print(f'CSV de candidaturas salvo em {path}')
    else:
        port=getattr(args,'port',8765)
        if not os.getenv('RADAR_SUPERVISED'):
            from desktop.start import supervise
            sys.exit(supervise(ROOT, DATA_HOME, port))
        server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
        server.daemon_threads=False
        conn().close()
        print(f'RadarVagas disponível em http://127.0.0.1:{port}/ (Ctrl+C para sair)',flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt:print('\nDesligado.')
        finally:server.server_close()
        if getattr(server,"restart_requested",False):sys.exit(75)

if __name__=='__main__':main()
