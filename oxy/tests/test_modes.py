import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

from proxy_finder import Settings
from proxy_finder.client import build_proxies


class ModeTests(unittest.TestCase):
    def load(self, extra):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text('PROXY_USERNAME=customer-test\n'
                            'PROXY_PASSWORD=fake-password\n' + extra)
            with patch.dict(os.environ, {}, clear=True):
                return Settings.from_env(path)

    def username(self, settings):
        proxy = build_proxies(settings, 't01q1')['http']
        return unquote(urlsplit(proxy).username)

    def test_asn_from_env_ignores_location(self):
        settings = self.load('PROXY_MODE=asn\nASN=9121\n'
                             'COUNTRY=\nCITY=ignored-value\n')
        self.assertEqual(self.username(settings),
                         'customer-test-sessid-t01q1-sesstime-30-asn-9121')

    def test_country_only_ignores_asn(self):
        settings = self.load('PROXY_MODE=location\nCOUNTRY=tr\n'
                             'CITY=\nASN=not-used\n')
        self.assertEqual(self.username(settings),
                         'customer-test-sessid-t01q1-sesstime-30-cc-tr')

    def test_country_city(self):
        settings = self.load('PROXY_MODE=LOCATION\nCOUNTRY=TR\n'
                             'CITY=Sakarya\n')
        username = self.username(settings)
        self.assertTrue(username.endswith('-cc-tr-city-sakarya'))
        self.assertNotIn('-asn-', username)

    def test_legacy_default(self):
        self.assertTrue(self.username(self.load('')).endswith('-cc-tr'))

    def test_invalid_active_settings(self):
        for extra in ('PROXY_MODE=wrong', 'PROXY_MODE=asn\nASN=abc',
                      'PROXY_MODE=asn\nASN=0',
                      'PROXY_MODE=location\nCOUNTRY=',
                      'PROXY_MODE=location\nCITY=sakarya-asn-1'):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.load(extra)


if __name__ == '__main__':
    unittest.main()
