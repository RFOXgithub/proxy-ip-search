"""Load and validate configuration without exposing secrets."""

import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    proxy_username: str = field(repr=False)
    proxy_password: str = field(repr=False)
    proxy_host: str = 'pr.oxylabs.io'
    proxy_port: int = 7777
    ip_info_url: str = 'https://ipinfo.io/json'
    target_prefix: str = '88.230.184.'
    session_prefix: str = 't01q'
    country: str = 'tr'
    proxy_mode: str = 'location'
    asn: int | None = 9121
    city: str = ''
    session_minutes: int = 30
    start_session: int = 1
    max_workers: int = 25
    request_timeout: float = 5.0
    execution_duration: float = 200.0
    batch_delay: float = 0.25

    def __post_init__(self) -> None:
        if not self.proxy_username or not self.proxy_password:
            raise ValueError('PROXY_USERNAME dan PROXY_PASSWORD wajib diisi.')
        if not re.fullmatch(r'[A-Za-z0-9.-]+', self.proxy_host):
            raise ValueError(
                'PROXY_HOST harus berupa hostname tanpa skema/port.'
            )
        if not 1 <= self.proxy_port <= 65535:
            raise ValueError('PROXY_PORT harus antara 1 dan 65535.')
        if not 1 <= self.max_workers <= 100:
            raise ValueError('MAX_WORKERS harus antara 1 dan 100.')
        if self.start_session < 0 or self.session_minutes <= 0:
            raise ValueError('START_SESSION >= 0 dan SESSION_MINUTES > 0.')
        for name in ('request_timeout', 'execution_duration', 'batch_delay'):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f'{name} harus angka finite >= 0.')
        if self.request_timeout == 0 or self.execution_duration == 0:
            raise ValueError('Timeout dan durasi harus lebih besar dari nol.')
        if not re.fullmatch(r'[A-Za-z0-9]+', self.session_prefix):
            raise ValueError('SESSION_PREFIX harus alfanumerik.')
        if self.proxy_mode not in ('asn', 'location'):
            raise ValueError('PROXY_MODE harus asn atau location.')
        if self.proxy_mode == 'asn':
            if self.asn is not None and not 1 <= self.asn <= 4294967295:
                raise ValueError('ASN harus angka antara 1 dan 4294967295.')
        else:
            if self.country and not re.fullmatch(r'[a-z]{2}', self.country):
                raise ValueError('COUNTRY harus kode dua huruf kecil bila diisi.')
            if self.city and not re.fullmatch(r'[a-z0-9_]+', self.city):
                raise ValueError(
                    'CITY harus slug huruf kecil/angka/underscore provider.'
                )
        parts = self.target_prefix.rstrip('.').split('.')
        if not self.target_prefix or len(parts) > 4 or any(
            not p.isascii() or not p.isdigit() or not 0 <= int(p) <= 255
            for p in parts
        ):
            raise ValueError(
                'TARGET_IP_PREFIX harus prefix IPv4 yang valid.'
            )
        url = urlsplit(self.ip_info_url)
        if (url.scheme != 'https' or not url.hostname or url.username
                or url.password or url.fragment):
            raise ValueError('IP_INFO_URL harus HTTPS tanpa kredensial/fragment.')

    @classmethod
    def from_env(cls, path: Path | None = None) -> 'Settings':
        load_dotenv(path or Path(__file__).resolve().parents[1] / '.env')
        names = {
            'proxy_username': 'PROXY_USERNAME',
            'proxy_password': 'PROXY_PASSWORD',
            'proxy_host': 'PROXY_HOST',
            'ip_info_url': 'IP_INFO_URL',
            'target_prefix': 'TARGET_IP_PREFIX',
            'session_prefix': 'SESSION_PREFIX',
            'country': 'COUNTRY',
            'proxy_mode': 'PROXY_MODE',
            'city': 'CITY',
        }
        values = {key: os.environ[env] for key, env in names.items()
                  if env in os.environ}
        values.setdefault('proxy_username', '')
        values.setdefault('proxy_password', '')
        for key in ('proxy_mode', 'country', 'city'):
            if key in values:
                values[key] = values[key].strip().lower()
        numeric = {
            'proxy_port': ('PROXY_PORT', int),
            'session_minutes': ('SESSION_MINUTES', int),
            'start_session': ('START_SESSION', int),
            'max_workers': ('MAX_WORKERS', int),
            'request_timeout': ('REQUEST_TIMEOUT', float),
            'execution_duration': ('EXECUTION_DURATION', float),
            'batch_delay': ('BATCH_DELAY', float),
        }
        if values.get('proxy_mode', 'location') == 'asn':
            numeric['asn'] = ('ASN', int)
        for key, (env, convert) in numeric.items():
            if env in os.environ:
                if key == 'asn' and not os.environ[env].strip():
                    values[key] = None
                    continue
                try:
                    values[key] = convert(os.environ[env])
                except ValueError:
                    raise ValueError(
                        f'{env} harus angka yang valid.'
                    ) from None
        return cls(**values)
