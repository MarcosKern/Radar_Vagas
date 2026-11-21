from pathlib import Path
import unittest
from bs4 import BeautifulSoup

class SettingsHeadingTests(unittest.TestCase):
    def test_settings_sections_use_uniform_unnumbered_heading(self):
        root=Path(__file__).resolve().parents[1]
        html=BeautifulSoup((root/'web/index.html').read_text(encoding='utf-8'),'html.parser')
        expected={
            'rules':'Regras da pesquisa',
            'exclusions':'Exclusões automáticas',
            'sources':'Fontes de vagas',
            'terms':'Termos de pesquisa e empresas',
            'ai':'Busca com IA na nuvem',
            'resume':'Modelo de currículo por vaga',
            'appearance':'Aparência e navegação',
            'backup':'Importar e exportar configurações',
            'updates':'Atualizações',
        }
        for panel in html.select('[data-config-panel]'):
            name=panel['data-config-panel']
            self.assertIn(name,expected)
            header=panel.select_one('.settings-section-heading')
            self.assertIsNotNone(header,name)
            self.assertEqual(header.select_one('h3').get_text(strip=True),expected[name])
            self.assertTrue(header.select_one('.settings-section-copy p').get_text(strip=True),name)
            self.assertNotIn('config-section-kicker',str(header))
        self.assertEqual(len(html.select('[data-config-panel]')),9)
        self.assertEqual(len(html.select('.config-tab-index')),0)
        self.assertIn('V0.17',html.select_one('.footer').get_text())

    def test_style_and_legacy_actions_remain(self):
        root=Path(__file__).resolve().parents[1]
        html=(root/'web/index.html').read_text(encoding='utf-8')
        css=(root/'web/assets/custom.css').read_text(encoding='utf-8')
        js=(root/'web/assets/app.js').read_text(encoding='utf-8')
        for token in ['id="resetExclusions"','id="resumeDownloadPt"','id="resumeDownloadEn"','id="saveSettingsBtn"','id="resumeSaveSettings"']:
            self.assertIn(token,html)
        self.assertIn('#page-config .settings-section-heading .settings-section-copy h3',css)
        self.assertNotIn('${index+1}. ${escapeHTML(PAGE_DEFAULTS',js)

if __name__=="__main__":unittest.main()
