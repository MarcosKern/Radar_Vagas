"""Conversões e normalizações sem dependências externas."""
from __future__ import annotations
import re
import json
import unicodedata
from datetime import datetime, timezone, timedelta
from html import unescape
from html.parser import HTMLParser
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse, urlsplit, urlunsplit, parse_qsl, urlencode


class _Extractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.drop = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'): self.drop += 1
        if tag in ('p', 'br', 'li', 'h1', 'h2', 'h3'): self.parts.append(' ')
    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.drop: self.drop -= 1
        if tag in ('p', 'li'): self.parts.append(' ')
    def handle_data(self, data):
        if not self.drop: self.parts.append(data)


def plain(s):
    s = str(s or '')
    # HTMLParser treats bare ampersands in company names such as C&A as entity prefixes.
    # Escape only ampersands which are not already completed HTML entities.
    s = re.sub(r'&(?!#[0-9]+;|#x[0-9a-fA-F]+;|[A-Za-z][A-Za-z0-9]+;)', '&amp;', s)
    p = _Extractor()
    try:
        p.feed(s)
        s = ' '.join(p.parts)
    except (ValueError, TypeError): pass
    return re.sub(r'\s+', ' ', unescape(s)).strip()


def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', plain(s).lower()) if not unicodedata.combining(c))


def iso_utc(v):
    if not v: return ''
    if isinstance(v, (float, int)):
        try: return datetime.fromtimestamp(v, timezone.utc).isoformat()
        except (ValueError, OSError, OverflowError): return ''
    try:
        return datetime.fromisoformat(str(v).replace('Z','+00:00')).astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        try:
            dt=parsedate_to_datetime(str(v))
            if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, IndexError):
            return ''


def age_days(v, now=None):
    v = iso_utc(v)
    if not v: return None
    now = now or datetime.now(timezone.utc)
    return max(0, (now - datetime.fromisoformat(v)).total_seconds()/86400)


def safe_url(u):
    try:
        p=urlparse(str(u or ''))
        if p.scheme not in ('https','http') or not p.netloc: return ''
        return str(u)[:1500]
    except ValueError: return ''


def list_str(v):
    if isinstance(v, (list,tuple)):
        return ', '.join(str(i.get('name',i.get('alpha2','')) if isinstance(i,dict) else i) for i in v)
    return str(v or '')


def canonical_job_url(value):
    """Canonical URL for matching the same posting across boards and tracking links.

    Keeps application identifiers (including meaningful query parameters) intact.
    """
    if not value:
        return ''
    try:
        p=urlsplit(str(value).strip())
        if p.scheme.lower() not in ('http','https') or not p.hostname:
            return ''
        hostname=p.hostname.lower().removeprefix('www.')
        if p.port and p.port not in (80,443):
            hostname += ':' + str(p.port)
        path=p.path.rstrip('/')
        # Tracking-only query parameters are not part of the vacancy identity.
        skip={'fbclid','gclid','igshid','ref','referrer','source','sourceid',
              'campaign','campaign_id','gh_src','lever-source','trk','trackingid'}
        query=sorted((k,v) for k,v in parse_qsl(p.query,keep_blank_values=True)
                     if k.lower() not in skip and not k.lower().startswith('utm_'))
        return urlunsplit(('https',hostname,path,urlencode(query),'')).removesuffix('/')
    except (ValueError,TypeError):
        return ''
