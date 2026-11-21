"""Smoke tests for v4 dashboard static assets and event-driven controls."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1];WEB=ROOT/'web'
class UITests(unittest.TestCase):
 def test_offline_stylesheets_exist_and_are_linked(self):
  html=(WEB/'index.html').read_text('utf8')
  for asset in ('bootstrap.min.css','bootstrap.bundle.min.js','tailwind.css','custom.css','app.js'):
   self.assertTrue((WEB/'assets'/asset).is_file());self.assertIn('/assets/'+asset,html)
  self.assertNotIn('cdn.tailwindcss.com',html);self.assertNotIn('cdn.jsdelivr.net',html)
 def test_v4_controls_present(self):
  html=(WEB/'index.html').read_text('utf8');js=(WEB/'assets'/'app.js').read_text('utf8')
  for id_ in ('page-dashboard','page-vagas','page-candidaturas','page-relatorios','page-config','manualDialog','manageDialog','importDialog','manualForm','manualBtn','scanBtn','exportXlsxBtn','modeFilter','statusFilter','viewFilter','sourceFilter','resetFilters','menuBtn','scrim','xlsxFile','manageNotes','cfgQueryCombos','aiSearchBtn','sourceGroups','tagGroups','linkedinSearchBtn','linkedinDialog','linkedinSearchList','linkedinJobUrl'):
   with self.subTest(id_=id_):self.assertIn('id="'+id_+'"',html)
  for fn in ('openManage','openManual','submitManual','saveManage','importWorkbook','saveSettings','renderTagGroups','linkedInSearchUrl','openLinkedInSearches','submitLinkedInUrl'):
   self.assertIn('function '+fn,js)
  self.assertNotIn('onclick=',html)
 def test_custom_css_accessibility_and_squares(self):
  css=(WEB/'assets'/'custom.css').read_text('utf8')
  for piece in (':focus-visible','prefers-reduced-motion','.sidebar.open','--primary:','border-radius:3px','.modal-box'):
   self.assertIn(piece,css)
