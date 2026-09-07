# SPDX-License-Identifier: Apache-2.0
"""Source contracts complement the measured offline Chromium regression."""
from pathlib import Path
import re
import unittest

CSS_PATH = Path(__file__).resolve().parents[1] / "static/szl-obsidian-signal.css"


class FamilyNavigationTargets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css = CSS_PATH.read_text(encoding="utf-8")

    def test_identity_has_a_nonshrinking_target_floor(self):
        rule = re.search(r"\.szl-family-identity\{([^}]+)\}", self.css)
        self.assertIsNotNone(rule)
        for dimension in ("width", "height"):
            value = re.search(r"min-" + dimension + r":([0-9.]+)px", rule.group(1))
            self.assertIsNotNone(value)
            self.assertGreaterEqual(float(value.group(1)), 44)

    def test_no_responsive_identity_override_shrinks_below_floor(self):
        for body in re.findall(r"\.szl-family-identity\{([^}]+)\}", self.css):
            for value in re.findall(r"min-height:([0-9.]+)px", body):
                self.assertGreaterEqual(float(value), 44)

    def test_overflow_alignment_preserves_earlier_navigation(self):
        body = re.search(r"\.szl-family-track\{([^}]+)\}", self.css).group(1)
        self.assertIn("justify-content:flex-start;justify-content:safe flex-end", body)
        self.assertIn("overflow-x:auto", body)
        self.assertNotIn("justify-content:flex-end;", body)

    def test_native_focus_and_accessibility_media_remain(self):
        for marker in (":focus-visible", "outline-offset:3px", "prefers-reduced-motion", "forced-colors"):
            self.assertIn(marker, self.css)

    def test_no_new_remote_css_dependency(self):
        self.assertNotIn("@import", self.css)
        self.assertIsNone(re.search(r"url\(\s*[\"']?https?:", self.css, re.I))


if __name__ == "__main__":
    unittest.main()
