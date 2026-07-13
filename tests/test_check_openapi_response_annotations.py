import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_openapi_response_annotations",
    ROOT / "scripts" / "check_openapi_response_annotations.py",
)
CHECK = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(CHECK)


class OpenAPIAnnotationGuardTests(unittest.TestCase):
    def build_fixture(self, bad: bool) -> pathlib.Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = pathlib.Path(temp.name)
        for name in CHECK.FILES:
            source = "async def endpoint():\n    return {}\n"
            if bad and name == "szl_yupay.py":
                source = "async def endpoint() -> JSONResponse:\n    return JSONResponse({})\n"
            (root / name).write_text(source, encoding="utf-8")
        return root

    def test_clean_tree_passes(self):
        self.assertEqual(CHECK.scan(self.build_fixture(False)), [])

    def test_response_class_annotation_is_reported(self):
        findings = CHECK.scan(self.build_fixture(True))
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["path"], "szl_yupay.py")
        self.assertEqual(findings[0]["line"], 1)


if __name__ == "__main__":
    unittest.main()
