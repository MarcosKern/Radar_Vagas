"""Persistência local em SQLite; registros preservados entre varreduras."""
import json
import sqlite3
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from .helpers import norm, canonical_job_url

ROOT=Path(__file__).resolve().parents[1]
DB_PATH=ROOT/'data'/'jobs.sqlite'
SCHEMA='''
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, source TEXT NOT NULL, external_id TEXT, fingerprint TEXT,
 title TEXT NOT NULL, company TEXT NOT NULL, location TEXT, mode TEXT,
 level TEXT, published TEXT, url TEXT NOT NULL, description TEXT, salary TEXT,
 eligible TEXT, score INTEGER NOT NULL, reasons TEXT NOT NULL, skills TEXT NOT NULL,
 first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'Nova', notes TEXT NOT NULL DEFAULT '',
 followup TEXT NOT NULL DEFAULT '', applied_at TEXT NOT NULL DEFAULT '',
 saved INTEGER NOT NULL DEFAULT 0, last_alerted TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_date ON jobs(published);
CREATE TABLE IF NOT EXISTS job_status_history (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 job_id TEXT NOT NULL,
 occurred_at TEXT NOT NULL,
 previous_status TEXT,
 new_status TEXT NOT NULL,
 event_type TEXT NOT NULL,
 source TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_job_status_history_by_job ON job_status_history(job_id,id DESC);
CREATE TABLE IF NOT EXISTS job_exclusions (
 owner_id TEXT NOT NULL, kind TEXT NOT NULL, value TEXT NOT NULL,
 created_at TEXT NOT NULL, PRIMARY KEY(owner_id,kind,value)
);
CREATE INDEX IF NOT EXISTS idx_exclusions_lookup ON job_exclusions(kind,value);
CREATE TABLE IF NOT EXISTS ai_runs (
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_at TEXT NOT NULL, model TEXT NOT NULL,
 queries TEXT NOT NULL, fetched INTEGER NOT NULL, inserted INTEGER NOT NULL,
 tokens INTEGER NOT NULL DEFAULT 0, errors TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_at TEXT NOT NULL, fetched INTEGER NOT NULL,
 inserted INTEGER NOT NULL, eligible INTEGER NOT NULL, sources TEXT NOT NULL, errors TEXT NOT NULL,
 excluded INTEGER NOT NULL DEFAULT 0, already_known INTEGER NOT NULL DEFAULT 0
);
'''
STATUSES={'Nova','Salva','Candidatada','Triagem','Entrevista','Teste técnico','Proposta','Aprovada','Rejeitada','Descartada'}


class RadarConnection(sqlite3.Connection):
    # A context manager should also close the handle; SQLite's default only commits.
    def __exit__(self,exc_type,exc,tb):
        try:return super().__exit__(exc_type,exc,tb)
        finally:self.close()


