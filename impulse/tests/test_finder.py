import os
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock, patch
from urllib.parse import unquote, urlsplit

import requests

from proxy_finder import Settings, find_matching_ip
from proxy_finder.client import Match, build_proxies, fetch_ip_info


class FinderTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings('test-login', 'fake@:/password',
                                 end_port=10002, execution_duration=0.2, asn=31721,
                                 batch_delay=0)

    def username(self, settings):
        return unquote(urlsplit(build_proxies(settings, 10000)['http'])
                       .username)

    def test_combined_username(self):
        self.assertEqual(self.username(self.settings),
                         'test-login__cr.az;city.baku;asn.31721')

    def test_modes(self):
        for mode, city, expected in (
            ('asn', 'ignored', 'test-login__cr.az;asn.31721'),
            ('location', 'baku', 'test-login__cr.az;city.baku'),
            ('location', '', 'test-login__cr.az'),
        ):
            settings = replace(self.settings, proxy_mode=mode, city=city)
            self.assertEqual(self.username(settings), expected)

    def test_env_mapping_and_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text('PROXY_USERNAME=test\nPROXY_PASSWORD=fake\n'
                            'PROXY_MODE=ASN\nASN=31721\nCOUNTRY=AZ\n'
                            'START_PORT=10005\nEND_PORT=10009\n')
            with patch.dict(os.environ, {'ASN': '9121'}, clear=True):
                settings = Settings.from_env(path)
        self.assertEqual(settings.asn, 9121)
        self.assertEqual(settings.proxy_mode, 'asn')
        self.assertEqual(settings.start_port, 10005)
        self.assertEqual(settings.end_port, 10009)

    def test_optional_asn_from_env(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            for mode in ('asn', 'combined'):
                for setting in ('', 'ASN=\n', 'ASN="   "\n'):
                    path.write_text(
                        'PROXY_USERNAME=test\nPROXY_PASSWORD=fake\n'
                        f'PROXY_MODE={mode}\n' + setting
                    )
                    with patch.dict(os.environ, {}, clear=True):
                        settings = Settings.from_env(path)
                    self.assertIsNone(settings.asn)
                    expected = 'test__cr.az'
                    if mode == 'combined':
                        expected += ';city.baku'
                    self.assertEqual(self.username(settings), expected)

    def test_combined_country_only(self):
        settings = replace(self.settings, asn=None, city='')
        self.assertEqual(self.username(settings), 'test-login__cr.az')

    def test_secrets_and_encoding(self):
        proxy = build_proxies(self.settings, 10000)['https']
        self.assertIn('fake%40%3A%2Fpassword', proxy)
        self.assertNotIn(self.settings.proxy_password, repr(self.settings))

    def fetch(self, payload=None, error=None, json_error=None):
        session = MagicMock()
        response = session.get.return_value.__enter__.return_value
        response.status_code = 200
        response.raise_for_status.side_effect = error
        response.json.return_value = payload
        response.json.side_effect = json_error
        with patch('dataimpulse_finder.client.requests.Session') as factory:
            factory.return_value.__enter__.return_value = session
            result = fetch_ip_info(self.settings, 10000, Event(),
                                   time.monotonic() + 1)
            factory.return_value.__exit__.assert_called_once()
        return result

    def test_match_tuple_contract(self):
        result = self.fetch({'ip': '185.30.88.2', 'city': 'Baku', 'org': 'ISP'})
        self.assertEqual(result, ('185.30.88.2', 10000, 'Baku', 'ISP'))
        self.assertIsInstance(result, tuple)

    def test_missing_optional_fields(self):
        self.assertEqual(self.fetch({'ip': '185.30.88.2'}),
                         ('185.30.88.2', 10000, 'N/A', 'N/A'))

    def test_bad_payloads(self):
        for payload in ({}, [], {'ip': None}, {'ip': 'bad'},
                        {'ip': '1.1.1.1'}):
            self.assertIsNone(self.fetch(payload))
        self.assertIsNone(self.fetch(json_error=ValueError()))

    def test_http_error_redacted(self):
        with self.assertLogs('dataimpulse_finder.client') as logs:
            self.assertIsNone(self.fetch(error=requests.HTTPError('SECRET')))
        self.assertNotIn('SECRET', ''.join(logs.output))

    def test_ports_increase_and_stop_at_end(self):
        seen = []

        def fetch(settings, port, stop, deadline):
            seen.append(port)
            return None

        with patch('dataimpulse_finder.service.fetch_ip_info',
                   side_effect=fetch):
            self.assertIsNone(find_matching_ip(self.settings))
        self.assertEqual(sorted(seen), [10000, 10001, 10002])

    def test_cancel_before_start(self):
        stop = Event()
        stop.set()
        with patch('dataimpulse_finder.service.fetch_ip_info') as fetch:
            self.assertIsNone(find_matching_ip(self.settings, stop))
            fetch.assert_not_called()

    def test_first_match(self):
        match = Match('185.30.88.2', 10000, 'Baku', 'ISP')
        with patch('dataimpulse_finder.service.fetch_ip_info',
                   return_value=match):
            self.assertEqual(find_matching_ip(self.settings), [match])

    def test_deadline_rejects_late_result(self):
        def fetch(*args):
            time.sleep(0.03)
            return Match('185.30.88.2', 10000, 'Baku', 'ISP')

        with patch('dataimpulse_finder.service.fetch_ip_info',
                   side_effect=fetch):
            self.assertIsNone(find_matching_ip(replace(
                self.settings, execution_duration=0.01,
            )))

    def test_validation(self):
        for changes in ({'start_port': 9999}, {'end_port': 20001},
                        {'start_port': 10003}, {'country': ''},
                        {'proxy_mode': 'bad'}, {'asn': 0},
                        {'city': 'baku;asn.1'}, {'max_workers': 0},
                        {'proxy_username': 'login__cr.az'},
                        {'request_timeout': float('nan')}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.settings, **changes)


if __name__ == '__main__':
    unittest.main()
