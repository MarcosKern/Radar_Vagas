"""Geração determinística de currículos ATS em DOCX (sem pacotes externos).

Alinha apenas trechos do perfil cadastrado às exigências do anúncio.
Nunca inventa cargos, períodos, competências ou resultados.
"""
from __future__ import annotations
import io
import re
import unicodedata
import zipfile
from copy import deepcopy
from html import unescape
from xml.sax.saxutils import escape

DEFAULT_TEMPLATE = {
    'font': 'Arial', 'accent': '#5367A4',
    'include_projects': True, 'include_certifications': True,
    'include_languages': True, 'max_bullets_per_job': 4,
    'max_skills': 18, 'default_language': 'pt',
    # Controls for actual DOCX formatting; defaults retain the V0.10 appearance.
    'layout_preset': 'classic', 'page_size': 'A4', 'margin_mm': 17,
    'body_font_pt': 9, 'name_font_pt': 17, 'section_font_pt': 10,
    'line_spacing': 1.12, 'section_spacing_pt': 5,
    'header_alignment': 'left',
    'section_order': ['summary','skills','experience','education','certifications','projects','languages'],
}
SECTION_NAMES=('summary','skills','experience','education','certifications','projects','languages')
DEFAULT_PROFILE = {
    'full_name': '',
    'email': '',
    'phone': '',
    'location': '',
    'linkedin': '',
    'github': '',
    'headline_pt': '',
    'headline_en': '',
    'summary_pt': '',
    'summary_en': '',
    'skills_pt': '',
    'skills_en': '',
    'experience_pt': '',
    'experience_en': '',
    'education_pt': '',
    'education_en': '',
    'certifications_pt': '',
    'certifications_en': '',
    'projects_pt': '',
    'projects_en': '',
    'languages_pt': '',
    'languages_en': '',
}

PROFILE_KEYS=tuple(DEFAULT_PROFILE)
TEMPLATE_KEYS=tuple(DEFAULT_TEMPLATE)

def cleaned(text):
    return re.sub(r'\s+',' ',unicodedata.normalize('NFKD',str(text or '')).encode('ascii','ignore').decode().lower()).strip()

def safe_text(value,limit=5000):
    if not isinstance(value,str):raise ValueError('Todos os campos do currículo devem ser texto')
    if len(value)>limit:raise ValueError('Campo do currículo excede o limite permitido')
    return value.strip().replace('\x00','')

def normalize_profile(data):
    if not isinstance(data,dict) or set(data)-set(PROFILE_KEYS):raise ValueError('Campos do perfil inválidos')
    result=deepcopy(DEFAULT_PROFILE)
    for key,value in data.items():result[key]=safe_text(value,12000 if key.startswith('experience_') else 5000)
    # Perfis vazios são válidos para instalações limpas e podem ser preenchidos ou importados depois.
    return result

def normalize_template(data):
    if not isinstance(data,dict) or set(data)-set(TEMPLATE_KEYS):raise ValueError('Configuração de modelo inválida')
    result=deepcopy(DEFAULT_TEMPLATE)
    for key,value in data.items():
        if key in ('include_projects','include_certifications','include_languages') and type(value) is not bool:raise ValueError('Seções do currículo inválidas')
        if key=='font' and value not in ('Arial','Calibri','Aptos','Liberation Sans'):raise ValueError('Fonte inválida')
        if key=='accent' and (not isinstance(value,str) or re.fullmatch('#[0-9A-Fa-f]{6}',value) is None):raise ValueError('Cor inválida')
        if key=='default_language' and value not in ('pt','en'):raise ValueError('Idioma inválido')
        if key=='max_bullets_per_job' and (type(value) is not int or not 1<=value<=7):raise ValueError('Quantidade de tópicos inválida')
        if key=='max_skills' and (type(value) is not int or not 6<=value<=35):raise ValueError('Quantidade de competências inválida')
        if key=='layout_preset' and value not in ('classic','compact','modern'):raise ValueError('Estilo do currículo inválido')
        if key=='page_size' and value not in ('A4','Letter'):raise ValueError('Tamanho da página inválido')
        if key=='margin_mm' and (type(value) is not int or not 10<=value<=30):raise ValueError('Margens inválidas')
        if key=='body_font_pt' and (type(value) is not int or not 8<=value<=12):raise ValueError('Tamanho do texto inválido')
        if key=='name_font_pt' and (type(value) is not int or not 14<=value<=26):raise ValueError('Tamanho do nome inválido')
        if key=='section_font_pt' and (type(value) is not int or not 9<=value<=15):raise ValueError('Tamanho do título inválido')
        if key=='line_spacing' and (not isinstance(value,(int,float)) or type(value) is bool or not 1<=value<=1.5):raise ValueError('Entrelinhas inválidas')
        if key=='section_spacing_pt' and (type(value) is not int or not 0<=value<=18):raise ValueError('Espaçamento inválido')
        if key=='header_alignment' and value not in ('left','center'):raise ValueError('Alinhamento inválido')
        if key=='section_order' and (not isinstance(value,list) or len(value)!=len(SECTION_NAMES) or set(value)!=set(SECTION_NAMES) or len(set(value))!=len(SECTION_NAMES)):raise ValueError('Ordem das seções inválida')
        result[key]=value
    return result

