"""Scoring transparente, conservador: elegibilidade > título > experiência > habilidades."""
import re
from datetime import datetime, timezone
from .helpers import norm, age_days
from .exclusion import exclusion_details, _remove_company_name


def contains(text, word):
    if not word: return False
    text,word=norm(text),norm(word)
    if len(word)<=3: return bool(re.search(r'(?<!\w)'+re.escape(word)+r'(?!\w)',text))
    return word in text


def local_allowed(job,cfg):
    loc=norm(job.get('location',''))
    if not loc: return False
    # UF isolada não significa automaticamente que a cidade esteja na região metropolitana.
    return any(norm(c) in loc for c in cfg.get('local_cities',[]))


def evaluate(job,cfg,skip_exclusion=False):
    title=job.get('title',''); mode=norm(job.get('mode',''))
    full=title+' '+job.get('description','')
    loc=norm(job.get('location',''))
    reasons=[]
    if not skip_exclusion and exclusion_details(job,cfg):
        return None
    if not any(contains(title,t) for t in cfg.get('role_terms',[])):
        return None
    if norm(job.get('company','')) in [norm(c) for c in cfg.get('blocked_companies',[])]: return None
    if job.get('eligible')=='no' and cfg.get('strict_brazil_eligibility',True): return None
    is_remote='remot' in mode
    is_local= 'hibrid' in mode or 'presencial' in mode or 'on-site' in mode
    if is_remote:
        if not cfg.get('include_remote',True): return None
    else:
        if not cfg.get('include_local',True): return None
        if not local_allowed(job,cfg): return None
    age=age_days(job.get('published'))
    max_age=int(cfg.get('max_age_days',7))
    if age is not None and age>max_age:return None
    deadline=job.get('extra',{}).get('deadline') or job.get('extra',{}).get('expiry')
    if deadline and age_days(deadline) is not None and age_days(deadline)>0: return None
    score=28
    terms=cfg.get('role_terms',[])
    matched_roles=[t for t in terms if contains(title,t)]
    score += min(23,12+4*len(matched_roles))
    reasons.append('Função alinhada: '+', '.join(matched_roles[:3]))
    skills=cfg.get('profile_skills',[])
    matched_skills=[s for s in skills if contains(full,s)]
    score+=min(22,len(matched_skills)*4)
    if matched_skills: reasons.append('Tecnologias: '+', '.join(matched_skills[:5]))
    level=_remove_company_name(title,job.get('company',''))+' '+job.get('level','')
    is_junior=any(contains(level,t) for t in cfg.get('junior_terms',[]))
    if is_junior: score+=13;reasons.append('Nível júnior/entrada')
    elif contains(level,'pleno') or contains(level,'mid-level') or contains(level,'mid '): score-=16;reasons.append('Nível pleno: conferir requisitos')
    elif contains(level,'senior') or contains(level,'sr.'): score-=18;reasons.append('Nível sênior (filtro de exclusão desativado)')
    else: reasons.append('Senioridade não explicitada')
    if is_remote:
        if job.get('eligible')=='yes':score+=9;reasons.append('Elegibilidade Brasil/mundial indicada')
        else: score-=12;reasons.append('Elegibilidade para Brasil não confirmada')
    else:
        score+=10; reasons.append('Região metropolitana de Porto Alegre')
    if age is not None:
        if age <= 3: score+=7
        elif age <= 7: score+=4
    else:
        score-=7;reasons.append('Data de publicação indisponível')
    score=min(100,max(0,score))
    if score < int(cfg.get('min_score',48)):return None
    return score,reasons,matched_skills,is_junior
