from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "static"


def test_brand_assets_are_packaged_and_served_as_css():
    app = FastAPI()
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    client = TestClient(app)

    for name in ("brand-tokens.css", "brand-bridge.css"):
        source = STATIC_DIR / name
        assert source.is_file(), f"missing packaged brand asset: {name}"

        response = client.get(f"/static/{name}")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/css")
        assert response.content == source.read_bytes()


def test_static_mount_precedes_the_spa_catch_all():
    source = (ROOT / "serve.py").read_text(encoding="utf-8")
    mount = 'app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")'
    catch_all = '@app.api_route("/{full_path:path}", methods=["GET", "HEAD"])'

    assert source.count(mount) == 1
    assert source.index(mount) < source.index(catch_all)
