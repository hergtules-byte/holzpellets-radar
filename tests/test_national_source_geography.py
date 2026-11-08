"""Tests für die geografische Zuordnung nationaler Bekanntmachungen."""
import unittest

from national_source import _resolve_state


class NationalSourceGeographyTests(unittest.TestCase):
    def test_target_state_performance_place_is_accepted(self):
        state, place = _resolve_state(
            [{"placePerformanceCountrySubdivision": "DE40", "placePerformanceCity": "Potsdam"}],
            [{"organisationCountrySubdivision": "DE80", "organisationCity": "Rostock"}],
        )
        self.assertEqual((state, place), ("Brandenburg", "Potsdam"))

    def test_outside_performance_place_is_not_overridden_by_target_buyer(self):
        state, place = _resolve_state(
            [{"placePerformanceCountrySubdivision": "DE11", "placePerformanceCity": "Stuttgart"}],
            [{"organisationCountrySubdivision": "DE40", "organisationCity": "Potsdam"}],
        )
        self.assertIsNone(state)
        self.assertEqual(place, "")

    def test_target_buyer_fallback_when_no_performance_region_is_provided(self):
        state, place = _resolve_state(
            [{"placePerformanceCity": "Unbekannt"}],
            [{"organisationCountrySubdivision": "DE40", "organisationCity": "Potsdam"}],
        )
        self.assertEqual((state, place), ("Brandenburg", "Potsdam"))

    def test_no_target_state_when_both_locations_are_outside(self):
        state, place = _resolve_state(
            [{"placePerformanceCountrySubdivision": "DE11", "placePerformanceCity": "Stuttgart"}],
            [{"organisationCountrySubdivision": "DE80", "organisationCity": "Rostock"}],
        )
        self.assertIsNone(state)
        self.assertEqual(place, "")

    def test_any_target_performance_location_is_found(self):
        state, place = _resolve_state(
            [
                {"placePerformanceCountrySubdivision": "DE11", "placePerformanceCity": "Stuttgart"},
                {"placePerformanceCountrySubdivision": "DE40", "placePerformanceCity": "Potsdam"},
            ],
            [],
        )
        self.assertEqual((state, place), ("Brandenburg", "Potsdam"))


if __name__ == "__main__":
    unittest.main()
