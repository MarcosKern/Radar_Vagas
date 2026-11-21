"""Configurações de teste criadas em memória, não usadas pela instalação real."""
import monitor
def configured():
    cfg=monitor.config()
    cfg.update(role_terms=['analista','suporte','support','devops','infrastructure','infraestrutura','cloud','engineer','it support'],
               junior_terms=['junior','júnior','jr','jr.','entry','analyst i','analista i'],
               profile_skills=['Linux','SQL','Azure','Terraform','Docker','VPN','CI/CD'],
               local_cities=['Porto Alegre','São Leopoldo','Canoas'], min_score=45)
    cfg['sources']['gupy']=True
    cfg['ai_daily_cap']=2
    return cfg
