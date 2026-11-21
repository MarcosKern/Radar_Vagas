"""Busca assistida por Gemini API na nuvem, sem Ollama nem SDK adicional.
A chave fica fora do config.json e nunca é devolvida ao frontend.
Os anúncios importados vêm apenas de conectores reais; a IA gera variações
contextualizadas por pesquisa web, sem inventar vagas ou URLs.
"""
from __future__ import annotations
import json
import os
import re
import urllib.request
import urllib.error
import time
import hashlib
from urllib.parse import urlencode
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from email.utils import parsedate_to_datetime
from datetime import date
from .paths import DATA_HOME
from pathlib import Path
from .db import conn, save_jobs, save_ai_run
from .scoring import evaluate
from .exclusion import exclusion_details
from .sources import collect

DEFAULT_MODEL = 'gemini-3.5-flash-lite'
# Somente modelos de texto atuais com cota gratuita publicada e acesso geral
# para novos projetos. A disponibilidade da chave é confirmada via models.list.
FREE_MODELS = {
    'gemini-3.5-flash-lite': 'Gemini 3.5 Flash-Lite · gratuito · recomendado',
    'gemini-3.1-flash-lite': 'Gemini 3.1 Flash-Lite · gratuito',
}
SUPPORTED_MODELS = tuple(FREE_MODELS)
_MODEL_CACHE = {}
_MODEL_CACHE_TTL = 600  # segundos: evita listagem repetitiva a cada refresh do painel
KEY_FILE = DATA_HOME / 'data' / 'gemini.key'
API_BASE = 'https://generativelanguage.googleapis.com/v1beta/models/'
COOLDOWN_FILE = KEY_FILE.with_name('gemini_cooldown.json')

def get_key():
    """Prefer an explicit environment secret, then the local-only saved key."""
    env = (os.environ.get('GEMINI_API_KEY') or '').strip()
    if env:
        return env
    try:
        return KEY_FILE.read_text('utf-8').strip()
    except FileNotFoundError:
        return ''

def key_status():
    return {'provider':'Google Gemini', 'configured':bool(get_key()),
            'source':'ambiente' if os.environ.get('GEMINI_API_KEY','').strip() else ('arquivo local' if KEY_FILE.exists() else 'nenhuma'),
            'model_default':DEFAULT_MODEL, 'web_search_supported':False}

def save_key(value):
    if not isinstance(value,str) or not 15 <= len(value.strip()) <= 300 or re.search(r'\s',value.strip()):
        raise ValueError('Informe uma chave Gemini válida do Google AI Studio.')
    KEY_FILE.parent.mkdir(parents=True,exist_ok=True)
    KEY_FILE.write_text(value.strip(),encoding='utf-8')
    _MODEL_CACHE.clear()
    try:os.chmod(KEY_FILE,0o600)
    except OSError:pass
    return {'configured':True}

def delete_key():
    _MODEL_CACHE.clear()
    try:KEY_FILE.unlink()
    except FileNotFoundError:pass
    return key_status()

