import unittest
from unittest.mock import Mock, patch
from ted_source import _category, _search


class FakeResponse:
    def __init__(self, payload, status=200, headers=None):
        self.payload, self.status_code = payload, status
        self.headers = headers or {}
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")
    def json(self):
        return self.payload


class TedSourceTests(unittest.TestCase):
    def test_fuel_delivery_title_is_positive(self):
        self.assertEqual(_category("Rahmenvereinbarung Holzpellets", "Lieferung", []),
                         "Holzpellets eindeutig")

    def test_heating_project_is_not_fuel_delivery(self):
        self.assertIsNone(_category("Umstellung auf Pelletfeuerung",
                                    "Lieferung und Montage einer Pelletheizung", []))

    def test_incidental_description_mention_is_not_positive(self):
        self.assertIsNone(_category("Neubau Verwaltungsgebäude",
                                    "Pellets werden im Energiekonzept erwähnt", []))

    def test_cpv_fuel_is_positive(self):
        self.assertEqual(_category("Rahmenvertrag Brennstoff", "", ["09111400"]),
                         "Holzbrennstoff – CPV 09111400")

    def test_search_fetches_all_pages(self):
        session = Mock()
        session.post.side_effect = [
            FakeResponse({"totalNoticeCount": 3, "notices": [{"id": 1}, {"id": 2}]}),
            FakeResponse({"totalNoticeCount": 3, "notices": [{"id": 3}]}),
        ]
        with patch("ted_source.time.sleep"):
            rows = _search(session, "query", limit=2)
        self.assertEqual(len(rows), 3)
        self.assertEqual([c.kwargs["json"]["page"] for c in session.post.call_args_list], [1, 2])

    def test_429_then_success_retries(self):
        session = Mock()
        session.post.side_effect = [
            FakeResponse({}, status=429, headers={"Retry-After": "0"}),
            FakeResponse({"totalNoticeCount": 1, "notices": [{"id": 1}]}),
        ]
        with patch("ted_source.time.sleep"):
            self.assertEqual(len(_search(session, "query", limit=2)), 1)
        self.assertEqual(session.post.call_count, 2)

    def test_503_then_success_retries(self):
        session = Mock()
        session.post.side_effect = [
            FakeResponse({}, status=503),
            FakeResponse({"totalNoticeCount": 1, "notices": [{"id": 1}]}),
        ]
        with patch("ted_source.time.sleep"):
            self.assertEqual(len(_search(session, "query", limit=2)), 1)
        self.assertEqual(session.post.call_count, 2)

    def test_repeated_429_fails_after_retry_limit(self):
        session = Mock()
        session.post.side_effect = [FakeResponse({}, status=429)] * 4
        with patch("ted_source.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "429"):
                _search(session, "query", limit=2)
        self.assertEqual(session.post.call_count, 4)

    def test_page_cap_never_silently_truncates(self):
        session = Mock()
        session.post.side_effect = [
            FakeResponse({"totalNoticeCount": 5, "notices": [{"id": 1}, {"id": 2}]}),
            FakeResponse({"totalNoticeCount": 5, "notices": [{"id": 3}, {"id": 4}]}),
        ]
        with patch("ted_source.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "pagination limit"):
                _search(session, "query", limit=2, max_pages=2)


if __name__ == "__main__":
    unittest.main()
