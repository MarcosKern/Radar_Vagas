"""Validated, deterministic selection shared by export preview, XLSX and CSV.

No browser-side filter is trusted: the server applies these options for every download.
"""
from __future__ import annotations
from datetime import date
from .db import rows, APPLICATION_STATUSES, opportunity_groups
from .exclusion import exclusion_details

SCOPES = {'applications', 'all', 'active', 'saved', 'blocked'}
STATUS_OPTIONS = {'all', 'Nova', 'Salva', *APPLICATION_STATUSES, 'Descartada'}
DATE_FIELDS = {'applied_at', 'first_seen', 'published'}
MODES = {'all', 'Remoto', 'Híbrido', 'Presencial', 'Não informado'}


def parse_options(params):
    """Accept dict[str,str] or parse_qs-like dict[str,list[str]]."""
    def first(k, default=''):
        v = params.get(k, default)
        return str(v[0] if isinstance(v, (tuple, list)) and v else v or default).strip()
    options = {
        'scope': first('scope','applications'),
        'status': first('status','all'),
        'company': first('company',''),
        'mode': first('mode','all'),
        'date_field': first('date_field','applied_at'),
        'date_from': first('date_from',''),
        'date_to': first('date_to',''),
        'include_blocked': first('include_blocked','true').lower(),
        'q': first('q',''),
    }
    if options['scope'] not in SCOPES: raise ValueError('Tipo de exportação inválido')
    if options['status'] not in STATUS_OPTIONS: raise ValueError('Status de exportação inválido')
    if options['mode'] not in MODES: raise ValueError('Modalidade de exportação inválida')
    if options['date_field'] not in DATE_FIELDS: raise ValueError('Campo de data inválido')
    if options['include_blocked'] not in ('true','false'): raise ValueError('Opção de bloqueadas inválida')
    if len(options['company']) > 150 or len(options['q']) > 250: raise ValueError('Filtro de texto muito longo')
    for key in ('date_from','date_to'):
        val = options[key]
        if val:
            try:
                if date.fromisoformat(val).isoformat() != val: raise ValueError
            except ValueError as e: raise ValueError('Informe uma data no formato AAAA-MM-DD') from e
    if options['date_from'] and options['date_to'] and options['date_from'] > options['date_to']:
        raise ValueError('A data inicial não pode superar a data final')
    return options


def select_jobs(options, jobs=None, cfg=None):
    options=parse_options(options)
    data = rows(limit=100000) if jobs is None else list(jobs)
    result=[]
    groups = dict(zip((job['id'] for job in data), opportunity_groups(data))) if options['scope']=='active' else {}
    seen = set()
    for j in data:
        status=j.get('status','Nova')
        blocked=bool(j.get('ignored'))
        scope=options['scope']
        if scope=='applications' and status not in APPLICATION_STATUSES: continue
        if scope=='active' and (blocked or (cfg is not None and status in ('Nova','Salva') and exclusion_details(j,cfg))): continue
        if scope=='saved' and not j.get('saved'): continue
        if scope=='blocked' and not blocked: continue
        if options['include_blocked']=='false' and blocked: continue
        if options['status']!='all' and status!=options['status']:continue
        if options['mode']!='all' and (j.get('mode') or 'Não informado')!=options['mode']:continue
        if options['company'] and (j.get('company') or '').casefold()!=options['company'].casefold():continue
        if options['q']:
            text=' '.join(str(j.get(k) or '') for k in ('title','company','notes','recruiter','location','description'))
            if options['q'].casefold() not in text.casefold():continue
        d=str(j.get(options['date_field']) or '')[:10]
        if options['date_from'] and (not d or d<options['date_from']):continue
        if options['date_to'] and (not d or d>options['date_to']):continue
        if groups:
            group = groups[j['id']]
            if group in seen:
                continue
            seen.add(group)
        result.append(j)
    result.sort(key=lambda j:(str(j.get('applied_at') or j.get('first_seen') or ''), str(j.get('id') or '')),reverse=True)
    return result


def export_preview(options, jobs=None, cfg=None):
    result=select_jobs(options,jobs,cfg=cfg)
    statuses={}
    for j in result:
        state=j.get('status','Nova')
        statuses[state]=statuses.get(state,0)+1
    return {'count':len(result),'status_counts':statuses,'blocked':sum(bool(j.get('ignored')) for j in result)}
