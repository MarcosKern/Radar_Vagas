"""Alertas opcionais. Só marca notificado quando um envio é confirmado."""
from __future__ import annotations
import json
import os
import urllib.request
import urllib.parse
from .db import mark_alerted,pending_alerts


def post_json(url,obj):
    req=urllib.request.Request(url,data=json.dumps(obj,ensure_ascii=False).encode(),headers={'Content-Type':'application/json','User-Agent':'RadarVagas/1.0'},method='POST')
    with urllib.request.urlopen(req,timeout=16) as r: return 200<=r.status<300


def notify(threshold=72):
    jobs=pending_alerts(threshold=threshold)
    if not jobs:return {'sent':0,'errors':[],'reason':'Sem novas vagas acima do limite'}
    telegram_token=os.getenv('TELEGRAM_BOT_TOKEN','').strip()
    telegram_id=os.getenv('TELEGRAM_CHAT_ID','').strip()
    discord_url=os.getenv('DISCORD_WEBHOOK_URL','').strip()
    if not (telegram_token and telegram_id) and not discord_url:
        return {'sent':0,'errors':[],'reason':'Notificações não configuradas'}
    lines=[f"📡 RadarVagas — {len(jobs)} oportunidades com alta aderência"]
    for j in jobs[:10]:
        lines.append(f"• {j['score']}/100 · {j['title']} — {j['company']} ({j['source']})\n{j['url']}")
    text='\n\n'.join(lines)[:3900]
    errors=[];success=False
    if telegram_token and telegram_id:
        try:
            success=bool(post_json(f'https://api.telegram.org/bot{telegram_token}/sendMessage',{'chat_id':telegram_id,'text':text,'disable_web_page_preview':True})) or success
        except Exception as e:errors.append('Telegram: '+str(e)[:100])
    if discord_url:
        try:
            success=bool(post_json(discord_url,{'content':text[:1900]})) or success
        except Exception as e:errors.append('Discord: '+str(e)[:100])
    if success:mark_alerted([j['id'] for j in jobs])
    return {'sent':len(jobs) if success else 0,'errors':errors,'reason':'Enviado' if success else 'Falha no envio'}
