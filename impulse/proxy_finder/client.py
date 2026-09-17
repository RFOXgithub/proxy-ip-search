"""One isolated HTTP session per sticky proxy port."""

import logging
import time
from ipaddress import IPv4Address
from threading import Event
from typing import NamedTuple
from urllib.parse import quote

import requests

from .config import Settings

logger = logging.getLogger(__name__)


class Match(NamedTuple):
    ip: str
    port: int
    city: str
    isp: str


def build_proxies(settings: Settings, port: int) -> dict[str, str]:
    if not settings.start_port <= port <= settings.end_port:
        raise ValueError('Port di luar rentang konfigurasi.')
    filters = [f'cr.{settings.country}'] if settings.country else []
    if settings.proxy_mode in ('location', 'combined') and settings.city:
        filters.append(f'city.{settings.city}')
    if (settings.proxy_mode in ('asn', 'combined')
            and settings.asn is not None):
        filters.append(f'asn.{settings.asn}')
    username = settings.proxy_username
    if filters:
        username += '__' + ';'.join(filters)
    proxy = (
        f'http://{quote(username, safe="")}:'
        f'{quote(settings.proxy_password, safe="")}@'
        f'{settings.proxy_host}:{port}'
    )
    return {'http': proxy, 'https': proxy}


def fetch_ip_info(
    settings: Settings, port: int, stop: Event, deadline: float, observer=None,
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
                proxies=build_proxies(settings, port),
                timeout=min(settings.request_timeout, remaining),
                allow_redirects=False,
            ) as response:
                response.raise_for_status()
                if response.status_code != 200:
                    logger.warning('Port %s: status HTTP tidak sesuai.',
                                   port)
                    return None
                info = response.json()
        if not isinstance(info, dict) or not isinstance(info.get('ip'), str):
            raise ValueError('Invalid IP payload')
        ip_address = str(IPv4Address(info['ip']))
        city = info.get('city')
        isp = info.get('org')
        city = city if isinstance(city, str) and city else 'N/A'
        isp = isp if isinstance(isp, str) and isp else 'N/A'
        logger.info('PORT: %s | IP: %s | CITY: %r | ASN: %r',
                    port, ip_address, city, isp)
        if stop.is_set() or time.monotonic() >= deadline:
            return None
        matched = ip_address.startswith(settings.target_prefix)
        if observer is not None:
            observer({'ip': ip_address, 'port': port, 'city': city,
                      'isp': isp, 'country': info.get('country'),
                      'matched': matched})
        if matched:
            return Match(ip_address, port, city, isp)
    except requests.RequestException as exc:
        # Exception text can contain proxy URLs and credentials.
        logger.warning('Port %s: request gagal (%s).',
                       port, type(exc).__name__)
    except ValueError:
        logger.warning('Port %s: JSON atau IPv4 tidak valid.', port)
    return None