def available_free_models(force=False):
    """List only documented free, general-access Gemini text models.

    The response of models.list is checked against a maintained allowlist.
    A model being listed does not prove a remaining quota for generateContent.
    The API key is never included in the response or logs.
    """
    key=get_key()
    candidates=[{'id':id,'label':label} for id,label in FREE_MODELS.items()]
    if not key:
        return {'models':candidates,'verified':False,'configured':False,
                'message':'Modelos com nível gratuito documentado. Cadastre uma chave para confirmar quais estão disponíveis para seu projeto.'}
    digest=hashlib.sha256(key.encode('utf-8')).hexdigest()
    cached=_MODEL_CACHE.get(digest)
    if not force and cached and time.monotonic()-cached[0]< _MODEL_CACHE_TTL:
        return dict(cached[1])
    names=set()
    page_token=''
    for _ in range(5):
        params={'pageSize':100}
        if page_token:params['pageToken']=page_token
        req=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models?'+urlencode(params),
                                   headers={'x-goog-api-key':key},method='GET')
        try:
            with urllib.request.urlopen(req,timeout=15) as response:
                data=json.loads(response.read(300_000))
        except urllib.error.HTTPError as e:raise _classify_error(e) from None
        except (urllib.error.URLError,OSError,TimeoutError) as e:
            raise GeminiAPIError('Não foi possível consultar os modelos Gemini. Verifique a conexão.',None,'network') from e
        for model in data.get('models',[]):
            if not isinstance(model,dict):continue
            name=str(model.get('name','')).removeprefix('models/')
            if name in FREE_MODELS and 'generateContent' in (model.get('supportedGenerationMethods') or []):
                names.add(name)
        page_token=str(data.get('nextPageToken') or '')
        if not page_token:break
    models=[{'id':id,'label':label} for id,label in FREE_MODELS.items() if id in names]
    result={'models':models,'verified':True,'configured':True,
            'message':('Modelos gratuitos encontrados para a chave cadastrada. Cotas e permissões de geração ainda podem limitar chamadas.'
                       if models else 'A API não listou modelos atuais do nível gratuito para sua chave. Confira o projeto no AI Studio.')}
    _MODEL_CACHE[digest]=(time.monotonic(),result)
    if len(_MODEL_CACHE)>8:_MODEL_CACHE.clear();_MODEL_CACHE[digest]=(time.monotonic(),result)
    return dict(result)


def _parse_json_text(s):
    s=s.strip()
    if s.startswith('```'):
        s=re.sub(r'^```(?:json)?\s*','',s,flags=re.I)
        s=re.sub(r'\s*```$','',s)
    try:obj=json.loads(s)
    except json.JSONDecodeError as e:raise ValueError('Gemini retornou texto fora do formato esperado. Tente novamente.') from e
    if not isinstance(obj,dict):raise ValueError('Gemini não retornou um objeto JSON.')
    return obj

class GeminiAPIError(ValueError):
    def __init__(self,message,code=None,error_type=None,retry_after=None):
        super().__init__(message)
        self.code=code
        self.error_type=error_type
        self.retry_after=retry_after


def _cooldown():
    try:
        data=json.loads(COOLDOWN_FILE.read_text('utf-8'))
        if float(data.get('until',0))>time.time():return data
    except (OSError,ValueError,TypeError):pass
    return None


def _set_cooldown(seconds,reason):
    seconds=max(10,min(172800,int(seconds)))
    COOLDOWN_FILE.parent.mkdir(parents=True,exist_ok=True)
    COOLDOWN_FILE.write_text(json.dumps({'until':time.time()+seconds,'reason':reason},ensure_ascii=False),encoding='utf-8')


def _retry_after(header,details):
    value=(header or '').strip()
    if value:
        try:return max(0,int(float(value)))
        except ValueError:
            try:return max(0,int((parsedate_to_datetime(value)-datetime.now(timezone.utc)).total_seconds()))
            except (TypeError,ValueError):pass
    for detail in details:
        if 'RetryInfo' in str(detail.get('@type','')):
            delay=str(detail.get('retryDelay',''))
            matched=re.search(r'^([0-9]+(?:\.[0-9]+)?)s$',delay)
            if matched:return max(1,int(float(matched.group(1))+0.99))
    return None


