"""Importação e exportação CSV do mesmo cadastro da planilha XLSX.
Usa CSV UTF-8 com BOM, delimitador ; e cabeçalhos do XLSX. Somente stdlib.
"""
from __future__ import annotations
import csv
import io
import json
from .db import rows
from .xlsxio import HEADERS, _norm, _get, _status, _mode, _datetime, _bool, import_items

MAX_CSV_BYTES = 12_000_000


def _safe_csv_cell(value):
    """Mitiga CSV/Excel formula injection em valores controlados por fontes externas."""
    value = '' if value is None else str(value)
    if value.lstrip(' \t\r\n').startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
        return "'" + value
    return value


def _read_csv_cell(value):
    if isinstance(value, str) and value.startswith("'") and value[1:].lstrip(' \t\r\n').startswith(('=', '+', '-', '@')):
        return value[1:]
    return value or ''


def export_csv(jobs=None):
    output = io.StringIO(newline='')
    writer = csv.writer(output, delimiter=';', lineterminator='\r\n')
    writer.writerow(HEADERS)
    for job in list(rows(limit=100000) if jobs is None else jobs):
        skills=job.get('skills') or []
        if isinstance(skills, str):
            try:skills=json.loads(skills)
            except (ValueError,TypeError):skills=[]
        vals=[job.get('title',''),job.get('company',''),job.get('status',''),
              str(job.get('applied_at') or '')[:10],job.get('mode',''),job.get('contract_type',''),
              job.get('recruiter',''),'',job.get('id',''),job.get('url',''),job.get('source',''),
              job.get('location',''),job.get('level',''),job.get('salary',''),job.get('score',''),
              str(job.get('published') or '')[:10],job.get('followup',''),job.get('notes',''),
              'Sim' if job.get('ignored') else 'Não','Sim' if job.get('saved') else 'Não',
              {'yes':'Sim','no':'Não'}.get(job.get('eligible'),'A confirmar'),', '.join(skills),
              str(job.get('first_seen') or '')[:10],str(job.get('last_seen') or '')[:10]]
        writer.writerow([_safe_csv_cell(v) for v in vals])
    return ('\ufeff' + output.getvalue()).encode('utf-8')


def parse_csv(data:bytes):
    if not isinstance(data,bytes) or not data:raise ValueError('Arquivo CSV vazio.')
    if len(data)>MAX_CSV_BYTES:raise ValueError('Arquivo CSV excede 12 MB.')
    try:text=data.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:text=data.decode('cp1252')
        except UnicodeDecodeError as exc:raise ValueError('CSV deve usar UTF-8 ou Windows-1252.') from exc
    if '\x00' in text:raise ValueError('Arquivo CSV inválido (contém caracteres binários).')
    sample=text[:6000]
    try: dialect=csv.Sniffer().sniff(sample,delimiters=';,\t')
    except csv.Error:
        dialect=csv.excel
        dialect.delimiter=';' if sample.splitlines()[0].count(';')>=sample.splitlines()[0].count(',') else ','
    try:reader=csv.DictReader(io.StringIO(text,newline=''),dialect=dialect)
    except (csv.Error,ValueError) as exc:raise ValueError('Cabeçalho CSV inválido.') from exc
    if not reader.fieldnames:raise ValueError('Cabeçalho do CSV não encontrado.')
    fieldnames=[_norm(h) for h in reader.fieldnames if h]
    if not any(h in fieldnames for h in (_norm('Vaga'),_norm('Título'),_norm('Cargo'),_norm('Job title'))):raise ValueError('CSV sem coluna Vaga ou Cargo.')
    if not any(h in fieldnames for h in (_norm('Empresa contratante'),_norm('Empresa'),_norm('Company'))):raise ValueError('CSV sem coluna Empresa.')
    items=[];warnings=[]
    try:
        for rownum,row in enumerate(reader,2):
            if rownum>50002:raise ValueError('O limite de importação é 50.000 vagas por CSV.')
            if None in row:
                warnings.append(f'Linha {rownum}: colunas excedentes ignoradas.')
                row.pop(None,None)
            rec={_norm(k):_read_csv_cell(v) for k,v in row.items() if k}
            title=str(_get(rec,'Vaga','Cargo','Título','Título da vaga','Job title')).strip()
            company=str(_get(rec,'Empresa contratante','Empresa','Company','Company name')).strip()
            if not title and not company:continue
            if not title or not company:
                warnings.append(f'Linha {rownum}: cargo ou empresa ausente.');continue
            url=str(_get(rec,'URL da vaga','Link','URL','Link da vaga')).strip()
            if url and not url.startswith(('https://','http://')):
                warnings.append(f'Linha {rownum}: URL ignorada (formato inválido).');url=''
            mode=_mode(_get(rec,'Modalidade','Mode'))
            eligibility=_norm(_get(rec,'Elegibilidade Brasil'))
            item={
                'title':title,'company':company,'url':url,'mode':mode,
                'location':str(_get(rec,'Localização','Local','Cidade')),
                'level':str(_get(rec,'Senioridade','Nível')),
                'salary':str(_get(rec,'Salário','Salário informado')),
                'status':_status(_get(rec,'Status','Etapa')),
                'explicit_nova': bool(str(_get(rec,'Status','Etapa')).strip()) and _status(_get(rec,'Status','Etapa'))=='Nova',
                'followup':_datetime(_get(rec,'Próximo acompanhamento','Follow-up','Próximo contato')),
                'published':_datetime(_get(rec,'Publicado em','Publicada em','Data da publicação')),
                'notes':str(_get(rec,'Anotações','Observações','Notas')),
                'contract_type':str(_get(rec,'Tipo de contrato','Contrato')),
                'recruiter':str(_get(rec,'Contato / recrutador','Recrutador','Contato')),
                'eligible':{'sim':'yes','nao':'no','yes':'yes','no':'no'}.get(eligibility,'unknown'),
                'saved':_bool(_get(rec,'Salva'),True),
                'ignored':_bool(_get(rec,'Ignorada'),False),
                'source_original':str(_get(rec,'Fonte','Source')),
                'description':str(_get(rec,'Descrição','Description','Atividades')),
                'id_original':str(_get(rec,'ID da vaga')),
                'score_original':str(_get(rec,'Aderência (0-100)','Pontuação')),
                'applied_at':_datetime(_get(rec,'Data da inscrição','Data de inscrição')),
                'xlsx_details':'',
            }
            items.append(item)
    except csv.Error as exc:raise ValueError(f'CSV malformado: {exc}') from exc
    return items,warnings


def import_csv(data:bytes,cfg):
    items,warnings=parse_csv(data)
    return import_items(items,warnings,cfg,origin='Importação CSV')
