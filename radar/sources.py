"""Fontes externas com atribuição e parsers tolerantes a atualizações de API."""
from __future__ import annotations
import json
import os
import time
import urllib.parse
import urllib.request
import urllib.error
import re
import xml.etree.ElementTree as ET
from .helpers import plain, list_str, iso_utc, safe_url, norm

USER_AGENT = 'RadarDeVagas/0.14 (+personal-job-search; respect-rate-limits)'


def fetch_json(base, params=None):
    url = base + ('?' + urllib.parse.urlencode(params) if params else '')
    headers={'User-Agent':USER_AGENT,'Accept':'application/json'}
    if 'himalayas.app' in base and os.getenv('HIMALAYAS_API_KEY'):
        headers['Authorization']='Bearer '+os.environ['HIMALAYAS_API_KEY']
    req=urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=22) as resp:
        return json.loads(resp.read(5_000_000).decode('utf-8'))


def record(source, external_id, title, company, location, mode, level, published, url, description='', salary='', eligible='unknown', extra=None):
    url=safe_url(url)
    if not url or not title: return None
    return dict(source=source, external_id=str(external_id or url), title=plain(title)[:250], company=plain(company)[:200] or 'Empresa não informada', location=plain(location)[:220], mode=plain(mode)[:80], level=plain(level)[:70], published=iso_utc(published), url=url, description=plain(description)[:20000], salary=plain(salary)[:140], eligible=eligible, extra=extra or {})


def parse_gupy(d):
    raw = d.get('data',d.get('jobs',[])) if isinstance(d,dict) else []
    out=[]
    for j in raw:
        if not isinstance(j,dict): continue
        mode = {'remote':'Remoto','hybrid':'Híbrido','on-site':'Presencial','onsite':'Presencial'}.get(j.get('workplaceType'), str(j.get('workplaceType','')))
        loc = ', '.join(x for x in (j.get('city'),j.get('state')) if x)
        x=record('Gupy',j.get('id'),j.get('name',j.get('title')),j.get('careerPageName',j.get('company')),loc,mode,'',j.get('publishedDate'),j.get('jobUrl'),j.get('description',''),extra={'deadline':iso_utc(j.get('applicationDeadline'))})
        if x: out.append(x)
    return out


def parse_himalayas(d):
    out=[]
    for j in d.get('jobs',[]) if isinstance(d,dict) else []:
        countries=j.get('locationRestrictions') or []
        country_tokens=[norm(c.get('alpha2', c.get('name','')) if isinstance(c,dict) else c) for c in countries]
        eligible='yes' if not country_tokens or any(c in ('br','brazil','brasil') for c in country_tokens) else 'no'
        loc='Mundial' if not countries else list_str(countries)
        seniority=j.get('seniority') or ''
        salary=''
        if j.get('minSalary') or j.get('maxSalary'):
            salary=f"{j.get('currency','')} {j.get('minSalary') or '?'}–{j.get('maxSalary') or '?'} / {j.get('salaryPeriod') or 'ano'}"
        x=record('Himalayas',j.get('guid'),j.get('title'),j.get('companyName'),loc,'Remoto',list_str(seniority),j.get('pubDate'),j.get('applicationLink'),j.get('description') or j.get('excerpt',''),salary,eligible,extra={'expiry':iso_utc(j.get('expiryDate'))})
        if x: out.append(x)
    return out


def parse_jobicy(d):
    out=[]
    for j in d.get('jobs',[]) if isinstance(d,dict) else []:
        loc=list_str(j.get('jobGeo',j.get('geo','')))
        low=norm(loc)
        eligible = 'yes' if any(c in low for c in ('worldwide','anywhere','global','latin america','latam','south america','brazil','brasil','remote - worldwide')) else ('no' if any(c in low for c in ('usa only','us only','united states','europe only','uk only')) else 'unknown')
        x=record('Jobicy',j.get('id'),j.get('jobTitle',j.get('title')),j.get('companyName'),loc,'Remoto',j.get('jobLevel',j.get('jobType','')),j.get('pubDate',j.get('date')),j.get('url'),j.get('jobDescription',j.get('description','')),j.get('annualSalaryMin','') if not j.get('annualSalaryMax') else f"{j.get('salaryCurrency','')} {j.get('annualSalaryMin','?')}–{j.get('annualSalaryMax','?')}/ano",eligible)
        if x: out.append(x)
    return out


