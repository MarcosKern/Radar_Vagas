"""Offline contract tests against representative documented response formats."""
from test_support import configured as test_config
import json
import unittest
from datetime import datetime,timezone
from xml.etree import ElementTree
from radar.helpers import iso_utc
from radar.sources import (parse_remoteok,parse_wwr,parse_greenhouse,parse_lever,
                           parse_ashby,parse_smartrecruiters,remote_eligibility,board_spec,
                           collect)
from radar.scoring import evaluate
from radar.db import job_identity
from monitor import config,save_config

NOW=datetime.now(timezone.utc).isoformat()
C=test_config()

class NewParsers(unittest.TestCase):
    def test_remoteok(self):
        d=[{'legal':'terms'}, {'id':123,'position':'Junior IT Support Analyst','company':'Example','location':'Brazil','date':NOW,'url':'https://remoteok.com/jobs/123','tags':['Linux','Azure']}]
        x=parse_remoteok(d)[0]
        self.assertEqual(x['eligible'],'yes')
        self.assertIn('Linux',x['description'])
        self.assertEqual(len(parse_remoteok(d)),1)
        self.assertIsNotNone(evaluate(x,C))

    def test_wwr_rss_rfc822(self):
        xml='''<rss><channel><item><title>Example: Junior DevOps Engineer</title><link>https://weworkremotely.com/jobs/test</link><pubDate>Thu, 19 Nov 2026 21:00:00 GMT</pubDate><description><![CDATA[Location: Anywhere. Terraform Docker.]]></description></item></channel></rss>'''
        x=parse_wwr(ElementTree.fromstring(xml))[0]
        self.assertEqual(x['source'],'We Work Remotely')
        self.assertEqual(x['eligible'],'yes')
        self.assertIn('2026-11-19',x['published'])
        self.assertIsNotNone(evaluate(x,C))

    def test_greenhouse_keeps_updated_separate(self):
        data={'jobs':[{'id':99,'title':'Junior IT Support Analyst','updated_at':NOW,'location':{'name':'Brazil - Remote'},'absolute_url':'https://job-boards.greenhouse.io/example/jobs/99','content':'Linux Azure'}]}
        x=parse_greenhouse(data,'Example')[0]
        self.assertEqual(x['mode'],'Remoto')
        self.assertEqual(x['eligible'],'yes')
        self.assertEqual(x['published'],'')
        self.assertEqual(x['extra']['last_updated'],NOW)

    def test_lever(self):
        d=[{'id':'uuid','text':'Junior DevOps Engineer','workplaceType':'remote','categories':{'location':'Remote / Brazil','commitment':'Full-time'},'hostedUrl':'https://jobs.lever.co/example/uuid','descriptionPlain':'Terraform Linux'}]
        x=parse_lever(d,'Example')[0]
        self.assertEqual(x['eligible'],'yes')
        self.assertEqual(x['mode'],'Remoto')
        self.assertEqual(x['published'],'')

    def test_ashby_hybrid_not_remote(self):
        d={'jobs':[{'title':'IT Support Analyst Junior','location':'Porto Alegre','workplaceType':'Hybrid','publishedAt':NOW,'jobUrl':'https://jobs.ashbyhq.com/test/x','descriptionPlain':'Linux','isListed':True},
                   {'title':'Hidden role','isListed':False,'jobUrl':'https://jobs.ashbyhq.com/test/hidden'}]}
        x=parse_ashby(d,'Example')
        self.assertEqual(len(x),1)
        self.assertEqual(x[0]['mode'],'Híbrido')
        self.assertIsNotNone(evaluate(x[0],C))

    def test_smartrecruiters(self):
        data={'content':[{'id':'999','name':'Junior Infrastructure Analyst','releasedDate':NOW,'location':{'city':'Porto Alegre','region':'RS','country':'br','hybrid':True},'company':{'name':'Example'},'experienceLevel':{'label':'Entry'}}]}
        x=parse_smartrecruiters(data,'Example','example')[0]
        self.assertEqual(x['mode'],'Híbrido')
        self.assertIn('Porto Alegre',x['location'])
        self.assertTrue(x['url'].startswith('https://jobs.smartrecruiters.com/'))
        self.assertIsNotNone(evaluate(x,C))

    def test_remote_restrictions(self):
        self.assertEqual(remote_eligibility('Remote - United States only'),'no')
        self.assertEqual(remote_eligibility('Remote - Brazil, United States'),'yes')
        self.assertEqual(remote_eligibility('Worldwide except Brazil'),'no')
        self.assertEqual(remote_eligibility('Remote'),'unknown')
        self.assertEqual(remote_eligibility('LATAM'),'yes')

    def test_board_spec_rejects_urls(self):
        self.assertEqual(board_spec('jumpcloud | JumpCloud'),('jumpcloud','JumpCloud'))
        self.assertIsNone(board_spec('https://example.com/x'))
        self.assertIsNone(board_spec('../../secret'))

    def test_dedup_preserves_distinct_geographies(self):
        a={'title':'IT Support Analyst','company':'Example','location':'Porto Alegre'}
        b={'title':'IT Support Analyst','company':'Example','location':'Sao Paulo'}
        self.assertNotEqual(job_identity(a),job_identity(b))
        self.assertEqual(job_identity(a),job_identity({'title':'IT SUPPORT ANALYST','company':'Example','location':'Porto Alegre'}))

    def test_local_only_collects_ats(self):
        cfg=dict(C)
        cfg['include_remote']=False
        cfg['sources']={s:False for s in C['sources']}
        cfg['sources']['greenhouse']=True
        cfg['greenhouse_boards']=[]
        res=list(collect(cfg))
        self.assertEqual(res[0][0],'Greenhouse')
        self.assertIn('Nenhuma empresa',res[0][2])

if __name__=='__main__':unittest.main()