def _classify_error(e):
    try:data=json.loads(e.read(32000).decode('utf-8','replace'))
    except (ValueError,OSError):data={}
    err=data.get('error') or {}
    msg=str(err.get('message') or '')[:1200]
    details=err.get('details') or []
    desc=' '.join(str(v.get('quotaId',''))+' '+str(v.get('quotaMetric','')) for d in details if isinstance(d,dict) for v in (d.get('violations') or []))
    mix=(msg+' '+desc).casefold()
    delay=_retry_after(e.headers.get('Retry-After'),[d for d in details if isinstance(d,dict)])
    code=e.code
    if code==429:
        if any(word in mix for word in ('perday','per_day','daily','requests per day','rpd')):
            try:
                zone=ZoneInfo('America/Los_Angeles')
                reset=(datetime.now(zone)+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
                delay=max(60,int((reset-datetime.now(zone)).total_seconds()))
            except ZoneInfoNotFoundError:
                # Windows sem banco IANA/tzdata: não requer instalações adicionais.
                delay=24*60*60
            err_type='daily_quota'
            text='Cota diária do Gemini esgotada para este projeto/modelo. Consulte o Google AI Studio; novas buscas com IA ficam suspensas até a próxima janela de cota.'
        elif any(x in mix for x in ('search','grounding')):
            delay=delay or 600
            err_type='grounding_quota'
            text='Cota de Google Search Grounding atingida. Desative a pesquisa fundamentada ou consulte os limites no AI Studio.'
        else:
            delay=delay or 90
            err_type='rate_limit'
            text='Gemini limitou o número de requisições/tokens. A pesquisa com IA ficará temporariamente suspensa para evitar novas falhas.'
        _set_cooldown(delay,text)
        return GeminiAPIError(f'HTTP 429: {text}',429,err_type,delay)
    known={400:('invalid_request','Requisição Gemini recusada; confira modelo e opções.'),
           401:('unauthorized','Chave Gemini inválida ou expirada.'),
           402:('payment','Conta sem créditos para este plano.'),
           403:('forbidden','Projeto sem permissão ou sem acesso ao modelo.'),
           404:('model_unavailable','Modelo indisponível para este projeto. Experimente Gemini 3.5 Flash-Lite ou 3.1 Flash-Lite.'),
           500:('server','Falha temporária no serviço Gemini.'),
           503:('overloaded','Serviço Gemini sobrecarregado; tente mais tarde.')}
    kind,text=known.get(code,('http_error','Erro HTTP devolvido pelo Gemini.'))
    if code in (500,503):
        delay=delay or 60
        _set_cooldown(delay,text)
    return GeminiAPIError(f'HTTP {code}: {text}',code,kind,delay)


def _request_model(model, prompt, max_tokens=320, use_web=False):
    key=get_key()
    if not key:raise ValueError('Cadastre a chave Gemini em Configurações → Busca com IA.')
    if model not in SUPPORTED_MODELS:raise ValueError('Modelo não disponível para todos no nível gratuito; escolha um Flash-Lite atual.')
    if use_web:raise ValueError('Google Search Grounding não faz parte da API gratuita destes modelos. Use as fontes públicas para buscar vagas.')
    pause=_cooldown()
    if pause:
        remaining=max(1,int(pause['until']-time.time()))
        raise GeminiAPIError(f'Gemini em espera: {pause["reason"]} Tente novamente em aproximadamente {remaining}s.',429,'cooldown',remaining)
    payload={'contents':[{'parts':[{'text':prompt}]}],
             'generationConfig':{'temperature':0.1,'maxOutputTokens':max(128,min(1200,int(max_tokens))),
                                 'responseMimeType':'application/json'}}
    if use_web:payload['tools']=[{'google_search':{}}]
    req=urllib.request.Request(API_BASE+model+':generateContent',
      data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),
      headers={'Content-Type':'application/json','x-goog-api-key':key},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=55) as response:
            response_data=json.loads(response.read(1_000_000))
    except urllib.error.HTTPError as e:raise _classify_error(e) from None
    except (urllib.error.URLError,OSError,TimeoutError) as e:
        raise GeminiAPIError('Não foi possível acessar Gemini; confira sua conexão.',None,'network') from e
    candidates=response_data.get('candidates') or []
    if not candidates:raise GeminiAPIError('Gemini não retornou resposta: verifique cotas e configurações.',None,'empty')
    parts=(candidates[0].get('content') or {}).get('parts') or []
    content=''.join(p.get('text','') for p in parts if isinstance(p,dict))
    decoded=_parse_json_text(content)
    usage=response_data.get('usageMetadata') or {}
    decoded['_tokens']=sum(max(0,int(usage.get(k) or 0)) for k in ('promptTokenCount','candidatesTokenCount'))
    decoded['_grounded']=bool((candidates[0].get('groundingMetadata') or {}).get('webSearchQueries'))
    return decoded


