import time
import unittest
from dataclasses import replace
from threading import Event
from unittest.mock import MagicMock, patch

import requests

from proxy_finder import Settings, find_matching_ip
from proxy_finder.client import build_proxies, fetch_ip_info


class FinderTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings('customer-test', 'fake@:/password',
                                 max_workers=2, execution_duration=0.2,
                                 batch_delay=0.01)

    def fetch(self, payload=None, error=None):
        session = MagicMock()
        response = session.get.return_value.__enter__.return_value
        response.status_code = 200
        response.json.return_value = payload
        response.raise_for_status.side_effect = error
        with patch('proxy_finder.client.requests.Session') as factory:
            factory.return_value.__enter__.return_value = session
            result = fetch_ip_info(self.settings, 't01q1', Event(),
                                   time.monotonic() + 1)
            factory.return_value.__exit__.assert_called_once()
        return result

    def test_match_and_missing_optional_fields(self):
        self.assertEqual(self.fetch({'ip': '88.230.184.12'}), {
            'ip': '88.230.184.12', 'session': 't01q1',
            'city': 'N/A', 'isp': 'N/A',
        })

    def test_invalid_payloads_and_nonmatch(self):
        for payload in ([], {}, {'ip': None}, {'ip': 'invalid'},
                        {'ip': '1.1.1.1'}):
            with self.subTest(payload=payload):
                self.assertIsNone(self.fetch(payload))

    def test_http_failure_does_not_log_credentials(self):
        with self.assertLogs('proxy_finder.client') as logs:
            self.assertIsNone(self.fetch(error=requests.HTTPError('SECRET')))
        self.assertNotIn('SECRET', ''.join(logs.output))

    def test_bad_json(self):
        with patch('proxy_finder.client.requests.Session') as factory:
            response = (factory.return_value.__enter__.return_value.get
                        .return_value.__enter__.return_value)
            response.status_code = 200
            response.json.side_effect = ValueError('invalid JSON')
            self.assertIsNone(fetch_ip_info(
                self.settings, 't01q1', Event(), time.monotonic() + 1,
            ))

    def test_encoding_and_secret_repr(self):
        proxy = build_proxies(self.settings, 't01q1')['https']
        self.assertIn('fake%40%3A%2Fpassword', proxy)
        self.assertNotIn(self.settings.proxy_password, repr(self.settings))

    def test_pre_cancelled_does_not_submit(self):
        stop = Event()
        stop.set()
        with patch('proxy_finder.service.fetch_ip_info') as fetch:
            self.assertIsNone(find_matching_ip(self.settings, stop))
            fetch.assert_not_called()

    def test_first_match_and_cleanup(self):
        stop = Event()
        match = {'ip': '88.230.184.2', 'session': 't01q1',
                 'city': 'N/A', 'isp': 'N/A'}
        with patch('proxy_finder.service.fetch_ip_info', return_value=match):
            self.assertEqual(find_matching_ip(self.settings, stop), [match])
        self.assertTrue(stop.is_set())

    def test_deadline_and_unique_session_ids(self):
        seen = []

        def fetch(settings, session_id, stop, deadline):
            seen.append(session_id)
            return None

        with patch('proxy_finder.service.fetch_ip_info', side_effect=fetch):
            self.assertIsNone(find_matching_ip(self.settings))
        self.assertGreater(len(seen), 2)
        self.assertEqual(len(seen), len(set(seen)))

    def test_cancellation_during_work(self):
        stop = Event()

        def fetch(*args):
            stop.set()
            return None

        with patch('proxy_finder.service.fetch_ip_info', side_effect=fetch):
            self.assertIsNone(find_matching_ip(self.settings, stop))

    def test_invalid_configuration(self):
        for changes in ({'request_timeout': float('nan')},
                        {'max_workers': 0}, {'proxy_password': ''},
                        {'execution_duration': -1},
                        {'ip_info_url': 'http://ipinfo.io/json'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.settings, **changes)


if __name__ == '__main__':
    unittest.main()
