"""Isolated Vergabeweiser HTTP client with persistent HTTP 429 cooldown."""
import json
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

class VergabeweiserRateLimited(Exception):
    """Raised when the provider is in a persisted rate-limit cooldown."""

class VergabeweiserClient:
    def __init__(self, session, pause_file, data_file):
        self.session = session
        self.pause_file = Path(pause_file)
        self.data_file = Path(data_file)
        self.paused_until = self._read_pause()

    @staticmethod
    def _parse_deadline(value):
        until = datetime.fromisoformat(value)
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        return until.astimezone(timezone.utc)

    def _read_pause(self):
        for path, key_path in ((self.pause_file, None), (self.data_file, ("statistics", "vergabeweiser_paused_until"))):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                value = payload.get("paused_until") if key_path is None else payload.get(key_path[0], {}).get(key_path[1])
                if value:
                    until = self._parse_deadline(value)
                    if until > datetime.now(timezone.utc):
                        return until
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                continue
        return None

    def _save_pause(self, response):
        retry_after = response.headers.get("Retry-After", "").strip()
        now = datetime.now(timezone.utc)
        try:
            until = now + timedelta(seconds=max(1, int(float(retry_after))))
        except (TypeError, ValueError, OverflowError):
            try:
                until = parsedate_to_datetime(retry_after).astimezone(timezone.utc)
            except (TypeError, ValueError, OverflowError):
                until = now + timedelta(hours=1)
        if until <= now:
            until = now + timedelta(minutes=1)
        self.pause_file.parent.mkdir(parents=True, exist_ok=True)
        self.pause_file.write_text(json.dumps({"paused_until": until.isoformat(), "reason": "HTTP 429"}, indent=2), encoding="utf-8")
        self.paused_until = until
        return until

    def request_json(self, url, params=None, max_retries=4):
        if self.paused_until and self.paused_until > datetime.now(timezone.utc):
            raise VergabeweiserRateLimited(f"Vergabeweiser pausiert bis {self.paused_until.isoformat()}")
        for attempt in range(max_retries + 1):
            response = self.session.get(url, params=params, timeout=45)
            if response.status_code == 429:
                until = self._save_pause(response)
                raise VergabeweiserRateLimited(f"HTTP 429; Vergabeweiser pausiert bis {until.isoformat()}")
            if response.status_code in (500, 502, 503, 504):
                if attempt >= max_retries:
                    response.raise_for_status()
                time.sleep(min(2 ** attempt, 30))
                continue
            response.raise_for_status()
            return response.json()
