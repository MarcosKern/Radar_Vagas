"""Importação/ exportação XLSX compatível com planilhas incompletas, usando somente stdlib.
O template é produzido externamente; este módulo preserva seus cabeçalhos e estilos.
"""
from __future__ import annotations
import io, json, ast, re, zipfile, posixpath, unicodedata, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, date
from pathlib import Path
from .db import conn, rows, update_job, set_job_ignored
from .manual import add_manual_job, DuplicateJobError
from .helpers import norm

ROOT=Path(__file__).resolve().parents[1]
TEMPLATE=ROOT/'templates'/'Vagas_template.xlsx'
NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
RNS='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PNS='http://schemas.openxmlformats.org/package/2006/relationships'
Q=lambda tag:'{'+NS+'}'+tag
ET.register_namespace('',NS)
ET.register_namespace('r',RNS)

HEADERS=['Vaga','Empresa contratante','Status','Data da inscrição','Modalidade','Tipo de contrato','Contato / recrutador','Dias desde inscrição','ID da vaga','URL da vaga','Fonte','Localização','Senioridade','Salário','Aderência (0-100)','Publicado em','Próximo acompanhamento','Anotações','Ignorada','Salva','Elegibilidade Brasil','Competências','Primeira visualização','Última visualização']
DETAIL_HEADERS=['Código / ID','Título do anúncio','Atividades','Requisitos','Escolaridade','Cursos','Horário','Benefícios','Organização do processo','Apresentação da empresa','Programa / duração','Restrições e remuneração','URL da vaga','Fonte','ID da vaga','Anotações detalhadas']

def _norm(text):
    x=unicodedata.normalize('NFKD',str(text or '').strip().lower())
    return re.sub(r'[^a-z0-9]+',' ',''.join(c for c in x if not unicodedata.combining(c))).strip()

def _col(col):
    n=0
    for x in col:n=n*26+ord(x)-64
    return n-1

def _letters(n):
    s='';n+=1
    while n:n,t=divmod(n-1,26);s=chr(65+t)+s
    return s

def _sheets(z):
    book=ET.fromstring(z.read('xl/workbook.xml'))
    rels=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
    rel={r.attrib['Id']:r.attrib['Target'] for r in rels if r.attrib.get('Id')}
    pairs={}
    for s in book.findall('.//'+Q('sheet')):
        target=rel.get(s.attrib.get('{'+RNS+'}id'),'')
        if not target:continue
        path=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
        if path in z.namelist():pairs[s.attrib['name']]=path
    return pairs

def _shared(z):
    if 'xl/sharedStrings.xml' not in z.namelist():return []
    root=ET.fromstring(z.read('xl/sharedStrings.xml'))
    return [''.join(n.text or '' for n in si.iter(Q('t'))) for si in root.findall(Q('si'))]

def _read_cells(z,path,shared):
    root=ET.fromstring(z.read(path));out={}
    for row in root.findall('.//'+Q('sheetData')+'/'+Q('row')):
        ix=int(row.attrib['r']); cols={}
        for c in row.findall(Q('c')):
            ref=c.attrib.get('r','');m=re.match(r'([A-Z]+)',ref)
            if not m:continue
            j=_col(m.group(1))
            typ=c.attrib.get('t')
            if typ=='inlineStr':value=''.join(t.text or '' for t in c.iter(Q('t')))
            else:
                el=c.find(Q('v'));value=el.text if el is not None else ''
                if typ=='s':
                    try:value=shared[int(value)]
                    except (IndexError,ValueError):value=''
                elif typ in ('n',None) and value not in ('',None):
                    try:value=float(value) if '.' in value else int(value)
                    except ValueError:pass
            cols[j]=value
        out[ix]=cols
    return out

def _as_rows(z,name):
    sheets=_sheets(z);path=sheets.get(name)
    return _read_cells(z,path,_shared(z)) if path else {}

def _datetime(value):
    if value is None or value=='':return ''
    if isinstance(value,(int,float)):
        if value<=0:return ''
        try:return (datetime(1899,12,30)+timedelta(days=float(value))).strftime('%Y-%m-%d')
        except (ValueError,OverflowError):return ''
    s=str(value).strip()
    for pat in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y','%Y-%m-%dT%H:%M:%S','%Y-%m-%dT%H:%M:%S%z'):
        try:return datetime.strptime(s[:25],pat).strftime('%Y-%m-%d')
        except ValueError:continue
    if s.startswith('1900'):return ''
    return ''

def _bool(value,default=False):
    if value is None or str(value).strip()=='':return default
    return _norm(value) in ('sim','s','1','true','yes','y','x')

