"""Cadastro pessoal de oportunidades, independente de filtros e varreduras externas.

Não faz scraping da URL cadastrada; dados informados pelo usuário.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from .db import STATUSES, conn, job_identity, refresh_exclusion_for_manual, _log_status_change
from .helpers import plain, safe_url, norm, age_days, canonical_job_url
from .scoring import contains


MODES = {'Remoto', 'Híbrido', 'Presencial', 'Não informado'}
ELIGIBILITY = {'yes', 'no', 'unknown'}


class DuplicateJobError(ValueError):
    def __init__(self, existing_id):
        super().__init__('Esta vaga já está na lista. Abra o registro existente para gerenciá-la.')
        self.existing_id = existing_id


def _clean_date(value, field):
    value = str(value or '').strip()
    if not value:
        return ''
    try:
        if len(value) != 10 or date.fromisoformat(value).isoformat() != value:
            raise ValueError()
    except ValueError:
        raise ValueError(f'Data inválida no campo {field}. Use AAAA-MM-DD.')
    return value


def validate(data):
    if not isinstance(data, dict):
        raise ValueError('Dados inválidos.')
    title = plain(data.get('title'))[:180]
    company = plain(data.get('company'))[:140]
    if len(title) < 2 or len(company) < 2:
        raise ValueError('Informe cargo e empresa (ao menos 2 caracteres cada).')
    raw_url = str(data.get('url') or '').strip()
    url = safe_url(raw_url)
    if raw_url and not url:
        raise ValueError('O link deve começar com https:// ou http://.')
    mode = str(data.get('mode') or 'Não informado')
    if mode not in MODES:
        raise ValueError('Modalidade inválida.')
    eligible = str(data.get('eligible') or 'unknown')
    if eligible not in ELIGIBILITY:
        raise ValueError('Elegibilidade inválida.')
    status = str(data.get('status') or 'Nova')
    if status not in STATUSES:
        raise ValueError('Etapa de candidatura inválida.')
    pub = _clean_date(data.get('published'), 'publicação')
    followup = _clean_date(data.get('followup'), 'acompanhamento')
    return {
        'title': title, 'company': company,
        'location': plain(data.get('location'))[:200],
        'mode': mode, 'level': plain(data.get('level'))[:80],
        'url': url, 'published': pub + 'T12:00:00+00:00' if pub else '',
        'description': plain(data.get('description'))[:12000],
        'salary': plain(data.get('salary'))[:160],
        'eligible': eligible,
        'notes': str(data.get('notes') or '')[:5000],
        'followup': followup, 'status': status,
        'saved': int(bool(data.get('saved', True))),
        'contract_type': plain(data.get('contract_type'))[:90],
        'recruiter': plain(data.get('recruiter'))[:180],
    }


def score_manual(job, cfg):
    """Heurística indicativa; NÃO autentica descrição ou vaga."""
    title = job['title']
    description = job['description']
    skills = [s for s in cfg.get('profile_skills', []) if contains(title + ' ' + description, s)]
    matched_roles = [r for r in cfg.get('role_terms', []) if contains(title, r)]
    juniors = any(contains(title + ' ' + job['level'], x) for x in cfg.get('junior_terms', []))
    s = 32 + (14 if matched_roles else 0) + min(25, len(skills) * 5) + (11 if juniors else 0)
    reasons = ['Cadastro manual: informações da vaga não verificadas por fonte automática.']
    if matched_roles: reasons.append('Função relacionada: ' + ', '.join(matched_roles[:3]))
    else: reasons.append('Cargo sem correspondência direta nos termos de busca.')
    if skills: reasons.append('Competências mencionadas: ' + ', '.join(skills[:5]))
    else: reasons.append('Descrição sem competências técnicas correspondentes cadastradas.')
    if juniors: reasons.append('Nível júnior/entrada indicado.')
    if job['mode'] == 'Remoto':
        if job['eligible'] == 'yes': s += 8; reasons.append('Elegibilidade Brasil indicada pelo usuário.')
        elif job['eligible'] == 'unknown': reasons.append('Elegibilidade Brasil não confirmada.')
    elif any(norm(c) in norm(job['location']) for c in cfg.get('local_cities', []) if c):
        s += 7; reasons.append('Localização na região de preferência.')
    age = age_days(job['published'])
    if age is not None and age <= 7: s += 5
    return min(100, max(0, s)), reasons, skills


def _canonical_url(value):
    if not value: return ''
    parts = urlsplit(value)
    return canonical_job_url(value)


def _duplicate(c, job, exclude_id=None):
    identity = job_identity(job)
    found = c.execute('SELECT id FROM jobs WHERE fingerprint=? AND id!=? LIMIT 1', (identity, exclude_id or '')).fetchone()
    if found:
        return found['id']
    url = _canonical_url(job['url'])
    if url:
        # A URL é opcional; comparar links exatos normalizados, não apenas hostname.
        for row in c.execute("SELECT id,url FROM jobs WHERE url!='' AND id!=?", (exclude_id or '',)):
            if _canonical_url(row['url']) == url:
                return row['id']
    return None


def add_manual_job(data, cfg, origin="Cadastro manual"):
    j = validate(data)
    score, reasons, skills = score_manual(j, cfg)
    now = datetime.now(timezone.utc).isoformat()
    job_id = 'manual-' + uuid.uuid4().hex[:24]
    fingerprint = job_identity(j)
    with conn() as c:
        exists = _duplicate(c, j)
        if exists: raise DuplicateJobError(exists)
        c.execute('''INSERT INTO jobs
            (id,source,external_id,fingerprint,title,company,location,mode,level,published,url,
             description,salary,eligible,score,reasons,skills,first_seen,last_seen,status,notes,
             followup,saved,applied_at,contract_type,recruiter)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (job_id, 'Manual', job_id, fingerprint, j['title'],j['company'],j['location'],j['mode'],
             j['level'],j['published'],j['url'],j['description'],j['salary'],j['eligible'],
             score,json.dumps(reasons,ensure_ascii=False),json.dumps(skills,ensure_ascii=False),
             now,now,j['status'],j['notes'],j['followup'],j['saved'],now if j['status']=='Candidatada' else '',j['contract_type'],j['recruiter']))
        _log_status_change(c,job_id,None,j['status'],origin,occurred_at=now)
    return job_id


def edit_manual_job(job_id, data, cfg):
    j = validate(data)
    score, reasons, skills = score_manual(j, cfg)
    now = datetime.now(timezone.utc).isoformat()
    with conn() as c:
        existing = c.execute('SELECT source,applied_at,status FROM jobs WHERE id=?',(job_id,)).fetchone()
        if not existing or existing['source'] not in ('Manual','Importação XLSX','Importação CSV'): return False
        other = _duplicate(c,j,exclude_id=job_id)
        if other: raise DuplicateJobError(other)
        c.execute('''UPDATE jobs SET fingerprint=?,title=?,company=?,location=?,mode=?,level=?,
             published=?,url=?,description=?,salary=?,eligible=?,score=?,reasons=?,skills=?,
             last_seen=?,status=?,notes=?,followup=?,saved=?,contract_type=?,recruiter=?,
             applied_at=CASE WHEN ?='Candidatada' AND applied_at='' THEN ? ELSE applied_at END
             WHERE id=? AND source IN ('Manual','Importação XLSX','Importação CSV') ''',
             (job_identity(j),j['title'],j['company'],j['location'],j['mode'],j['level'],
              j['published'],j['url'],j['description'],j['salary'],j['eligible'],score,
              json.dumps(reasons,ensure_ascii=False),json.dumps(skills,ensure_ascii=False),
              now,j['status'],j['notes'],j['followup'],j['saved'],j['contract_type'],j['recruiter'],j['status'],now,job_id))
        _log_status_change(c,job_id,existing['status'],j['status'],'Edição de cadastro',occurred_at=now)
        refresh_exclusion_for_manual(c,job_id)
    return True


def delete_manual_job(job_id):
    with conn() as c:
        deleted=c.execute("DELETE FROM jobs WHERE id=? AND source IN ('Manual','Importação XLSX','Importação CSV')",(job_id,)).rowcount == 1
        if deleted:
            c.execute('DELETE FROM job_status_history WHERE job_id=?',(job_id,))
            refresh_exclusion_for_manual(c,job_id)
        return deleted