def parse_remotive(d):
    out=[]
    for j in d.get('jobs',[]) if isinstance(d,dict) else []:
        loc=list_str(j.get('candidate_required_location',''))
        low=norm(loc)
        eligible='yes' if not low or any(c in low for c in ('worldwide','anywhere','global','latin america','latam','south america','brazil','brasil')) else ('unknown' if 'america' in low else 'no')
        x=record('Remotive',j.get('id'),j.get('title'),j.get('company_name'),loc,'Remoto',j.get('job_type',''),j.get('publication_date'),j.get('url'),j.get('description',''),j.get('salary',''),eligible)
        if x: out.append(x)
    return out



# APIs oficiais com acesso publico / feeds RSS; slugs de empresas configuraveis.
def fetch_xml(url):
    req=urllib.request.Request(url,headers={'User-Agent':USER_AGENT,'Accept':'application/rss+xml, application/xml, text/xml'})
    with urllib.request.urlopen(req,timeout=22) as resp:
        return ET.fromstring(resp.read(5_000_000))


def board_spec(value):
    """Entrada `slug | Nome da Empresa`; evita interpolacao de caminhos arbitrarios."""
    if not isinstance(value,str):return None
    parts=[x.strip() for x in value.split('|',1)]
    slug=parts[0]
    if not re.fullmatch(r'[A-Za-z0-9_-]{2,65}',slug):return None
    return slug, plain(parts[1] if len(parts)>1 and parts[1] else slug)[:100]


def remote_eligibility(location):
    """Nao pressupor que 'remote' significa que uma pessoa no Brasil pode aplicar."""
    s=norm(location)
    if not s or s.strip() in ('remote','remoto','work from home','home office'):
        return 'unknown'
    positive=('brazil','brasil','latin america','latam','south america','worldwide','anywhere','global','remote worldwide')
    if re.search(r'\b(except|excluding|exclude|not available in|no applicants from|excluding applicants from)\s+(?:residents of\s+)?(?:brazil|brasil)\b',s):return 'no'
    if any(term in s for term in positive):return 'yes'
    negative=('united states','us only','usa only','united kingdom','uk only','europe only','european union','canada only','australia only','remote us','remote usa','remote eu','remote uk')
    if any(term in s for term in negative):return 'no'
    # Explicit US- or EU-country location for remote work does not prove Brazil eligible.
    if re.search(r'\b(usa|us|uk|eu|de|fr|gb|ca)\b',s):return 'no'
    return 'unknown'


def workplace(value,location='',title=''):
    k=norm(value).replace('_','-')
    if k in ('remote','remoto','fully remote','home office'):return 'Remoto'
    if k in ('hybrid','hibrido'):return 'Híbrido'
    if k in ('onsite','on-site','on site','presencial'):return 'Presencial'
    probe=norm(str(location)+' '+str(title))
    if 'hybrid' in probe or 'hibrid' in probe:return 'Híbrido'
    if 'remote' in probe or 'remot' in probe or 'work from home' in probe:return 'Remoto'
    return 'Não informado'


def parse_remoteok(d):
    out=[]
    for j in d if isinstance(d,list) else []:
        if not isinstance(j,dict) or not j.get('position'):continue
        loc=list_str(j.get('location'))
        sal=''
        if j.get('salary_min') or j.get('salary_max'):
            sal=f"{j.get('salary_min') or '?'}–{j.get('salary_max') or '?'} / ano (moeda a confirmar)"
        x=record('Remote OK',j.get('id'),j.get('position'),j.get('company'),loc,'Remoto','',j.get('date') or j.get('epoch'),j.get('url'),(j.get('description') or '')+' '+' '.join(j.get('tags') or []),sal,remote_eligibility(loc))
        if x:out.append(x)
    return out