def _status(value):
    n=_norm(value)
    if n in ('candidatura enviada','inscrita','aplicada','aplicado','enviada','candidatada'):return 'Candidatada'
    if n in ('reprovada','reprovado','recusada','recusado','rejeitada','rejeitado'):return 'Rejeitada'
    if n in ('em andamento','aguardando','em analise'):return 'Triagem'
    valid=['Nova','Salva','Candidatada','Triagem','Entrevista','Teste técnico','Proposta','Aprovada','Rejeitada','Descartada']
    for s in valid:
        if _norm(s)==n:return s
    return 'Nova'

def _mode(value):
    n=_norm(value)
    if 'hibrid' in n:return 'Híbrido'
    if 'presen' in n or 'on site' in n:return 'Presencial'
    if 'remot' in n or 'home office' in n:return 'Remoto'
    return 'Não informado'

def _map_row(cellrow,cols):
    return {_norm(name):cellrow.get(j,'') for j,name in cols.items() if name}

def _get(row,*aliases):
    for a in aliases:
        val=row.get(_norm(a),'')
        if val is not None and str(val).strip()!='':return val
    return ''

def parse_xlsx(data:bytes):
    if len(data)>12_000_000:raise ValueError('Arquivo excede 12 MB')
    try:z=zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:raise ValueError('Arquivo XLSX inválido')
    with z:
        if sum(i.file_size for i in z.infolist())>60_000_000:raise ValueError('Planilha descompactada muito grande')
        candidates=_as_rows(z,'Candidaturas')
        if not candidates:
            # Accept a single-sheet workbook with headings on row 1/7.
            sheets=_sheets(z)
            if not sheets:raise ValueError('Planilha sem abas legíveis')
            candidates=_read_cells(z,next(iter(sheets.values())),_shared(z))
        headrow=next((i for i,row in candidates.items() if any(_norm(v) in ('vaga','titulo','cargo','titulo da vaga','job title') for v in row.values()) and any(_norm(v) in ('empresa contratante','empresa','company','company name') for v in row.values())),None)
        if not headrow:raise ValueError('Não encontrei colunas de Vaga e Empresa contratante (ou sinônimos).')
        heads=candidates[headrow]
        items=[];errors=[]
        details=_as_rows(z,'Detalhes das vagas')
        detailcols=details.get(7,{})
        by_id={};by_title={}
        for rno,rec in details.items():
            if rno<=7:continue
            d=_map_row(rec,detailcols)
            id=str(_get(d,'ID da vaga','Código / ID')).strip();title=_norm(_get(d,'Título do anúncio'))
            if id:by_id[id]=d
            if title:by_title[title]=d
        for rno,rec in candidates.items():
            if rno<=headrow:continue
            item=_map_row(rec,heads)
            title=str(_get(item,'Vaga','Cargo','Título','Título da vaga','Job title')).strip()
            company=str(_get(item,'Empresa contratante','Empresa','Company','Company name')).strip()
            if not title and not company:continue
            if not title or not company:
                errors.append(f'Linha {rno}: cargo ou empresa ausente');continue
            id=str(_get(item,'ID da vaga')).strip()
            d=by_id.get(id) or by_title.get(_norm(title)) or {}
            # A aba de detalhes do XLSX original contém títulos ligeiramente mais longos
            # (ex.: AIESEC). Um cruzamento aproximado conservador evita perder os dados.
            if not d and len(_norm(title).split())>=4:
                query=set(_norm(title).split())
                matches=[(len(query & set(key.split()))/len(query | set(key.split())),val)
                         for key,val in by_title.items() if key]
                if matches:
                    best=max(matches,key=lambda x:x[0])
                    if best[0]>=0.78:d=best[1]
            url=str(_get(item,'URL da vaga','Link','URL','Link da vaga') or _get(d,'URL da vaga')).strip()
            if url and not (url.startswith('https://') or url.startswith('http://')):
                # Reject malformed optional URLs without losing the entire row.
                errors.append(f'Linha {rno}: URL ignorada (formato inválido)');url=''
            status_raw=_get(item,'Status','Etapa')
            status=_status(status_raw)
            desc='\n\n'.join(str(_get(d,h)).strip() for h in ['Atividades','Requisitos','Benefícios','Restrições e remuneração','Anotações detalhadas'] if _get(d,h))
            followup=_datetime(_get(item,'Próximo acompanhamento','Follow-up'))
            published=_datetime(_get(item,'Publicado em','Data da publicação'))
            applied=_datetime(_get(item,'Data da inscrição','Data de inscrição'))
            x={'title':title,'company':company,'url':url,'mode':_mode(_get(item,'Modalidade')),
               'location':str(_get(item,'Localização','Local','Cidade')),
               'level':str(_get(item,'Senioridade','Nível')),
               'salary':str(_get(item,'Salário','Salário informado')),
               'status':status,'explicit_nova':bool(str(status_raw).strip()) and status=='Nova','followup':followup,'published':published,
               'notes':str(_get(item,'Anotações','Observações','Notas')),
               'contract_type':str(_get(item,'Tipo de contrato','Contrato')),
               'recruiter':str(_get(item,'Contato / recrutador','Recrutador','Contato')),
               'eligible':{'sim':'yes','nao':'no','yes':'yes','no':'no'}.get(_norm(_get(item,'Elegibilidade Brasil')),'unknown'),
               'saved':_bool(_get(item,'Salva'),True),
               'ignored':_bool(_get(item,'Ignorada'),False),
               'source_original':str(_get(item,'Fonte','Source')),
               'description':desc,
               'id_original':id,
               'score_original':str(_get(item,'Aderência (0-100)','Aderência')),
               'applied_at':applied,
               'xlsx_details':json.dumps(d,ensure_ascii=False)[:20000] if d else ''}
            items.append(x)
        return items,errors

