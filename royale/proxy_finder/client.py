"""One isolated HTTP session per proxy session ID."""

import logging
import re
import time
from ipaddress import IPv4Address
from threading import Event
from typing import TypedDict
from urllib.parse import quote

import requests

from .config import Settings

logger = logging.getLogger(__name__)


class Match(TypedDict):
    ip: str
    session: str
    city: str
    isp: str


def build_proxies(settings: Settings, session_id: str) -> dict[str, str]:
    if not re.fullmatch(r'[A-Za-z0-9]{8}', session_id):
        raise ValueError('Session ID harus tepat 8 karakter alfanumerik.')
    password = settings.proxy_password
    if settings.country:
        password += f'_country-{settings.country}'
    if settings.city:
        password += f'_city-{settings.city}'
    password += (
        f'_session-{session_id}_lifetime-{settings.session_minutes}m'
    )
    proxy = (
        f'{settings.proxy_scheme}://'
        f'{quote(settings.proxy_username, safe="")}:'
        f'{quote(password, safe="")}@'
        f'{settings.proxy_host}:{settings.proxy_port}'
    )
    return {'http': proxy, 'https': proxy}


def fetch_ip_info(
    settings: Settings, session_id: str, stop: Event, deadline: float,
    observer=None,
) -> Match | None:
    remaining = deadline - time.monotonic()
    if stop.is_set() or remaining <= 0:
        return None
    try:
        with requests.Session() as session:
            # Do not inherit system proxies or .netrc credentials.
            session.trust_env = False
            with session.get(
                settings.ip_info_url,
                proxies=build_proxies(settings, session_id),
                timeout=min(settings.request_timeout, remaining),
                allow_redirects=False,
            ) as response:
                response.raise_for_status()
                if response.status_code != 200:
                    logger.warning('Session %s: status HTTP tidak sesuai.',
                                   session_id)
                    return None
                info = response.json()
        if not isinstance(info, dict) or not isinstance(info.get('ip'), str):
            raise ValueError('Invalid IP payload')
        ip_address = str(IPv4Address(info['ip']))
        city = info.get('city')
        isp = info.get('org')
        city = city if isinstance(city, str) and city else 'N/A'
        isp = isp if isinstance(isp, str) and isp else 'N/A'
        logger.info('ID: %s | IP: %s | CITY: %r | ASN: %r',
                    session_id, ip_address, city, isp)
        if stop.is_set() or time.monotonic() >= deadline:
            return None
        matched = ip_address.startswith(settings.target_prefix)
        if observer is not None:
            observer({'ip': ip_address, 'session': session_id, 'city': city,
                      'isp': isp, 'country': info.get('country'),
                      'matched': matched})
        if matched:
            return {'ip': ip_address, 'session': session_id,
                    'city': city, 'isp': isp}
    except requests.RequestException as exc:
        # Exception text can contain proxy URLs and credentials.
        logger.warning('Session %s: request gagal (%s).',
                       session_id, type(exc).__name__)
    except ValueError:
        logger.warning('Session %s: JSON atau IPv4 tidak valid.', session_id)
    return None