def parse_wwr(root):
    out=[]
    for item in root.findall('.//item'):
        title=plain(item.findtext('title'))
        company,position=('','')
        if ': ' in title:company,position=title.split(': ',1)
        else:position=title
        desc=item.findtext('description') or ''
        # RSS geralmente nao disponibiliza um campo estruturado para elegibilidade.
        snippet=plain(desc)
        m=re.search(r'(?i)\b(?:location|region|where|localiza[cç][aã]o)\s*:\s*([^.;|]{3,90})',snippet)
        loc=plain(m.group(1)) if m else 'Não especificada'
        x=record('We Work Remotely',item.findtext('guid') or item.findtext('link'),position,company or 'Não informada',loc,'Remoto','',item.findtext('pubDate'),item.findtext('link'),desc,'',remote_eligibility(loc))
        if x:out.append(x)
    return out


def parse_greenhouse(d, company):
    out=[]
    for j in d.get('jobs',[]) if isinstance(d,dict) else []:
        if not isinstance(j,dict):continue
        loc=j.get('location',{})
        loc=loc.get('name','') if isinstance(loc,dict) else list_str(loc)
        mode=workplace('',loc,j.get('title',''))
        x=record('Greenhouse',j.get('id'),j.get('title'),company,loc,mode,'',j.get('first_published'),j.get('absolute_url'),j.get('content',''),'',remote_eligibility(loc) if mode=='Remoto' else 'unknown',extra={'last_updated':iso_utc(j.get('updated_at'))})
        if x:out.append(x)
    return out


def parse_lever(d, company):
    out=[]
    for j in d if isinstance(d,list) else []:
        if not isinstance(j,dict):continue
        categories=j.get('categories') or {}
        loc=list_str(categories.get('allLocations') or categories.get('location',''))
        country=list_str(j.get('country',''))
        if country and country not in loc:loc=(loc+', '+country).strip(', ')
        mode=workplace(j.get('workplaceType',''),loc,j.get('text',''))
        salary=j.get('salaryRange') or {}
        sal=(f"{salary.get('currency','')} {salary.get('min','?')}–{salary.get('max','?')} / {salary.get('interval','')}" if isinstance(salary,dict) and salary else '')
        x=record('Lever',j.get('id'),j.get('text'),company,loc,mode,categories.get('commitment',''),j.get('createdAt'),j.get('hostedUrl') or j.get('applyUrl'),j.get('descriptionPlain') or j.get('description',''),sal,remote_eligibility(loc) if mode=='Remoto' else 'unknown')
        if x:out.append(x)
    return out


def parse_ashby(d,company):
    out=[]
    for j in d.get('jobs',[]) if isinstance(d,dict) else []:
        if not isinstance(j,dict) or j.get('isListed') is False:continue
        loc=list_str(j.get('location',''))
        more=[x.get('location','') for x in j.get('secondaryLocations',[]) if isinstance(x,dict)]
        if more:loc=', '.join([loc]+more)
        mode=workplace(j.get('workplaceType',''),loc,j.get('title',''))
        comp=j.get('compensation') or {}
        sal=comp.get('scrapeableCompensationSalarySummary') or comp.get('compensationTierSummary','') if isinstance(comp,dict) else ''
        x=record('Ashby',j.get('id') or j.get('jobUrl'),j.get('title'),company,loc,mode,j.get('employmentType',''),j.get('publishedAt'),j.get('jobUrl') or j.get('applyUrl'),j.get('descriptionPlain') or j.get('descriptionHtml',''),sal,remote_eligibility(loc) if mode=='Remoto' else 'unknown')
        if x:out.append(x)
    return out


def parse_smartrecruiters(d,company,slug):
    out=[]
    for j in d.get('content',[]) if isinstance(d,dict) else []:
        if not isinstance(j,dict):continue
        loc=j.get('location') or {}
        if not isinstance(loc,dict):loc={}
        pieces=[loc.get('city',''),loc.get('region',''),loc.get('country','')]
        locname=loc.get('fullLocation') or ', '.join(x for x in pieces if x)
        mode=workplace('remote' if loc.get('remote') else ('hybrid' if loc.get('hybrid') else ''),locname,j.get('name',''))
        comp=j.get('company') or {}
        companyname=comp.get('name',company) if isinstance(comp,dict) else company
        level=j.get('experienceLevel') or {}
        level=level.get('label','') if isinstance(level,dict) else list_str(level)
        ident=j.get('id') or j.get('uuid')
        link=j.get('postingUrl') or (f'https://jobs.smartrecruiters.com/{slug}/{ident}' if ident else '')
        x=record('SmartRecruiters',ident,j.get('name'),companyname,locname,mode,level,j.get('releasedDate'),link,'','',remote_eligibility(locname) if mode=='Remoto' else 'unknown')
        if x:out.append(x)
    return out