def test_connection(cfg):
    """Check model listing without generation tokens or extra billing."""
    if not get_key():raise ValueError('Configure a chave Gemini primeiro.')
    model=cfg.get('ai_model',DEFAULT_MODEL)
    if model not in SUPPORTED_MODELS:model=DEFAULT_MODEL
    response=available_free_models(force=True)
    supports=any(m['id']==model for m in response['models'])
    return {'ok':supports,'model':model,
            'message':('Chave aceita: o modelo gratuito aparece na lista deste projeto. Sem consumo de tokens de geração. Isso não garante cota restante.'
                       if supports else 'Este modelo gratuito não está disponível para o projeto da sua chave. Atualize a lista de modelos e selecione outro.')}

def _clean_terms(value, ceiling=6):
    if not isinstance(value,list):return []
    out=[]
    for text in value:
        if not isinstance(text,str):continue
        text=re.sub(r'[\x00-\x1f]',' ',text).strip()[:65]
        if not 3<=len(text)<=65 or 'http' in text.lower():continue
        if text.casefold() not in {v.casefold() for v in out}:out.append(text)
        if len(out)>=ceiling:break
    return out

def _requests_today():
    with conn() as c:
        row=c.execute('SELECT calls,tokens FROM ai_usage WHERE day=?',(date.today().isoformat(),)).fetchone()
    return dict(row) if row else {'calls':0,'tokens':0}

