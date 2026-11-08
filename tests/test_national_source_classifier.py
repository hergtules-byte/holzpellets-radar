"""Tests für die konservative fachliche Klassifizierung nationaler Bekanntmachungen."""
import unittest

from national_source import _category


class NationalSourceCategoryTests(unittest.TestCase):
    def test_incidental_hackschnitzel_mention_does_not_match_bauhof(self):
        self.assertIsNone(_category(
            "Neubau Bauhof Greifswald",
            "Beschreibung erwähnt Hackschnitzel nur beiläufig.",
            ["45000000"],
        ))

    def test_biomass_boiler_without_fuel_procurement_cpv_is_not_a_fuel_tender(self):
        self.assertIsNone(_category(
            "Biomassekesselanlage 2x 1400 kW Leistung",
            "Beschreibung erwähnt Hackschnitzel im technischen Zusammenhang.",
            ["09324000"],
        ))

    def test_polymer_pellets_machine_is_rejected(self):
        self.assertIsNone(_category(
            "Mikrocompoundier- und Spritzgießsystem inklusive Rheologischer Analyse",
            "Verarbeitung von Kunststoff-Pellets und Granulat.",
            ["38430000", "42994000"],
        ))

    def test_explicit_wood_pellet_title_is_accepted(self):
        self.assertEqual(
            _category("Lieferung von Holzpellets", "", ["09111400"]),
            "Holzbrennstoff – CPV 09111400",
        )

    def test_wood_chips_cpv_is_accepted(self):
        self.assertEqual(
            _category("Lieferung von Brennstoff", "", ["03413000"]),
            "Holzhackschnitzel / Holzbrennstoff – CPV 03413000",
        )

    def test_coal_in_title_is_accepted(self):
        self.assertEqual(
            _category("Lieferung von Braunkohlestaub", "", ["09111100"]),
            "BKS / Kohle",
        )


if __name__ == "__main__":
    unittest.main()
