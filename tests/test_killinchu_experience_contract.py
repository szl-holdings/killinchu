import unittest

import killinchu_experience as experience


class ExperienceManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = experience.build_manifest("killinchu")
        self.surfaces = self.manifest["surfaces"]

    def test_manifest_has_all_discoverable_surfaces(self):
        self.assertEqual(48, self.manifest["surface_count"])
        self.assertEqual(48, len(self.surfaces))
        ids = [row["id"] for row in self.surfaces]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue({"hero_interdiction", "mosaic", "kc_energy", "route_spaces"} <= set(ids))

    def test_every_surface_has_an_honest_contract(self):
        required = {
            "id",
            "label",
            "route",
            "kind",
            "visibility",
            "purpose",
            "source",
            "data_state",
            "evidence_state",
            "operational_boundary",
            "investor_value",
        }
        for row in self.surfaces:
            self.assertFalse(required - row.keys(), row["id"])
            self.assertTrue(row["operational_boundary"].strip(), row["id"])
            self.assertTrue(row["investor_value"].strip(), row["id"])

    def test_automatic_probes_are_get_only_api_reads(self):
        for row in self.surfaces:
            source = row["source"]
            if source["safe_probe"]:
                self.assertEqual("GET", source["method"], row["id"])
                self.assertTrue(source["endpoint"].startswith("/api/"), row["id"])
        decoder = next(row for row in self.surfaces if row["id"] == "decoders")
        self.assertEqual("POST", decoder["source"]["method"])
        self.assertFalse(decoder["source"]["safe_probe"])

    def test_visibility_counts_match_the_audit(self):
        counts = self.manifest["summary"]["by_visibility"]
        self.assertEqual(6, counts["hidden_r_and_d"])
        self.assertEqual(6, counts["retired_from_nav"])
        self.assertEqual(11, counts["runtime"])
        self.assertEqual(25, counts["primary"])

    def test_ui_layer_is_accessible_and_read_only(self):
        html = experience.EXPERIENCE_LAYER_HTML
        self.assertIn("__KILLINCHU_EXPERIENCE_LAYER_V1__", html)
        self.assertIn("aria-label','Data and evidence passport", html)
        self.assertIn("setAttribute('role','button')", html)
        self.assertIn("var nativeLink=node.tagName", html)
        self.assertIn("if(!nativeLink)", html)
        self.assertIn("e.key==='Enter'||e.key===' '", html)
        self.assertIn("aria-current", html)
        self.assertNotIn("method:'POST'", html)
        self.assertIn("row.source.safe_probe", html)

    def test_mobile_surface_finder_is_keyboard_and_touch_accessible(self):
        html = experience.EXPERIENCE_LAYER_HTML
        self.assertIn("__KILLINCHU_SURFACE_FINDER_V2__", html)
        self.assertIn("role','search'", html)
        self.assertIn('type="search"', html)
        self.assertIn('aria-label="Clear surface filter"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn("if(e.key==='/'", html)
        self.assertIn("e.key==='Escape'", html)
        self.assertIn("height:44px", html)
        self.assertIn("max-width:820px", html)
        self.assertNotIn("method:'POST'", html)

    def test_manifest_declares_the_operator_ui_contract(self):
        contract = self.manifest["operator_ui"]
        self.assertEqual("ENABLED", contract["surface_finder"])
        self.assertEqual("/", contract["keyboard_shortcut"])
        self.assertTrue(contract["escape_clears_filter"])
        self.assertEqual(44, contract["minimum_touch_target_css_px"])
        self.assertTrue(contract["read_only"])


if __name__ == "__main__":
    unittest.main()