def run(cfg,tracker=None,run_id=None):
    """Single small-generation request; sources supply real vacancies, not invented URLs."""
    def step(idx):
        if tracker and run_id:tracker.step(run_id,idx)
    def end(idx):
        if tracker and run_id:tracker.end_step(run_id,idx)
    def event(level,message,**metrics):
        if tracker and run_id:tracker.log(run_id,level,message,**metrics)
    step(0)
    cap=max(0,min(10,int(cfg.get('ai_daily_cap',2))))
    usage=_requests_today()
    if usage['calls']>=cap:raise ValueError(f'Limite diário definido no RadarVagas atingido ({cap} consulta(s)). Altere a configuração ou aguarde o dia seguinte.')
    if not get_key():raise ValueError('Cadastre a chave gratuita Gemini em Configurações → Busca com IA.')
    model=cfg.get('ai_model',DEFAULT_MODEL)
    if model not in SUPPORTED_MODELS:model=DEFAULT_MODEL
    if _cooldown():
        pause=_cooldown()
        remaining=max(1,int(pause['until']-time.time()))
        raise GeminiAPIError(f'Gemini em espera: {pause["reason"]} Tente novamente em aproximadamente {remaining}s.',429,'cooldown',remaining)
    event('success',f'Chave configurada. Limite local: {usage["calls"]}/{cap} geração(ões) hoje.')
    end(0)
    step(1)
    active={k:bool(cfg.get('sources',{}).get(k)) for k in ('gupy','himalayas')}
    if not any(active.values()):raise ValueError('Ative Gupy ou Himalayas para recuperar anúncios reais.')
    event('success',f'Modelo selecionado: {model}. Uma geração de termos por execução.')
    if cfg.get('ai_web_search',False):
        event('warning','A pesquisa web integrada do Gemini requer faturamento nesses modelos; será desconsiderada no modo gratuito. A busca nas fontes públicas permanece ativa.')
    end(1)
    step(2)
    prompt=(
        'Você produz somente JSON compacto {"pt": ["..."], "en": ["..."]}. '
        'Para uma candidata júnior do Brasil, crie até 4 combinações curtas por idioma, '
        'com 2 a 4 palavras, de cargos de Suporte N1/N2, Infraestrutura TI, Cloud, DevOps, '
        'SecOps, Operations. Contexto: Linux, Azure, SQL, VMware, Terraform, Python, Go e redes. '
        'Evite senior/lead e não invente vagas, empresas ou URLs. Sem comentários. '
        'Não repita os termos existentes. BR: '+', '.join(cfg.get('gupy_queries',[])[:8])+'. '
        'EN: '+', '.join(cfg.get('remote_queries',[])[:8])
    )
    # Count each actual generation call once, including failures. No retry storm.
    with conn() as c:
        c.execute('INSERT INTO ai_usage(day,calls,tokens) VALUES(?,1,0) ON CONFLICT(day) DO UPDATE SET calls=calls+1',
                  (date.today().isoformat(),))
    event('info','Solicitação enviada à API Gemini; aguardando resposta...',calls=usage['calls']+1)
    generated=_request_model(model,prompt,int(cfg.get('ai_max_output_tokens',320)),False)
    tokens=int(generated.get('_tokens') or 0)
    with conn() as c:
        c.execute('UPDATE ai_usage SET tokens=tokens+? WHERE day=?',(tokens,date.today().isoformat()))
    pt=_clean_terms(generated.get('pt',[]),4);en=_clean_terms(generated.get('en',[]),4)
    if not pt and not en:raise ValueError('Gemini não produziu termos de pesquisa utilizáveis.')
    event('success',f'IA respondeu com {len(pt)} termos BR e {len(en)} termos internacionais; {tokens} tokens.',tokens=tokens)
    end(2)
    step(3)
    copy=dict(cfg);copy['gupy_queries']=pt;copy['remote_queries']=en
    copy['max_queries_per_source']=min(4,max(1,int(cfg.get('max_queries_per_source',10))))
    copy['query_combinations']=False
    copy['sources']={k:(bool(v) and k in ('gupy','himalayas')) for k,v in cfg.get('sources',{}).items()}
    fetched=0;matched=[];errors=[];stats={};auto_excluded=0;exclusion_groups={};exclusion_examples=[]
    for source,jobs,error in collect(copy):
        fetched+=len(jobs)
        if error:
            errors.append(source+': '+error[:120])
            event('warning',f'{source}: {error}')
        else:event('success',f'{source}: {len(jobs)} anúncios recebidos.',fetched=fetched)
        for job in jobs:
            exclusion=exclusion_details(job,cfg)
            if exclusion:
                auto_excluded+=1
                label=exclusion['reason']
                exclusion_groups[label]=exclusion_groups.get(label,0)+1
                if len(exclusion_examples)<3:exclusion_examples.append(f"{job.get('title','')[:65]} — {label}")
                continue
            result=evaluate(job,cfg,skip_exclusion=True)
            if result:
                score,reasons,skills,_=result
                reasons.insert(0,'Termos sugeridos pelo Gemini; anúncio obtido de '+source+'.')
                matched.append((job,score,reasons,skills))
    event('info',f'Fontes consultadas: {fetched} anúncios coletados.')
    end(3)
    step(4)
    if auto_excluded:
        event('warning',f'{auto_excluded} vaga(s) excluída(s) automaticamente por senioridade/termos; não são bloqueios manuais.',auto_excluded=auto_excluded)
        for example in exclusion_examples:event('info','Exclusão automática: '+example)
    event('success',f'{len(matched)} vagas atenderam aos filtros de aderência.',qualified=len(matched))
    end(4)
    step(5)
    inserted=save_jobs(matched,stats)
    save_ai_run(model,{'br':pt,'international':en,'google_search_used':False},fetched,inserted,tokens,errors)
    event('success',f'{inserted} vaga(s) nova(s); {stats.get("already_known",0)} repetida(s); {stats.get("excluded",0)} bloqueada(s).',new=inserted)
    end(5)
    return {'ok':True,'model':model,'queries':{'br':pt,'international':en},'fetched':fetched,
            'qualified':len(matched),'new':inserted,'auto_excluded':auto_excluded,'exclusion_groups':exclusion_groups,'excluded':stats.get('excluded',0),
            'already_known':stats.get('already_known',0),'errors':errors,
            'calls_today':_requests_today()['calls'],'tokens':tokens,
            'grounded':False,'grounding_warning':bool(cfg.get('ai_web_search',False)),
            'verification':'Anúncios e links obtidos diretamente das fontes públicas; IA gerou termos.'}
