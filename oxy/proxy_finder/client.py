"""One isolated HTTP session per proxy session ID."""

import logging
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
    username = (
        f'{settings.proxy_username}-sessid-{session_id}'
        f'-sesstime-{settings.session_minutes}'
    )
    if settings.proxy_mode == 'asn' and settings.asn is not None:
        username += f'-asn-{settings.asn}'
    else:
        if settings.country:
            username += f'-cc-{settings.country}'
        if settings.city:
            username += f'-city-{settings.city}'
    proxy = (
        f'http://{quote(username, safe="")}:'
        f'{quote(settings.proxy_password, safe="")}@'
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
