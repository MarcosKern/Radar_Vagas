"""Filtros automáticos configuráveis, com correspondência contextual de senioridade.

Vagas descartadas por este módulo NÃO são gravadas em Bloqueados:
voltam a ser elegíveis em buscas futuras se a configuração mudar.
"""
from __future__ import annotations
import re
from .helpers import norm, plain

LEVEL_PRESETS = {
    'senior': ('Sênior / Senior / Sr.', True, ('senior', 'sr', 'sr.', 'senior-level')),
    'pleno': ('Pleno / Mid-level / Intermediate', True, ('pleno', 'mid-level', 'mid level', 'midlevel', 'intermediate', 'mid-senior', 'middle')),
    'lead': ('Lead / Tech Lead / Líder', True, ('tech lead', 'team lead', 'technical lead', 'engineering lead', 'lead', 'leader', 'lider', 'lider tecnico')),
    'staff': ('Staff / Principal', True, ('staff', 'principal')),
    'manager': ('Gerente / Manager / Diretor', True, ('manager', 'gerente', 'director', 'diretor', 'head of', 'coordenador', 'coordinator', 'supervisor')),
    'architect': ('Architect / Arquiteto', True, ('architect', 'arquiteto', 'arquiteta')),
    'intern': ('Estágio / Internship', False, ('estagio', 'estagiario', 'estagiaria', 'intern', 'internship')),
    'junior': ('Júnior / Entry-level', False, ('junior', 'jr', 'jr.', 'entry-level', 'entry level', 'analyst i', 'analista i', 'associate')),
}
DEFAULT_EXCLUDED = {k: default for k,(_,default,_) in LEVEL_PRESETS.items()}
DEFAULT_TERMS = ['Tech Lead', 'Head of', 'Coordinator']


def _has(text, term):
    """Termos devem corresponder a palavras inteiras, não fragmentos (ex.: 'sr')."""
    text=norm(text)
    word=norm(term).strip()
    if not word:return False
    pattern=r'(?<![\w])'+re.escape(word).replace(r'\ ',r'\s+')+r'(?![\w])'
    return bool(re.search(pattern,text))


def _remove_company_name(text, company):
    """Remove apenas a razão social COMPLETA do campo examinado.

    Nunca procurar senioridade concatenando cargo+empresa. Uma empresa
    chamada Senior Sistemas não implica uma vaga sênior.
    """
    normalized = norm(text)
    name = norm(company).strip()
    if not name:
        return normalized
    # Retira sufixos societários da empresa quando aparecem no cadastro,
    # mas não no título (ex.: "Senior Sistemas Ltda").
    variants = {name}
    suffix = r'(?:ltda\.?|sa|s\.?\s*a\.?|inc\.?|llc|eireli|corp\.?|limited)'
    shorter = re.sub(rf'(?:[\s,\.-]+{suffix})+$', '', name).strip(' .,-')
    if shorter and len(shorter) >= 5:
        variants.add(shorter)
    for candidate in sorted(variants, key=len, reverse=True):
        normalized = re.sub(
            r'(?<![\w])' + re.escape(candidate).replace(r'\ ', r'\s+') + r'(?![\w])',
            ' ', normalized,
        )
    return re.sub(r'\s+', ' ', normalized).strip()


def _role_clause(text):
    """Analisa só a indicação de cargo, não a equipe com quem trabalhará."""
    return re.split(
        r'\b(?:que (?:ira|vai|trabalha|atuara)|para (?:atuar|trabalhar|colaborar)|'
        r'junto (?:a|com)|working with|works with|alongside|with (?:the|our|a) '
        r'|com (?:a|uma|o) equipe|em parceria com|in a team with)\b',
        text, maxsplit=1,
    )[0].strip()


def _match(text, cfg):
    for key, (_, _, patterns) in LEVEL_PRESETS.items():
        if not cfg.get(key,False):continue
        for term in patterns:
            if _has(text,term):return {'category':key, 'reason':LEVEL_PRESETS[key][0], 'match':term}
    for term in cfg.get('_custom',[]):
        if _has(text,term):return {'category':'custom','reason':'Termo personalizado: '+term,'match':term}
    return None


def _explicit_description_fragments(description):
    """Examina apenas trechos sobre o nível do cargo, nunca referências gerais à equipe.

    Ex: 'Trabalhará com engenheiros seniores' NÃO indica senioridade da vaga.
    """
    text=norm(description)[:15000]
    expressions=[
        r'(?:senioridade|nivel da vaga|nivel do cargo|perfil da vaga|experience level|seniority|job level|role level|position level)\s*[:\-–]\s*([^\n.;|]{1,70})',
        r'(?:vaga|cargo|posicao|position|role|oportunidade)\s+(?:para|de|for|as)\s+([^\n.;|]{1,60})',
        r'(?:buscamos|procuramos|contratamos|hiring|looking for)\s+(?:um|uma|a|an)?\s*([^\n.;|]{1,55})',
    ]
    for pattern in expressions:
        for match in re.finditer(pattern,text,re.I):
            yield match.group(1)


def exclusion_details(job, cfg):
    """Retorna o motivo exato ou None; regras têm precedência sobre pontuação.

    Não altera vagas cadastradas manualmente, que permanecem sob controle humano.
    """
    if str(job.get('source','')).lower()=='manual':return None
    values=cfg.get('exclude_seniority')
    levels={k:bool(values.get(k,DEFAULT_EXCLUDED[k])) for k in LEVEL_PRESETS} if isinstance(values,dict) else dict(DEFAULT_EXCLUDED)
    custom=cfg.get('exclude_custom_terms',DEFAULT_TERMS)
    custom=[x.strip() for x in custom if isinstance(x,str) and x.strip()] if isinstance(custom,list) else list(DEFAULT_TERMS)
    levels['_custom']=custom
    company=job.get('company','')
    title=_remove_company_name(job.get('title',''),company)
    # Somente cargo e campo de nível, não nome da empresa/fonte/local.
    for place,content in [('Título',title),('Senioridade',job.get('level',''))]:
        found=_match(content,levels)
        if found:return {**found,'where':place}
    for section in _explicit_description_fragments(job.get('description','')):
        # Remover nome da empresa também de trechos como
        # "Buscamos um analista para Senior Sistemas".
        section=_remove_company_name(section,company)
        section=_role_clause(section)
        found=_match(section,levels)
        # Se o anúncio pede explicitamente um júnior, menções a seniors no
        # mesmo trecho geralmente descrevem colegas/mentores, não o cargo.
        if found and found['category'] not in ('junior','custom'):
            junior_in_section=any(_has(section,t) for t in LEVEL_PRESETS['junior'][2])
            junior_in_title=any(_has(job.get('title',''),t) for t in LEVEL_PRESETS['junior'][2])
            if junior_in_section and junior_in_title:continue
        if found:return {**found,'where':'Descrição explícita'}
    return None


def exclusion_reason(job,cfg):
    found=exclusion_details(job,cfg)
    return f"{found['reason']} ({found['where'].lower()})" if found else None