def import_xlsx(data:bytes,cfg):
    items,warnings=parse_xlsx(data)
    return import_items(items, warnings, cfg, 'Importação XLSX')

def import_items(items, warnings, cfg, origin='Importação XLSX'):
    """Shared deduplication and non-destructive merge for XLSX and CSV."""
    if not items:return {'inserted':0,'updated':0,'skipped':0,'warnings':warnings,'count':0}
    inserted=updated=skipped=0
    skipped_nova=0
    for item in items:
        if item.get('explicit_nova') and not item.get('id_original'):
            skipped+=1;skipped_nova+=1
            continue
        try:
            j_id=add_manual_job(item,cfg,origin=origin)
            inserted+=1
        except DuplicateJobError as e:
            j_id=e.existing_id
            changes={k:item[k] for k in ('contract_type','recruiter') if item[k]}
            # Nunca retroceder o andamento de uma candidatura ao reimportar planilhas antigas.
            # Mudanças regressivas intencionais devem ser feitas em Gerenciar candidatura.
            stage_rank={'Nova':0,'Salva':1,'Candidatada':2,'Triagem':3,'Entrevista':4,'Teste técnico':5,'Proposta':6,'Rejeitada':7,'Aprovada':8}
            with conn() as c:
                found=c.execute('SELECT status FROM jobs WHERE id=?',(j_id,)).fetchone()
            current=found['status'] if found else 'Nova'
            incoming=item['status']
            if incoming!='Nova' and stage_rank.get(incoming,0)>stage_rank.get(current,0):
                changes['status']=incoming
            if item['followup']:changes['followup']=item['followup']
            # Não destruir anotações e decisões feitas no painel ao reimportar um XLSX antigo.
            if item['notes']:
                with conn() as c:
                    existing=c.execute('SELECT notes FROM jobs WHERE id=?',(j_id,)).fetchone()
                if existing and not existing['notes']:changes['notes']=item['notes']
            if changes:update_job(j_id,origin=origin,**changes)
            updated+=1
        except ValueError as e:
            warnings.append(f'{item["company"]} — {item["title"]}: {e}')
            skipped+=1;continue
        if item['ignored']:set_job_ignored(j_id,True)
        with conn() as c:
            if j_id.startswith('manual-'):
                # Imported items are editable just like manual ones.
                c.execute("UPDATE jobs SET source=? WHERE id=? AND source='Manual'",(origin,j_id))
            if item['xlsx_details']:
                c.execute('UPDATE jobs SET xlsx_details=? WHERE id=?',(item['xlsx_details'],j_id))
            if item['applied_at']:
                c.execute('UPDATE jobs SET applied_at=? WHERE id=? AND (applied_at=\'\' OR applied_at IS NULL)',(item['applied_at'],j_id))
    return {'inserted':inserted,'updated':updated,'skipped':skipped,'warnings':warnings[:30],'count':len(items),'skipped_nova':skipped_nova}

def _inline(ref,value):
    if value is None or value=='':return None
    c=ET.Element(Q('c'),{'r':ref})
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        c.set('t','n');ET.SubElement(c,Q('v')).text=str(value)
    else:
        c.set('t','inlineStr');t=ET.SubElement(ET.SubElement(c,Q('is')),Q('t'));t.text=str(value)
        if str(value).startswith(' ') or str(value).endswith(' '):t.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
    return c

