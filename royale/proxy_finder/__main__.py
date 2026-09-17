"""CLI entry point with stoppable terminal polling on Windows and POSIX."""

import logging
import os
import select
import signal
import sys
from threading import Event, Thread

from . import Settings, find_matching_ip

logger = logging.getLogger(__name__)


def monitor_input(stop: Event) -> None:
    try:
        while not stop.wait(0.1):
            if os.name == 'nt':
                import msvcrt
                if msvcrt.kbhit() and msvcrt.getwch() in ('\r', '\n'):
                    stop.set()
            else:
                readable, _, _ = select.select([sys.stdin], [], [], 0)
                if readable:
                    line = sys.stdin.readline()
                    if not line:  # EOF must not cancel a background search.
                        return
                    if line.endswith('\n'):
                        stop.set()
    except (OSError, ValueError):
        logger.warning('Input terminal tidak tersedia; gunakan Ctrl+C.')


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')
    try:
        settings = Settings.from_env()
    except (ValueError, OSError) as exc:
        logger.error('Konfigurasi gagal (%s).', type(exc).__name__)
        if isinstance(exc, ValueError):
            logger.error('%s', exc)
        return 2
    stop = Event()
    previous_handler = signal.signal(signal.SIGINT, lambda *_: stop.set())
    input_thread = None
    try:
        if sys.stdin.isatty():
            logger.info('Tekan Enter atau Ctrl+C untuk berhenti.')
            input_thread = Thread(target=monitor_input, args=(stop,),
                                  name='terminal-input')
            input_thread.start()
        results = find_matching_ip(settings, stop)
        if results:
            for result in results:
                logger.info('IP: %s | Session: %s | City: %r | ISP: %r',
                            result['ip'], result['session'], result['city'],
                            result['isp'])
        else:
            logger.info('Tidak ada IP yang cocok.')
        return 0
    except Exception as exc:
        logger.error('Pencarian gagal (%s).', type(exc).__name__)
        return 1
    finally:
        stop.set()
        if input_thread is not None:
            input_thread.join()
        signal.signal(signal.SIGINT, previous_handler)


if __name__ == '__main__':
    raise SystemExit(main())
