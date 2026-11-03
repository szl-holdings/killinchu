from pathlib import Path
import re
import subprocess
import unittest
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]


class ReadmeLinkContractTests(unittest.TestCase):
    def test_relative_readme_links_match_tracked_paths_exactly(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        tracked = set(
            subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
        )
        missing = []
        for raw in re.findall(r"\]\(([^)]+)\)", readme):
            target = raw.strip().split()[0].strip("<>")
            if not target or target.startswith(("#", "http:", "https:", "mailto:")):
                continue
            path = unquote(target.split("#", 1)[0]).replace("\\", "/")
            if path and path not in tracked:
                missing.append(path)

        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