def _rowdata(sheetroot,table,headerrow=7):
    data=sheetroot.find(Q('sheetData'))
    if data is None:data=ET.SubElement(sheetroot,Q('sheetData'))
    # Keep presentation and header rows 1-7; replace all data rows.
    for row in list(data):
        if int(row.attrib.get('r','0'))>headerrow:data.remove(row)
    for ix,values in enumerate(table,headerrow+1):
        el=ET.SubElement(data,Q('row'),{'r':str(ix),'ht':'32','customHeight':'1'})
        for j,v in enumerate(values):
            cell=_inline(_letters(j)+str(ix),v)
            if cell is not None:el.append(cell)
    # Widen the print area reference only if used.
    dimension=sheetroot.find(Q('dimension'))
    if dimension is not None:dimension.set('ref',f'A1:{_letters(max((len(x) for x in table),default=8)-1)}{max(7,7+len(table))}')

def _update_summary(root,alljobs):
    sheet=root.find(Q('sheetData'))
    for row in sheet.findall(Q('row')):
        if row.attrib.get('r')=='5':
            for c in list(row):
                if c.attrib.get('r') in ('B5','D5','F5'):row.remove(c)
            nums={'B5':len(alljobs),'D5':sum(1 for j in alljobs if j['status'] in ('Candidatada','Triagem','Entrevista','Teste técnico','Proposta','Aprovada','Rejeitada')),'F5':sum(1 for j in alljobs if j['status'] in ('Entrevista','Teste técnico'))}
            for k,v in nums.items():row.append(_inline(k,v))
            break

def export_xlsx(jobs=None):
    alljobs=list(jobs if jobs is not None else rows(limit=100000))
    if not TEMPLATE.exists():raise ValueError('Template XLSX não instalado')
    main=[];details=[]
    for j in alljobs:
        status={'Candidatada':'Candidatura enviada','Rejeitada':'Reprovada'}.get(j['status'],j['status'])
        applied=j.get('applied_at','')[:10]
        age=(date.today()-date.fromisoformat(applied)).days if re.fullmatch(r'\d{4}-\d{2}-\d{2}',applied) else ''
        skills=j.get('skills',[])
        if isinstance(skills,str):
            try:skills=json.loads(skills)
            except ValueError:skills=[]
        main.append([
            j.get('title',''),j.get('company',''),status,applied,j.get('mode',''),j.get('contract_type',''),j.get('recruiter',''),age,j.get('id',''),j.get('url',''),j.get('source',''),j.get('location',''),j.get('level',''),j.get('salary',''),j.get('score',''),j.get('published','')[:10],j.get('followup',''),j.get('notes',''),'Sim' if j.get('ignored') else 'Não','Sim' if j.get('saved') else 'Não',{'yes':'Sim','no':'Não'}.get(j.get('eligible'),'A confirmar'),', '.join(skills),j.get('first_seen','')[:10],j.get('last_seen','')[:10]
        ])
        if j.get('description') or j.get('xlsx_details'):
            original={}
            if j.get('xlsx_details'):
                try: original=json.loads(j['xlsx_details'])
                except (ValueError,TypeError):
                    try: original=ast.literal_eval(j['xlsx_details'])
                    except (ValueError,SyntaxError): original={}
                if not isinstance(original,dict):original={}
            # Recupere todas as colunas estruturadas de Detalhes quando disponíveis.
            fields=[original.get(_norm(k),'') for k in DETAIL_HEADERS]
            fields[0]=fields[0] or j.get('id','')
            fields[1]=fields[1] or j.get('title','')
            fields[2]=fields[2] or j.get('description','')
            fields[12]=fields[12] or j.get('url','')
            fields[13]=fields[13] or j.get('source','')
            fields[14]=j.get('id','')
            if j.get('notes'):fields[15]=j['notes']
            details.append(fields)
    with zipfile.ZipFile(TEMPLATE) as zin:
        sheets=_sheets(zin);needed={sheets.get('Candidaturas'):'Candidaturas',sheets.get('Detalhes das vagas'):'Detalhes das vagas'}
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                if info.filename in needed and needed[info.filename]:
                    root=ET.fromstring(zin.read(info.filename))
                    if needed[info.filename]=='Candidaturas':
                        _rowdata(root,main);_update_summary(root,alljobs)
                    else:_rowdata(root,details)
                    payload=ET.tostring(root,encoding='utf-8',xml_declaration=True)
                else:payload=zin.read(info.filename)
                zout.writestr(info,payload)
    return stream.getvalue()