# Correspondências com o texto do anúncio. A lista base é sempre a lista declarada pelo candidato.
ALIASES={
 'azure':['microsoft azure','azure','cloud computing'],
 'microsoft azure':['microsoft azure','azure','cloud computing'],
 'linux':['linux','unix'], 'sql':['sql','database','banco de dados','bancos de dados'],
 'terraform':['terraform','infrastructure as code','iac','infraestrutura como codigo'],
 'go':['golang','go language','linguagem go','terraform provider'],
 'python':['python'], 'vmware vsphere':['vmware','vsphere','virtualization','virtualizacao'],
 'proxmox':['proxmox'], 'docker':['docker','containers','conteiner'],
 'kubernetes':['kubernetes','k8s'], 'wireshark':['wireshark','packet capture','analise de trafego'],
 'tcp/ip':['tcp/ip','tcp','ip networking','protocolos de rede'], 'dns':['dns'],
 'vpn':['vpn'], 'firewall':['firewall'], 'prometheus':['prometheus'],
 'grafana':['grafana'], 'zabbix':['zabbix'], 'devsecops':['devsecops','secure development'],
 'owasp':['owasp','application security','seguranca de aplicacoes'],
 'troubleshooting':['troubleshooting','incident response','incidentes','suporte tecnico','technical support','it support','diagnostico','root cause'],
 'git':['git','version control','controle de versao'],
 'github actions':['github actions','workflow automation'],
 'ci/cd':['ci/cd','pipelines','continuous integration','continuous deployment'],
 'jira':['jira'], 'confluence':['confluence'], 'bash':['bash','shell'], 'powershell':['powershell'],
}

def phrase_present(text,phrase):
    norm=cleaned(text); needle=cleaned(phrase)
    if not needle:return False
    return bool(re.search(r'(?<![a-z0-9])'+re.escape(needle)+r'(?![a-z0-9])',norm))

def skill_matched(skill,job_text):
    key=cleaned(skill)
    aliases=ALIASES.get(key,[skill]);return any(phrase_present(job_text,a) for a in aliases)

def parse_jobs(value):
    blocks=[s.strip() for s in re.split(r'\n\s*\n',value.strip()) if s.strip()]
    result=[]
    for block in blocks:
        lines=[l.strip() for l in block.splitlines() if l.strip()]
        if not lines:continue
        header=[p.strip() for p in lines[0].split('|',2)]
        title=header[0]
        role=header[1] if len(header)>1 else ''
        period=header[2] if len(header)>2 else ''
        bullets=[l.lstrip('-• ').strip() for l in lines[1:] if l.strip().startswith(('-','•'))]
        result.append((title,role,period,bullets))
    return result

def focus_bullets(bullets,text,count):
    search=cleaned(text)
    terms=[t for t in re.split(r'[^a-z0-9]+',search) if len(t)>=4]
    generic={'with','para','como','and','from','including','using','cloud','remoto','vaga','junior','senior','experience','experiencia','empresa','team','work'}
    terms=set(t for t in terms if t not in generic)
    # Reorganizar apenas - nunca criar bullets novos.
    def rank(b):
        c=cleaned(b)
        return sum(2 for t in terms if re.search(r'(?<![a-z0-9])'+re.escape(t)+r'(?![a-z0-9])',c))
    return sorted(bullets,key=rank,reverse=True)[:count]

