from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "static" / "index.html"


class _DocumentContract(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def _document():
    source = INDEX.read_text(encoding="utf-8")
    parser = _DocumentContract()
    parser.feed(source)
    return source, parser.tags


def test_primary_landmark_and_skip_link_are_explicit():
    source, tags = _document()

    mains = [attrs for tag, attrs in tags if tag == "main"]
    assert mains == [{"id": "main-content", "tabindex": "-1"}]
    assert any(
        tag == "a"
        and attrs.get("class") == "kcd-skip"
        and attrs.get("href") == "#main-content"
        for tag, attrs in tags
    )
    assert 'aria-labelledby="kcd-title"' in source


def test_canonical_and_social_metadata_use_the_public_space_identity():
    _, tags = _document()
    links = [attrs for tag, attrs in tags if tag == "link"]
    metas = [attrs for tag, attrs in tags if tag == "meta"]
    canonical = "https://szlholdings-killinchu.hf.space/"
    social_image = canonical + "static/og-card.png"

    assert {"rel": "canonical", "href": canonical} in links
    assert any(meta.get("name") == "description" and len(meta.get("content", "")) > 120 for meta in metas)
    assert any(meta.get("property") == "og:title" and "Killinchu" in meta.get("content", "") for meta in metas)
    assert any(meta.get("property") == "og:url" and meta.get("content") == canonical for meta in metas)
    assert any(meta.get("property") == "og:image" and meta.get("content") == social_image for meta in metas)
    assert any(meta.get("property") == "og:image:alt" and meta.get("content") for meta in metas)
    assert any(meta.get("name") == "twitter:card" and meta.get("content") == "summary_large_image" for meta in metas)


def test_controls_expose_keyboard_focus_labels_and_reduced_motion():
    source, tags = _document()

    labels = {attrs.get("for") for tag, attrs in tags if tag == "label"}
    assert {"kcd-operator-token", "kcd-advisory-reason"} <= labels
    assert sum(1 for tag, attrs in tags if tag == "button" and attrs.get("type") == "button") == 3
    assert ':focus-visible' in source
    assert 'prefers-reduced-motion:reduce' in source
    assert 'role="button" aria-pressed=' in source
    assert 'ev.key==="Enter"||ev.key===" "' in source


def test_scope_copy_and_error_presentation_remain_truthful():
    source, _ = _document()

    for statement in (
        "Public demonstration",
        "Advisory-only; no actuation",
        "Developer repository",
        "For investors:",
        "For developers:",
    ):
        assert statement in source

    assert "function isDeckEntryPath()" in source
    assert '["/", "/killinchu", "/counter-uas"]' in source
    assert 'deck.setAttribute("hidden", "")' in source
    assert "HTTP status repair remains server-side" in source