def conn():
    DB_PATH.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DB_PATH,timeout=20,factory=RadarConnection)
    c.row_factory=sqlite3.Row
    c.executescript(SCHEMA)
    columns={row['name'] for row in c.execute('PRAGMA table_info(jobs)')}
    # Migrate existing installations transparently without clearing the database.
    if 'ignored' not in columns:
        try:c.execute('ALTER TABLE jobs ADD COLUMN ignored INTEGER NOT NULL DEFAULT 0')
        except sqlite3.OperationalError as ex:
            if 'duplicate column name' not in str(ex).lower():raise
    if 'ignored_at' not in columns:
        try:c.execute("ALTER TABLE jobs ADD COLUMN ignored_at TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError as ex:
            if 'duplicate column name' not in str(ex).lower():raise
    for name in ('contract_type','recruiter','xlsx_details'):
        if name not in columns:
            try:c.execute(f"ALTER TABLE jobs ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
            except sqlite3.OperationalError as ex:
                if 'duplicate column name' not in str(ex).lower():raise
    c.execute('''CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS ai_usage (day TEXT PRIMARY KEY, calls INTEGER NOT NULL DEFAULT 0, tokens INTEGER NOT NULL DEFAULT 0)''')
    run_columns={row['name'] for row in c.execute('PRAGMA table_info(runs)')}
    for name in ('excluded','already_known'):
        if name not in run_columns:
            try:c.execute(f'ALTER TABLE runs ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0')
            except sqlite3.OperationalError as ex:
                if 'duplicate column name' not in str(ex).lower():raise
    return c


def job_identity(job):
    # Cross-board dedup by normalized title+company, retaining a single candidate record.
    # Include geography so distinct locations with identical job titles are not collapsed.
    a=re.sub(r'[^a-z0-9]+','',norm(job['company']))
    b=re.sub(r'[^a-z0-9]+','',norm(job['title']))
    location=re.sub(r'[^a-z0-9]+','',norm(job.get('location','')))
    return hashlib.sha1((a+'|'+b+'|'+location).encode()).hexdigest()[:20]


def exclusion_keys(job):
    """Independent identifiers; no broad company-wide blocking."""
    job=dict(job)
    keys={('fingerprint', job_identity(job))}
    url=canonical_job_url(job.get('url',''))
    if url:keys.add(('url',url))
    src=norm(job.get('source',''))
    ext=str(job.get('external_id','')).strip()
    if src and ext:keys.add(('external_id',src+':'+ext))
    return keys


def _all_exclusions(c):
    return {(r['kind'],r['value']) for r in c.execute('SELECT kind,value FROM job_exclusions')}


def _sync_ignored(c):
    rules=_all_exclusions(c)
    now=datetime.now(timezone.utc).isoformat()
    for r in c.execute('SELECT id,source,external_id,title,company,location,url,ignored,ignored_at FROM jobs').fetchall():
        blocked=bool(exclusion_keys(r) & rules)
        if blocked != bool(r['ignored']):
            c.execute('UPDATE jobs SET ignored=?,ignored_at=? WHERE id=?',
                      (int(blocked),now if blocked else '',r['id']))


def set_job_ignored(j_id,ignored):
    """Persist blacklist rules and synchronize all matching saved records."""
    if type(ignored) is not bool:raise ValueError('Valor de exclusão inválido')
    with conn() as c:
        row=c.execute('SELECT * FROM jobs WHERE id=?',(j_id,)).fetchone()
        if row is None:return False
        c.execute('DELETE FROM job_exclusions WHERE owner_id=?',(j_id,))
        if ignored:
            now=datetime.now(timezone.utc).isoformat()
            for kind,value in exclusion_keys(row):
                c.execute('INSERT OR IGNORE INTO job_exclusions(owner_id,kind,value,created_at) VALUES(?,?,?,?)',
                          (j_id,kind,value,now))
        _sync_ignored(c)
    return True


def refresh_exclusion_for_manual(c,j_id):
    """Keep ignore rules aligned after a manually entered job is edited/deleted."""
    existing=c.execute('SELECT COUNT(*) AS n FROM job_exclusions WHERE owner_id=?',(j_id,)).fetchone()['n']
    if not existing:return
    c.execute('DELETE FROM job_exclusions WHERE owner_id=?',(j_id,))
    row=c.execute('SELECT * FROM jobs WHERE id=?',(j_id,)).fetchone()
    if row:
        now=datetime.now(timezone.utc).isoformat()
        for kind,value in exclusion_keys(row):
            c.execute('INSERT OR IGNORE INTO job_exclusions(owner_id,kind,value,created_at) VALUES(?,?,?,?)',
                      (j_id,kind,value,now))
    _sync_ignored(c)


def save_jobs(items,stats=None):
    """Deduplicate against the database and blacklist across all enabled sources."""
    now=datetime.now(timezone.utc).isoformat()
    inserted=0
    excluded=0
    already_known=0
    with conn() as c:
        rules=_all_exclusions(c)
        existing_rows=c.execute('SELECT id,source,fingerprint,url FROM jobs').fetchall()
        by_fp={r['fingerprint']:r for r in existing_rows if r['fingerprint']}
        by_url={canonical_job_url(r['url']):r for r in existing_rows if canonical_job_url(r['url'])}
        for job,score,reasons,skills in items:
            j_id=job_identity(job)
            canon=canonical_job_url(job.get('url',''))
            # Exclusions are checked BEFORE storing / alerting; do not alter history.
            if exclusion_keys(job) & rules:
                excluded+=1
                continue
            existing=by_fp.get(j_id) or (by_url.get(canon) if canon else None)
            if existing is not None:
                already_known+=1
                if existing['source'] in ('Manual','Importação XLSX'):continue
                actual_id=existing['id']
            else:
                actual_id=j_id
                inserted+=1
            c.execute("""INSERT INTO jobs (id,source,external_id,fingerprint,title,company,location,mode,level,published,url,description,salary,eligible,score,reasons,skills,first_seen,last_seen)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen,
                 score=excluded.score,reasons=excluded.reasons,skills=excluded.skills,
                 published=CASE WHEN excluded.published != '' THEN excluded.published ELSE jobs.published END,
                 description=CASE WHEN length(excluded.description)>length(jobs.description) THEN excluded.description ELSE jobs.description END,
                 eligible=CASE WHEN excluded.eligible='yes' THEN 'yes' ELSE jobs.eligible END""",
                (actual_id,job['source'],job['external_id'],j_id,job['title'],job['company'],job['location'],job['mode'],job['level'],job['published'],job['url'],job['description'],job['salary'],job['eligible'],score,json.dumps(reasons,ensure_ascii=False),json.dumps(skills,ensure_ascii=False),now,now))
            if existing is None:
                row={'id':actual_id,'source':job['source'],'fingerprint':j_id,'url':job['url']}
                by_fp[j_id]=row
                if canon:by_url[canon]=row
    if stats is not None:
        stats.update(excluded=excluded,already_known=already_known)
    return inserted


def save_run(fetched, inserted, eligible, sources, errors, excluded=0, already_known=0):
    with conn() as c:
        c.execute('INSERT INTO runs (run_at,fetched,inserted,eligible,sources,errors,excluded,already_known) VALUES(?,?,?,?,?,?,?,?)',(datetime.now(timezone.utc).isoformat(),fetched,inserted,eligible,json.dumps(sources,ensure_ascii=False),json.dumps(errors,ensure_ascii=False),excluded,already_known))


def rows(limit=2000):
    with conn() as c:
        raw=c.execute('SELECT * FROM jobs ORDER BY score DESC, first_seen DESC LIMIT ?',(limit,)).fetchall()
    out=[]
    for r in raw:
        j=dict(r);j['reasons']=json.loads(j['reasons']);j['skills']=json.loads(j['skills']);out.append(j)
    return out


def save_ai_run(model,queries,fetched,inserted,tokens,errors):
    with conn() as c:
        c.execute('INSERT INTO ai_runs (run_at,model,queries,fetched,inserted,tokens,errors) VALUES(?,?,?,?,?,?,?)',
                  (datetime.now(timezone.utc).isoformat(),model,json.dumps(queries,ensure_ascii=False),fetched,inserted,tokens,json.dumps(errors,ensure_ascii=False)))


def ai_runs(limit=12):
    with conn() as c:
        return [dict(r) for r in c.execute('SELECT * FROM ai_runs ORDER BY id DESC LIMIT ?',(limit,))]


def runs(limit=20):
    with conn() as c:
        return [dict(r) for r in c.execute('SELECT * FROM runs ORDER BY id DESC LIMIT ?',(limit,))]



APPLICATION_STATUSES={'Candidatada','Triagem','Entrevista','Teste técnico','Proposta','Aprovada','Rejeitada'}


def _log_status_change(c, job_id, previous_status, new_status, source='Painel', occurred_at=None):
    # Record only real transitions, atomically with the status update.
    previous_status=previous_status or None
    if previous_status == new_status:
        return
    if previous_status is None:
        if new_status not in APPLICATION_STATUSES:
            return
        event_type='application' if new_status=='Candidatada' else 'initial'
    else:
        event_type='application' if previous_status in ('Nova','Salva') and new_status=='Candidatada' else 'transition'
    c.execute('INSERT INTO job_status_history (job_id,occurred_at,previous_status,new_status,event_type,source) VALUES(?,?,?,?,?,?)',
              (job_id,occurred_at or datetime.now(timezone.utc).isoformat(),previous_status,new_status,event_type,source))


def job_history(job_id,limit=250):
    # Return only events belonging to the requested job, newest first.
    with conn() as c:
        if c.execute('SELECT 1 FROM jobs WHERE id=?',(job_id,)).fetchone() is None:
            return None
        limit=max(1,min(int(limit),500))
        return [dict(row) for row in c.execute('SELECT id,occurred_at,previous_status,new_status,event_type,source FROM job_status_history WHERE job_id=? ORDER BY id DESC LIMIT ?', (job_id,limit))]

def update_job(j_id,status=None,notes=None,followup=None,saved=None,contract_type=None,recruiter=None,origin='Painel'):
    updates=[];values=[]
    if status is not None:
        if status not in STATUSES:raise ValueError('Status inválido')
        updates.append('status=?');values.append(status)
        if status=='Candidatada':updates.append("applied_at=CASE WHEN applied_at='' THEN ? ELSE applied_at END");values.append(datetime.now(timezone.utc).isoformat())
    if notes is not None:updates.append('notes=?');values.append(str(notes)[:5000])
    if followup is not None:
        if followup and not re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(followup)):raise ValueError('Data inválida')
        updates.append('followup=?');values.append(followup)
    if saved is not None:updates.append('saved=?');values.append(int(bool(saved)))
    if contract_type is not None:updates.append('contract_type=?');values.append(str(contract_type)[:90])
    if recruiter is not None:updates.append('recruiter=?');values.append(str(recruiter)[:180])
    if not updates:return False
    with conn() as c:
        previous=c.execute('SELECT status FROM jobs WHERE id=?',(j_id,)).fetchone()
        if previous is None:return False
        res=c.execute('UPDATE jobs SET '+','.join(updates)+' WHERE id=?',(*values,j_id))
        if res.rowcount and status is not None:
            _log_status_change(c,j_id,previous['status'],status,origin)
        return res.rowcount>0


def pending_alerts(threshold=72,limit=12):
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM jobs WHERE ignored=0 AND score>=? AND last_alerted='' AND status='Nova' ORDER BY score DESC, published DESC LIMIT ?",(threshold,limit))]


def mark_alerted(ids):
    if not ids:return
    with conn() as c:
        c.executemany('UPDATE jobs SET last_alerted=? WHERE id=?',[(datetime.now(timezone.utc).isoformat(),i) for i in ids])
