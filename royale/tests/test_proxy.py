import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

from proxy_finder import Settings, find_matching_ip
from proxy_finder.client import build_proxies


class ProxyTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings('test-user', 'fake-password')

    def test_password_parameters_and_socks_port(self):
        proxy = urlsplit(build_proxies(self.settings, 'm18mabcd')['https'])
        self.assertEqual(proxy.scheme, 'socks5')
        self.assertEqual(proxy.port, 32325)
        self.assertEqual(unquote(proxy.username), 'test-user')
        self.assertEqual(unquote(proxy.password),
                         'fake-password_country-az_city-baku'
                         '_session-m18mabcd_lifetime-30m')

    def test_optional_city(self):
        settings = replace(self.settings, city='')
        proxy = build_proxies(settings, 'm18mabcd')['http']
        self.assertNotIn('_city-', proxy)
        self.assertIn('_country-az_session-', proxy)

    def test_env(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text('PROXY_USERNAME=test\nPROXY_PASSWORD=fake\n'
                            'CITY=\nCOUNTRY=AZ\nPROXY_SCHEME=socks5h\n'
                            'SESSION_MINUTES=60\n')
            with patch.dict(os.environ, {}, clear=True):
                settings = Settings.from_env(path)
        self.assertEqual(settings.city, '')
        self.assertEqual(settings.country, 'az')
        self.assertEqual(settings.session_minutes, 60)
        self.assertTrue(build_proxies(settings, 'm18mabcd')['https']
                        .startswith('socks5h://'))

    def test_invalid_sessions_and_settings(self):
        for value in ('m18m1', '123456789', '1234567_'):
            with self.assertRaises(ValueError):
                build_proxies(self.settings, value)
        for changes in ({'session_prefix': 'abcde'},
                        {'session_minutes': 10081},
                        {'city': 'baku_session-bad'},
                        {'proxy_scheme': 'wrong'}):
            with self.assertRaises(ValueError):
                replace(self.settings, **changes)

    def test_generated_sessions_and_collision(self):
        seen = []
        # First two IDs collide; the third candidate must replace the second.
        chars = iter('aaaaaaaabbbbccccdddd')

        def fetch(settings, session_id, stop, deadline):
            seen.append(session_id)
            if len(seen) >= 2:
                stop.set()
            return None

        with patch('proxy_finder.service.secrets.choice',
                   side_effect=lambda _: next(chars)), patch(
                       'proxy_finder.service.fetch_ip_info',
                       side_effect=fetch):
            find_matching_ip(replace(self.settings, max_workers=2))
        self.assertEqual(seen[:2], ['m18maaaa', 'm18mbbbb'])
        self.assertTrue(all(len(item) == 8 for item in seen))

    def test_socks_dependency_installed(self):
        from requests.adapters import SOCKSProxyManager
        manager = SOCKSProxyManager('socks5://test:fake@localhost:32325')
        manager.clear()


if __name__ == '__main__':
    unittest.main()
