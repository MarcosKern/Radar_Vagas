"""LinkedIn integration stays user-driven and does not automate the platform."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class LinkedInSafeIntegrationTests(unittest.TestCase):
    def test_generates_public_search_links_without_api_credentials(self):
        js = (ROOT / 'web' / 'assets' / 'app.js').read_text(encoding='utf-8')
        self.assertIn("https://www.linkedin.com/jobs/search/", js)
        self.assertIn("url.searchParams.set('keywords',term)", js)
        self.assertIn("url.searchParams.set('f_WT','2')", js)
        self.assertNotIn('api.linkedin.com', js)
        self.assertNotIn('access_token', js.casefold())
        self.assertNotIn('client_secret', js.casefold())

    def test_links_open_safely_and_import_is_explicit(self):
        html = (ROOT / 'web' / 'index.html').read_text(encoding='utf-8')
        js = (ROOT / 'web' / 'assets' / 'app.js').read_text(encoding='utf-8')
        self.assertIn('id="linkedinImportForm"', html)
        self.assertIn('id="linkedinJobUrl"', html)
        self.assertIn('target="_blank" rel="noopener noreferrer"', js)
        self.assertIn("host==='linkedin.com'||host.endsWith('.linkedin.com')", js)
        self.assertIn("openManual(null,{url:url.toString()})", js)


if __name__ == '__main__':
    unittest.main()
