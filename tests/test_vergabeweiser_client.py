import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from vergabeweiser_client import VergabeweiserClient, VergabeweiserRateLimited

class FakeResponse:
    def __init__(self, status_code, headers=None, payload=None):
        self.status_code, self.headers, self.payload = status_code, headers or {}, payload or {}
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(f"HTTP {self.status_code}")
    def json(self): return self.payload

class FakeSession:
    def __init__(self, responses): self.responses, self.calls = list(responses), []
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)

class VergabeweiserClientTests(unittest.TestCase):
    def test_429_persists_cooldown_and_prevents_second_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            pause, latest = Path(tmp)/"pause.json", Path(tmp)/"latest.json"
            session = FakeSession([FakeResponse(429, {"Retry-After":"3600"})])
            client = VergabeweiserClient(session, pause, latest)
            with self.assertRaises(VergabeweiserRateLimited): client.request_json("https://example.test")
            saved = json.loads(pause.read_text(encoding="utf-8"))
            self.assertGreater(datetime.fromisoformat(saved["paused_until"]), datetime.now(timezone.utc))
            self.assertEqual(len(session.calls), 1)
            restarted = VergabeweiserClient(session, pause, latest)
            with self.assertRaises(VergabeweiserRateLimited): restarted.request_json("https://example.test")
            self.assertEqual(len(session.calls), 1)

    def test_latest_snapshot_restores_cooldown(self):
        with tempfile.TemporaryDirectory() as tmp:
            latest, pause = Path(tmp)/"latest.json", Path(tmp)/"pause.json"
            deadline = (datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat()
            latest.write_text(json.dumps({"statistics":{"vergabeweiser_paused_until":deadline}}))
            session = FakeSession([])
            client = VergabeweiserClient(session, pause, latest)
            with self.assertRaises(VergabeweiserRateLimited): client.request_json("https://example.test")
            self.assertEqual(session.calls, [])

    def test_successful_response_returns_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = FakeSession([FakeResponse(200, payload={"results":[1,2]})])
            client = VergabeweiserClient(session, Path(tmp)/"pause.json", Path(tmp)/"latest.json")
            self.assertEqual(client.request_json("https://example.test"), {"results":[1,2]})
            self.assertEqual(len(session.calls), 1)

if __name__ == "__main__": unittest.main()