def parsed_lines(value):
    return [[p.strip() for p in line.split('|',2)] for line in str(value or '').splitlines() if line.strip()]

def tailored_data(job,profile,template,language):
    language='en' if language=='en' else 'pt'
    text=' '.join(str(job.get(k) or '') for k in ('title','description','level'))
    available=[s.strip() for s in profile['skills_'+language].replace('\n',';').split(';') if s.strip()]
    matched=[x for x in available if skill_matched(x,text)]
    ordered=matched+[x for x in available if x not in matched]
    ordered=ordered[:template['max_skills']]
    experiences=parse_jobs(profile['experience_'+language])
    experiences=[(company,role,period,focus_bullets(bullets,text,template['max_bullets_per_job'])) for company,role,period,bullets in experiences]
    return {'language':language,'skills':ordered,'matched':matched,'experience':experiences,
            'education':parsed_lines(profile['education_'+language]),
            'certifications':parsed_lines(profile['certifications_'+language]),
            'projects':parsed_lines(profile['projects_'+language]),
            'has_description':bool(str(job.get('description') or '').strip())}

def _run(text,bold=False,color=None):
    fmt='<w:rPr>'+('<w:b/>' if bold else '')+(f'<w:color w:val="{color}"/>' if color else '')+'</w:rPr>'
    text=escape(str(text))
    return f'<w:r>{fmt}<w:t xml:space="preserve">{text}</w:t></w:r>'

def _para(text,style='Normal',bold=False,color=None):
    return f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>{_run(text,bold,color)}</w:p>'