def collect_boards(name, config_key, config, endpoint, parser, params=None):
    out=[];errors=[];limit=min(40,max(0,len(config.get(config_key,[]))))
    for val in config.get(config_key,[])[:limit]:
        spec=board_spec(val)
        if not spec:
            errors.append(f'Identificador invalido: {str(val)[:30]}');continue
        slug,company=spec
        try:
            data=fetch_json(endpoint.format(slug=urllib.parse.quote(slug,safe='')),params)
            out.extend(parser(data,company,slug) if name=='SmartRecruiters' else parser(data,company))
        except Exception as ex:
            errors.append(f'{company}: {str(ex)[:85]}')
        time.sleep(.10)
    msg='; '.join(errors[:3])+(f' (+{len(errors)-3} erros)' if len(errors)>3 else '') if errors else ''
    return out,msg


def parse_arbeitnow(d):
    out=[]
    for j in d.get('data',[]) if isinstance(d,dict) else []:
        if not isinstance(j,dict):continue
        loc=list_str(j.get('location',''))
        mode='Remoto' if j.get('remote') else workplace('',loc,j.get('title',''))
        x=record('Arbeitnow',j.get('slug'),j.get('title'),j.get('company_name'),loc,mode,'',j.get('created_at'),j.get('url'),j.get('description',''),' ',remote_eligibility(loc) if mode=='Remoto' else 'unknown')
        if x:out.append(x)
    return out


def parse_workable(d,company):
    out=[]
    jobs=d.get('jobs',d.get('results',[])) if isinstance(d,dict) else d
    for j in jobs if isinstance(jobs,list) else []:
        if not isinstance(j,dict):continue
        loc=j.get('location') or {}
        city=(loc.get('city') or '') if isinstance(loc,dict) else list_str(loc)
        country=(loc.get('country') or '') if isinstance(loc,dict) else ''
        locname=', '.join(x for x in [city,country] if x)
        mode=workplace('remote' if j.get('telecommuting') else '',locname,j.get('title',''))
        url=j.get('url') or j.get('application_url') or j.get('shortlink') or (f'https://apply.workable.com/{company.lower().replace(" ","-")}/j/{j["shortcode"]}/' if j.get('shortcode') else '')
        x=record('Workable',j.get('shortcode') or j.get('id'),j.get('title'),company,locname,mode,'',j.get('published_on') or j.get('created_at'),url,j.get('description',''),eligible=remote_eligibility(locname) if mode=='Remoto' else 'unknown')
        if x:out.append(x)
    return out


def parse_recruitee(d,company):
    out=[]
    offers=d.get('offers',d.get('data',[])) if isinstance(d,dict) else []
    for j in offers if isinstance(offers,list) else []:
        if not isinstance(j,dict):continue
        loc=list_str(j.get('location') or j.get('city') or '')
        mode=workplace(j.get('remote') and 'remote' or '',loc,j.get('title',''))
        x=record('Recruitee',j.get('id') or j.get('slug'),j.get('title'),company,loc,mode,'',j.get('published_at') or j.get('created_at'),j.get('careers_url') or j.get('url'),j.get('description') or '',eligible=remote_eligibility(loc) if mode=='Remoto' else 'unknown')
        if x:out.append(x)
    return out


def parse_adzuna(d):
    out=[]
    for j in d.get('results',[]) if isinstance(d,dict) else []:
        if not isinstance(j,dict):continue
        company=(j.get('company') or {}).get('display_name','')
        loc=(j.get('location') or {}).get('display_name','')
        salary=''
        if j.get('salary_min') or j.get('salary_max'):
            salary=f"{j.get('salary_min','?')}–{j.get('salary_max','?')} (moeda da fonte)"
        x=record('Adzuna',j.get('id'),j.get('title'),company,loc,workplace('',loc,j.get('title','')),'',j.get('created'),j.get('redirect_url'),j.get('description',''),salary,remote_eligibility(loc))
        if x:out.append(x)
    return out


