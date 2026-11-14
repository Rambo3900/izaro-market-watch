import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import market_watch as m

NOW = datetime(2026, 11, 13, 20, 0, tzinfo=timezone.utc)


def gem(price, color="gruen", listings=10):
    return {"price_chaos": price, "color": color, "level": 1, "quality": 0,
            "listings": listings, "observations": 100}


class IzaroTests(unittest.TestCase):
    def test_league_never_falls_back_to_standard(self):
        self.assertIsNone(m.choose_league([{"id": "Standard"}, {"id": "Hardcore"}]))
        self.assertEqual(m.choose_league([{"id": "Covens of Umbra"}, {"id": "Standard"}]),
                         "Covens of Umbra")

    def test_catalog_is_transfigured_only_and_color_correct(self):
        items = [
            {"display_name": "Poisonous Concoction of Bouncing", "color": "g",
             "is_support": False,
             "base_item": {"display_name": "Poisonous Concoction", "release_state": "released"}},
            {"display_name": "Wave of Conviction", "color": "b",
             "is_support": False,
             "base_item": {"display_name": "Wave of Conviction", "release_state": "released"}},
            {"display_name": "Vaal Ice Shot (Ice Shot of Penetration)", "color": "g",
             "is_support": False,
             "base_item": {"display_name": "Vaal Ice Shot", "release_state": "released"}},
            {"display_name": "Bladefall of Trarthus", "color": "g",
             "is_support": False,
             "base_item": {"display_name": "Bladefall", "release_state": "released"}},
        ]
        items += [{"display_name": f"Gem {i} of Variant", "color": "b", "is_support": False,
                   "base_item": {"display_name": f"Gem {i}", "release_state": "released"}}
                  for i in range(120)]
        catalog = m.build_catalog(items)
        self.assertEqual(catalog["Poisonous Concoction of Bouncing"], "gruen")
        self.assertNotIn("Wave of Conviction", catalog)
        self.assertNotIn("Vaal Ice Shot (Ice Shot of Penetration)", catalog)
        self.assertNotIn("Bladefall of Trarthus", catalog)

    def test_cached_catalog_purges_heist_only_trarthan_gems(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "catalog.json"
            path.write_text(json.dumps({
                "source": "RePoE", "updated_at": m.iso(NOW),
                "gems": {"Bladefall of Trarthus": "gruen",
                         "Heavy Strike of Trarthus": "rot",
                         "Poisonous Concoction of Bouncing": "gruen"}
            }))
            with patch.object(m, "DATA", Path(td)), patch.object(m, "fetch",
                                                                 side_effect=AssertionError("do not refetch")):
                cleaned = m.get_catalog(NOW)
            self.assertEqual(cleaned, {"Poisonous Concoction of Bouncing": "gruen"})
            stored = json.loads(path.read_text())["gems"]
            self.assertNotIn("Bladefall of Trarthus", stored)
            self.assertNotIn("Heavy Strike of Trarthus", stored)

    def test_drop_only_gem_does_not_enter_market(self):
        catalog = m.exclude_non_font_gems({"Bladefall of Trarthus": "gruen",
                                            "Bladefall of Impaling": "gruen"})
        entries = [{"name": n, "gemLevel": 1, "gemQuality": 0,
                    "chaosValue": 137 if n.endswith("Trarthus") else 3,
                    "listingCount": 20, "count": 20, "corrupted": False}
                   for n in ("Bladefall of Trarthus", "Bladefall of Impaling")]
        result = m.extract(entries, catalog)
        self.assertEqual(list(result), ["Bladefall of Impaling"])

    def test_unlevelled_and_corrupted_and_high_quality_filtered(self):
        catalog = {"Poisonous Concoction of Bouncing": "gruen"}
        def line(level, quality, price, corrupt=False):
            return {"name": "Poisonous Concoction of Bouncing", "gemLevel": level,
                    "gemQuality": quality, "chaosValue": price,
                    "listingCount": 12, "count": 20, "corrupted": corrupt}
        rows = [
            line(21, 20, 9000),
            line(1, 0, 75, True),
            line(1, 20, 100),
            line(1, None, 33),
        ]
        result = m.extract(rows, catalog)
        self.assertEqual(result["Poisonous Concoction of Bouncing"]["price_chaos"], 33)

    def test_first_sample_is_not_alert(self):
        events, _ = m.detect({"Poisonous Concoction of Bouncing": gem(800)}, {}, {}, NOW)
        self.assertEqual(events, [])

    def test_large_move_alert_but_low_listings_no_alert(self):
        prior = {"Poisonous Concoction of Bouncing": gem(50),
                 "Kinetic Blast of Clustering": gem(30, "blau", 1)}
        current = {"Poisonous Concoction of Bouncing": gem(90),
                   "Kinetic Blast of Clustering": gem(100, "blau", 1)}
        events, cooldown = m.detect(current, prior, {}, NOW)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["gem"], "Poisonous Concoction of Bouncing")
        self.assertEqual(events[0]["change_percent"], 80)
        # A second small move a minute later should not repeat the alert.
        newer = {"Poisonous Concoction of Bouncing": gem(115),
                 "Kinetic Blast of Clustering": gem(100, "blau", 1)}
        repeat, _ = m.detect(newer, current, cooldown, NOW)
        self.assertEqual(repeat, [])

    def test_main_writes_baseline_and_no_null_alert(self):
        with tempfile.TemporaryDirectory() as td:
            catalog = {"Poisonous Concoction of Bouncing": "gruen"}
            responses = [
                [{"id": "Covens of Umbra"}, {"id": "Standard"}],
                {"lines": [{
                    "name": "Poisonous Concoction of Bouncing",
                    "gemLevel": 1, "gemQuality": 0, "chaosValue": 80,
                    "listingCount": 9, "count": 25, "corrupted": False
                }]}
            ]
            with patch.object(m, "DATA", Path(td)), patch.object(m, "fetch", side_effect=responses), \
                 patch.object(m, "get_catalog", return_value=catalog):
                self.assertEqual(m.main(), 0)
                last = json.loads((Path(td) / "latest.json").read_text())
                self.assertEqual(last["league"], "Covens of Umbra")
                alert = json.loads((Path(td) / "latest_alert.json").read_text())
                self.assertEqual(alert["events"], [])
                self.assertEqual(len(json.loads((Path(td) / "history.json").read_text())["samples"]), 1)

    def test_main_skips_standard_without_creating_data(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(m, "DATA", Path(td)), patch.object(m, "fetch",
                                                                 return_value=[{"id": "Standard"}, {"id": "Hardcore"}]):
                self.assertEqual(m.main(), 0)
                self.assertFalse((Path(td) / "latest.json").exists())


if __name__ == "__main__":
    unittest.main()