def _styles(template):
    font=template['font']; accent=template['accent'][1:]
    body=template['body_font_pt']*2
    name=template['name_font_pt']*2
    section=template['section_font_pt']*2
    spacing=round(template['line_spacing']*240)
    before=template['section_spacing_pt']*20
    compact=template['layout_preset']=='compact'
    modern=template['layout_preset']=='modern'
    normal_after=36 if compact else 75
    bullet_after=16 if compact else 36
    border=('' if compact else f'<w:pBdr><w:bottom w:val="single" w:color="{accent}" w:sz="{10 if modern else 7}" w:space="3"/></w:pBdr>')
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="{font}" w:hAnsi="{font}"/><w:sz w:val="{body}"/><w:color w:val="263242"/></w:rPr></w:rPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:pPr><w:spacing w:after="{normal_after}" w:line="{spacing}" w:lineRule="auto"/></w:pPr><w:rPr><w:rFonts w:ascii="{font}" w:hAnsi="{font}"/><w:sz w:val="{body}"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Name"><w:name w:val="Name"/><w:pPr><w:spacing w:after="36"/></w:pPr><w:rPr><w:rFonts w:ascii="{font}" w:hAnsi="{font}"/><w:b/><w:sz w:val="{name}"/><w:color w:val="{accent}"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Headline"><w:name w:val="Headline"/><w:pPr><w:spacing w:after="78"/></w:pPr><w:rPr><w:b/><w:sz w:val="{body+2}"/><w:color w:val="42526A"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Contact"><w:name w:val="Contact"/><w:pPr><w:spacing w:after="32"/></w:pPr><w:rPr><w:sz w:val="{max(15,body-1)}"/><w:color w:val="4B5D70"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Section"><w:name w:val="Section"/><w:pPr><w:spacing w:before="{before}" w:after="60"/>{border}</w:pPr><w:rPr><w:b/><w:color w:val="{accent}"/><w:sz w:val="{section}"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Job"><w:name w:val="Job"/><w:pPr><w:spacing w:before="60" w:after="38"/></w:pPr><w:rPr><w:b/><w:sz w:val="{body}"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Bullet"><w:name w:val="Bullet"/><w:pPr><w:ind w:left="235" w:hanging="170"/><w:spacing w:after="{bullet_after}" w:line="{spacing}" w:lineRule="auto"/></w:pPr><w:rPr><w:sz w:val="{body}"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Compact"><w:name w:val="Compact"/><w:pPr><w:spacing w:after="36"/></w:pPr><w:rPr><w:sz w:val="{body}"/></w:rPr></w:style>
</w:styles>'''

def generate_docx(job,profile=None,template=None,language='pt'):
    profile=normalize_profile(profile or {})
    template=normalize_template(template or {})
    if language not in ('pt','en'):raise ValueError('Idioma inválido')
    v=tailored_data(job,profile,template,language)
    h={'pt':{'summary':'RESUMO PROFISSIONAL','skills':'COMPETÊNCIAS TÉCNICAS','experience':'EXPERIÊNCIA PROFISSIONAL','education':'FORMAÇÃO ACADÊMICA','certifications':'CERTIFICAÇÕES','projects':'PROJETOS TÉCNICOS','languages':'IDIOMAS'},
       'en':{'summary':'PROFESSIONAL SUMMARY','skills':'TECHNICAL SKILLS','experience':'WORK EXPERIENCE','education':'EDUCATION','certifications':'CERTIFICATIONS','projects':'TECHNICAL PROJECTS','languages':'LANGUAGES'}}[language]
    paras=[]
    # Header is always visible, with a configurable alignment.
    alignment={'left':'left','center':'center'}[template['header_alignment']]
    header=[]
    header.append(_para(profile['full_name'],'Name'))
    header.append(_para(profile['headline_'+language],'Headline'))
    header.append(_para('  |  '.join(x for x in (profile['phone'],profile['email'],profile['location']) if x),'Contact'))
    header.append(_para('  |  '.join(x for x in (profile['linkedin'],profile['github']) if x),'Contact'))
    if alignment=='center':
        header=[part.replace('<w:pPr>', '<w:pPr><w:jc w:val="center"/>',1) for part in header]
    paras.extend(header)
    content={
        'summary':[_para(h['summary'],'Section'),_para(profile['summary_'+language])],
        'skills':[_para(h['skills'],'Section'),_para('  •  '.join(v['skills']),'Compact')],
        'experience':[_para(h['experience'],'Section')],
        'education':[_para(h['education'],'Section')]+[_para('  |  '.join(parts),'Compact') for parts in v['education']],
    }
    for company,role,period,bullets in v['experience']:
        content['experience'].append(_para('  |  '.join(x for x in (company,role,period) if x),'Job'))
        for bullet in bullets:content['experience'].append(_para('• '+bullet,'Bullet'))
    if template['include_certifications'] and v['certifications']:
        content['certifications']=[_para(h['certifications'],'Section')]+[_para('  |  '.join(parts),'Compact') for parts in v['certifications']]
    if template['include_projects'] and v['projects']:
        content['projects']=[_para(h['projects'],'Section')]+[_para('  |  '.join(parts),'Compact') for parts in v['projects']]
    if template['include_languages'] and profile['languages_'+language]:
        content['languages']=[_para(h['languages'],'Section'),_para(profile['languages_'+language],'Compact')]
    for section in template['section_order']:
        paras.extend(content.get(section,[]))
    page_width,page_height=(11906,16838) if template['page_size']=='A4' else (12240,15840)
    margin=round(template['margin_mm']*1440/25.4)
    page_margins=f'<w:sectPr><w:pgSz w:w="{page_width}" w:h="{page_height}"/><w:pgMar w:top="{margin}" w:right="{margin}" w:bottom="{margin}" w:left="{margin}" w:header="450" w:footer="450" w:gutter="0"/></w:sectPr>'
    document=f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{"".join(paras)}{page_margins}</w:body></w:document>'
    content_types='''<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>'''
    rels='''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>'''
    styles_rel='''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''
    core='''<?xml version="1.0" encoding="UTF-8"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Currículo profissional</dc:title><dc:creator>Radar de vagas</dc:creator></cp:coreProperties>'''
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
        for name,payload in {'[Content_Types].xml':content_types,'_rels/.rels':rels,
                'word/document.xml':document,'word/styles.xml':_styles(template),
                'word/_rels/document.xml.rels':styles_rel,'docProps/core.xml':core}.items():
            z.writestr(name,payload.encode('utf-8'))
    return buf.getvalue(),v