# Bounded role+skill combinations, high signal; never cartesian-product the whole profile.
COMBO_PAIRS=[
 ('analista de suporte','Linux'),('analista de suporte','SQL'),('infraestrutura','Azure'),
 ('infraestrutura','VMware'),('cloud','Terraform'),('DevOps','Docker'),
 ('segurança da informação','SIEM'),('suporte técnico','redes'),('IT Support','Linux'),
 ('Technical Support','SQL'),('Cloud Engineer','Azure'),('DevOps','Terraform'),
 ('Security Analyst','SOC'),('Infrastructure Engineer','Linux'),('IT Operations','VMware')]
def search_queries(cfg, key):
    base=[str(x).strip() for x in cfg.get(key,[]) if str(x).strip()]
    limit=max(1,min(20,int(cfg.get('max_queries_per_source',10))))
    if cfg.get('query_combinations',True):
        is_pt=key=='gupy_queries'
        combos=[' '.join((r,s)) for r,s in COMBO_PAIRS if (not is_pt if r[:1].isupper() else is_pt)]
        # Rotate subset each day to expand breadth without excessive API calls.
        rot=int(time.time()//86400)%max(1,len(combos))
        combos=combos[rot:]+combos[:rot]
        base+=combos
    return list(dict.fromkeys(base))[:limit]


def collect(config, on_source_start=None):
    """Yield (source, jobs, error) separately: failure does not erase existing records."""
    flags=config.get('sources',{})
    def begin(name):
        if on_source_start:
            on_source_start(name)
    if config.get('include_local',True) or config.get('include_remote',True):
        if flags.get('gupy',True):
            begin('Gupy')
            found=[]; errors=[]
            kinds=[]
            if config.get('include_remote',True): kinds.append(('remote',None))
            if config.get('include_local',True): kinds.append(('hybrid',config.get('local_state','Rio Grande do Sul')))
            if config.get('include_local',True): kinds.append(('on-site',config.get('local_state','Rio Grande do Sul')))
            # 7 keywords x 3 work models => 21 requests/day; single page/request.
            for kind,state in kinds:
                for q in search_queries(config,'gupy_queries'):
                    params={'jobName':q,'workplaceType':kind,'sortBy':'publishedDate','sortOrder':'desc','limit':25,'offset':0}
                    if state: params['state']=state
                    try: found.extend(parse_gupy(fetch_json('https://portal.gupy.io/api/job-search/jobs',params)))
                    except Exception as ex: errors.append(f'{q}/{kind}: {str(ex)[:90]}')
                    time.sleep(.10)
            yield 'Gupy',found, '; '.join(errors[:3]) + (f' (+{len(errors)-3} erros)' if len(errors)>3 else '') if errors else ''
    # Os ATS sao publicos, mas cada site exige uma lista explicita de empresas.
    # Se o tipo estiver habilitado, mesmo uma lista vazia devolve status visivel.
    boards=[
        ('Greenhouse','greenhouse','greenhouse_boards','https://boards-api.greenhouse.io/v1/boards/{slug}/jobs',parse_greenhouse,{'content':'true'}),
        ('Lever','lever','lever_boards','https://api.lever.co/v0/postings/{slug}',parse_lever,{'mode':'json','limit':100}),
        ('Ashby','ashby','ashby_boards','https://api.ashbyhq.com/posting-api/job-board/{slug}',parse_ashby,{'includeCompensation':'true'}),
        ('SmartRecruiters','smartrecruiters','smartrecruiters_boards','https://api.smartrecruiters.com/v1/companies/{slug}/postings',parse_smartrecruiters,{'limit':100,'offset':0,'destination':'PUBLIC'}),
    ]
    for name,flag,key,url,parser,params in boards:
        if flags.get(flag,True):
            begin(name)
            if not config.get(key):
                yield name,[],'Nenhuma empresa configurada; edite Preferencias'
                continue
            jobs,error=collect_boards(name,key,config,url,parser,params)
            yield name,jobs,error

    # Adicional: dois ATS públicos selecionáveis por organização.
    for name,flag,key,template,parser in [
        ('Workable','workable','workable_boards','https://apply.workable.com/api/v1/widget/accounts/{slug}',parse_workable),
        ('Recruitee','recruitee','recruitee_boards','https://{slug}.recruitee.com/api/offers/',parse_recruitee),
    ]:
        if flags.get(flag,False):
            begin(name)
            if not config.get(key):
                yield name,[],'Configure ao menos uma empresa';continue
            found=[];errors=[]
            for value in config.get(key,[])[:35]:
                spec=board_spec(value)
                if not spec: errors.append('Identificador inválido');continue
                slug,company=spec
                try:
                    data=fetch_json(template.format(slug=slug))
                    found.extend(parser(data,company))
                except urllib.error.HTTPError as ex:
                    if name=='Recruitee' and ex.code==404:
                        # Invalid/removed slug: don't report an API outage. Delete or fix this board in settings.
                        continue
                    errors.append(f'{company}: HTTP {ex.code}')
                except Exception as ex:errors.append(f'{company}: {str(ex)[:80]}')
                time.sleep(.1)
            yield name,found,'; '.join(errors[:3])
    if flags.get('adzuna',False):
        begin('Adzuna')
        appid=os.environ.get('ADZUNA_APP_ID','');key=os.environ.get('ADZUNA_APP_KEY','')
        if not (appid and key):yield 'Adzuna',[],'Configure ADZUNA_APP_ID e ADZUNA_APP_KEY no ambiente'
        else:
            found=[];errors=[]
            for q in search_queries(config,'gupy_queries')[:5]:
                try:
                    d=fetch_json('https://api.adzuna.com/v1/api/jobs/br/search/1',{'app_id':appid,'app_key':key,'what':q,'results_per_page':50,'sort_by':'date'})
                    found.extend(parse_adzuna(d))
                except Exception as ex: errors.append(str(ex)[:80])
            yield 'Adzuna',found,'; '.join(errors[:3])
    if flags.get('arbeitnow',True):
        begin('Arbeitnow')
        try:yield 'Arbeitnow',parse_arbeitnow(fetch_json('https://www.arbeitnow.com/api/job-board-api')),''
        except Exception as ex:yield 'Arbeitnow',[],str(ex)[:200]
    if not config.get('include_remote',True): return
    if flags.get('himalayas',True):
        begin('Himalayas')
        found=[]; errors=[]
        for q in search_queries(config,'remote_queries'):
            try: found.extend(parse_himalayas(fetch_json('https://himalayas.app/jobs/api/search',{'q':q,'sort':'recent','page':1})))
            except Exception as ex: errors.append(f'{q}: {str(ex)[:90]}')
            time.sleep(.15)
        yield 'Himalayas',found, '; '.join(errors[:3]) + (f' (+{len(errors)-3} erros)' if len(errors)>3 else '') if errors else ''
    if flags.get('jobicy',True):
        begin('Jobicy')
        try:
            d=fetch_json('https://jobicy.com/api/jobs',{'count':100})
            yield 'Jobicy',parse_jobicy(d),''
        except Exception as ex: yield 'Jobicy',[],str(ex)[:220]
    if flags.get('remotive',True):
        begin('Remotive')
        try:
            d=fetch_json('https://remotive.com/api/remote-jobs')
            yield 'Remotive',parse_remotive(d),''
        except Exception as ex: yield 'Remotive',[],str(ex)[:220]

    # Novos feeds publicados pelos proprios portais; consultas com atribuicao.
    if flags.get('remoteok',True):
        begin('Remote OK')
        try:yield 'Remote OK',parse_remoteok(fetch_json('https://remoteok.com/api')),''
        except Exception as ex:yield 'Remote OK',[],str(ex)[:220]
    if flags.get('weworkremotely',True):
        begin('We Work Remotely')
        try:yield 'We Work Remotely',parse_wwr(fetch_xml('https://weworkremotely.com/remote-jobs.rss')),''
        except Exception as ex:yield 'We Work Remotely',[],str(ex)[:220]
