"""Positiv- und Negativtests für die fachliche Brennstoffklassifikation."""
import unittest

from national_source import _category


class NationalSourceClassificationTests(unittest.TestCase):
    def test_ted_wood_fuel_cpv_is_positive(self):
        self.assertEqual(
            _category(
                "Rahmenvereinbarung Pellets",
                "Lieferung von Holzpellets für die Wärmeversorgung",
                ["09111400"],
            ),
            "Holzbrennstoff – CPV 09111400",
        )

    def test_wood_chips_cpv_is_positive(self):
        self.assertEqual(
            _category(
                "Lieferung von Holzhackschnitzeln",
                "Brennstoff für das Heizwerk",
                ["03413000"],
            ),
            "Holzhackschnitzel / Holzbrennstoff – CPV 03413000",
        )

    def test_explicit_wood_pellets_title_is_positive_without_cpv(self):
        self.assertEqual(
            _category("Holzpellets für das Heizwerk", "Jahresbedarf", []),
            "Holzpellets eindeutig",
        )

    def test_wood_briquettes_title_is_positive(self):
        self.assertEqual(
            _category("Lieferung Holzbriketts", "Lieferung frei Lager", []),
            "Sonstiger Holzbrennstoff",
        )

    def test_coal_dust_title_is_positive(self):
        self.assertEqual(
            _category("Lieferung Braunkohlestaub", "Brennstofflieferung", []),
            "BKS / Kohle",
        )

    def test_generic_pellets_with_heating_context_are_flagged_for_review(self):
        self.assertEqual(
            _category("Lieferung von Pellets für Heizkessel", "Jahresbedarf", []),
            "Pellets – Holzart prüfen",
        )

    def test_biomass_boiler_equipment_is_not_a_fuel_delivery(self):
        self.assertIsNone(
            _category(
                "Biomassekesselanlage 2x 1400 kW Leistung",
                "Lieferung und Montage von Holzhackschnitzelfeuerungsanlagen",
                ["09324000"],
            )
        )

    def test_incidental_wood_chips_in_building_work_are_rejected(self):
        self.assertIsNone(
            _category(
                "Neubau Bauhof Greifswald",
                "Betonboden für Hackschnitzelhalle und Innenputz",
                ["45000000"],
            )
        )

    def test_polymer_pellet_processing_equipment_is_rejected(self):
        self.assertIsNone(
            _category(
                "Mikrocompoundier- und Spritzgießsystem",
                "Extruder zum Einzug von Pellets und Dosiersystem für Polymere",
                ["38430000", "42994000"],
            )
        )


if __name__ == "__main__":
    unittest.main()
