"""Outbound webhooks notifying integrators that a board changed.

A partner program can use this to flip "updated since last seen" badges without polling.
The webhook is optional - if ``TAVLE_WEBHOOK_URL`` is unset, this module is
a no-op and the integrator can fall back to polling ``/api/boards/<id>``
for the ``version`` field.

Delivery strategy:
- A background daemon thread coalesces events per ``board_id`` and waits
  ``TAVLE_WEBHOOK_DEBOUNCE_SECONDS`` (default 5s) of inactivity before
  posting. This stops a long drawing session from emitting hundreds of
  requests while still feeling near-realtime.
- Posts include an HMAC-SHA256 signature in the ``X-Tavle-Signature``
  header if ``TAVLE_WEBHOOK_SECRET`` is configured, so the receiver can
  reject forgeries.
- All failures are logged and dropped (no retries) - the receiver can
  always reconcile by polling. The whiteboard is the source of truth.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    return bool(os.environ.get('TAVLE_WEBHOOK_URL', '').strip())


def _config():
    return {
        'url': os.environ.get('TAVLE_WEBHOOK_URL', '').strip(),
        'secret': os.environ.get('TAVLE_WEBHOOK_SECRET', '').strip(),
        'debounce': float(os.environ.get('TAVLE_WEBHOOK_DEBOUNCE_SECONDS', '5') or 5),
        'timeout': float(os.environ.get('TAVLE_WEBHOOK_TIMEOUT_SECONDS', '5') or 5),
    }


# Per-board pending event state. We only need to remember the latest
# version (events are not deltas, they are "look at this board now"
# signals) so the dict value is the latest (version, updated_at_iso,
# scheduled_at) tuple.
_pending: dict[str, tuple[int, str, float]] = {}
_lock = threading.Lock()
_worker_started = False


def _ensure_worker():
    global _worker_started
    if _worker_started:
        return
    with _lock:
        if _worker_started:
            return
        thread = threading.Thread(target=_dispatch_loop, name='tavle-webhooks', daemon=True)
        thread.start()
        _worker_started = True


def _dispatch_loop():
    while True:
        time.sleep(1.0)
        try:
            _flush_due()
        except Exception as exc:  # pragma: no cover - keep daemon alive
            logger.error(f'Tavle webhook dispatcher crashed: {exc}')


def _flush_due():
    cfg = _config()
    if not cfg['url']:
        return
    now = time.time()
    due: list[tuple[str, int, str]] = []
    with _lock:
        for board_id, (version, updated_at, scheduled_at) in list(_pending.items()):
            if scheduled_at <= now:
                due.append((board_id, version, updated_at))
                _pending.pop(board_id, None)
    for board_id, version, updated_at in due:
        _post(cfg, board_id, version, updated_at)


def _post(cfg, board_id: str, version: int, updated_at: str):
    body = json.dumps({
        'event': 'board.updated',
        'board_id': board_id,
        'version': version,
        'updated_at': updated_at,
    }, ensure_ascii=False).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'tavle-webhook/1',
    }
    if cfg['secret']:
        sig = hmac.new(cfg['secret'].encode('utf-8'), body, hashlib.sha256).hexdigest()
        headers['X-Tavle-Signature'] = f'sha256={sig}'
    req = urllib.request.Request(cfg['url'], data=body, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=cfg['timeout']) as resp:  # noqa: S310
            if resp.status >= 400:
                logger.warning(
                    f'Tavle webhook for board {board_id[:8]} returned HTTP {resp.status}'
                )
    except urllib.error.HTTPError as exc:
        logger.warning(f'Tavle webhook HTTP error for board {board_id[:8]}: {exc.code}')
    except urllib.error.URLError as exc:
        logger.warning(f'Tavle webhook delivery failed for board {board_id[:8]}: {exc}')
    except Exception as exc:  # pragma: no cover
        logger.warning(f'Tavle webhook unexpected error for board {board_id[:8]}: {exc}')


def notify_board_updated(board_id: str, version: int, updated_at_iso: str):
    """Schedule a debounced ``board.updated`` webhook for ``board_id``.

    Safe to call from request handlers and socket handlers - returns
    immediately. Will not raise.
    """
    if not _enabled() or not board_id:
        return
    cfg = _config()
    debounce = max(0.0, cfg['debounce'])
    _ensure_worker()
    with _lock:
        # Always advance to the *latest* version we've seen; reset the
        # debounce timer so we wait for activity to settle.
        existing = _pending.get(board_id)
        new_version = max(int(version or 0), existing[0] if existing else 0)
        _pending[board_id] = (new_version, updated_at_iso, time.time() + debounce)
