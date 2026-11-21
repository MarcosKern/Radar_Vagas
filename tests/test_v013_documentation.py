import unittest
from pathlib import Path
import re

BASE=Path(__file__).resolve().parents[1]

class TestDocumentation(unittest.TestCase):
    def test_single_readme(self):
        self.assertTrue((BASE / 'README.md').is_file())
        self.assertEqual([], list(BASE.glob('CHANGELOG*.md')))

    def test_versions_in_chronological_order(self):
        content=(BASE / 'README.md').read_text(encoding='utf-8')
        headings=re.findall(r'^### (V0\.\d+(?:\.\d+)?)\b',content,re.M)
        self.assertEqual(["V0.1","V0.3","V0.4","V0.5","V0.6","V0.7","V0.8","V0.8.1","V0.8.2","V0.9","V0.9.1","V0.9.2","V0.10","V0.11","V0.12","V0.13","V0.14","V0.15","V0.16","V0.17","V0.18"],headings)

    def test_no_stale_changelog_file_references(self):
        text=(BASE / 'README.md').read_text(encoding='utf-8')
        self.assertNotIn('Veja `CHANGELOG_',text)

    def test_display_version(self):
        self.assertIn('V0.18 · DADOS LOCAIS',(BASE / 'web' / 'index.html').read_text(encoding='utf-8'))

if __name__=='__main__': unittest.main()
