"""Synchronous search service; independent from terminal and web framework."""

import logging
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from threading import Event

from .client import Match, fetch_ip_info
from .config import Settings

logger = logging.getLogger(__name__)


def find_matching_ip(
    settings: Settings, stop_event: Event | None = None, observer=None,
) -> list[Match] | None:
    """Return one match in a list, or None, matching the original contract.

    The deadline stops scheduling/accepting results. In-flight requests are
    drained before return; Requests timeouts are not hard wall-clock limits.
    """
    stop = stop_event if stop_event is not None else Event()
    deadline = time.monotonic() + settings.execution_duration
    next_session = settings.start_session
    executor = ThreadPoolExecutor(max_workers=settings.max_workers)
    pending = set()
    try:
        while not stop.is_set() and time.monotonic() < deadline:
            # Bounded batches preserve the old concurrency pattern.
            for _ in range(settings.max_workers):
                if stop.is_set() or time.monotonic() >= deadline:
                    break
                session_id = f'{settings.session_prefix}{next_session}'
                next_session += 1
                args = (settings, session_id, stop, deadline)
                if observer is not None:
                    args += (observer,)
                pending.add(executor.submit(fetch_ip_info, *args))
            while pending and not stop.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                done, pending = wait(
                    pending, timeout=min(0.1, remaining),
                    return_when=FIRST_COMPLETED,
                )
                for future in done:
                    # Unexpected programming errors propagate to the caller.
                    result = future.result()
                    if (result and not stop.is_set()
                            and time.monotonic() < deadline):
                        logger.info('Matched IP: %s | Session: %s',
                                    result['ip'], result['session'])
                        return [result]
            if pending or stop.is_set():
                break
            stop.wait(min(settings.batch_delay,
                          max(0.0, deadline - time.monotonic())))
        logger.info('Pencarian dihentikan atau durasi habis.')
        return None
    finally:
        stop.set()
        for future in pending:
            future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)
