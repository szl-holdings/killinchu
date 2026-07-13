import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_killinchu_public_contract_wiring",
    ROOT / "scripts" / "check_killinchu_public_contract_wiring.py",
)
CHECK = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(CHECK)


class ContractWiringTests(unittest.TestCase):
    def fixture(self, good: bool) -> pathlib.Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = pathlib.Path(temp.name)
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / "killinchu_public_contracts.py").write_text("# contract\n", encoding="utf-8")
        serve = (
            "import killinchu_public_contracts as _killinchu_public_contracts\n"
            '_killinchu_public_contracts.register(app, ns="killinchu")\n'
            'if __name__ == "__main__":\n    pass\n'
        )
        if not good:
            serve = 'if __name__ == "__main__":\n    pass\n'
        (root / "serve.py").write_text(serve, encoding="utf-8")
        (root / "Dockerfile").write_text("COPY killinchu_public_contracts.py ./\n", encoding="utf-8")
        (root / ".github" / "workflows" / "hf-sync.yml").write_text(
            "check_killinchu_public_contract_wiring.py\n"
            "check_killinchu_public_contracts.py\n"
            "post-deploy-contracts:\n",
            encoding="utf-8",
        )
        return root

    def test_good_wiring_passes(self):
        self.assertEqual(CHECK.evaluate(self.fixture(True)), [])

    def test_missing_fail_closed_registration_is_reported(self):
        errors = CHECK.evaluate(self.fixture(False))
        self.assertTrue(any("serve.py" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
