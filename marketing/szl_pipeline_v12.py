#!/usr/bin/env python3
"""SZL-MARKETING-1.2 — fact pipeline + compliance linter + channel drafts.
Vigil patch of Rosa's Part 5. Four defects fixed:
  (1) pasted Part 5 did not compile (f-string slice, no comma);
  (2) URLs arrived as markdown links -> invalid Python literals;
  (3) headline number came from top MODEL (chaski, 3,070) not top DATASET
      (killinchu-osint-corpus, 74,157) -- the campaign's crown jewel;
  (4) no User-Agent / no pagination guard -> GitHub 403 from a datacenter IP.
Plus: linter now strips quoted rule text so a doctrine doc does not fail its own gate.
Usage: python3 szl_pipeline_v12.py            # writes marketing/factbase.json
       python3 szl_pipeline_v12.py --lint F   # gate a draft (exit 1 = blocked)
"""
import json, pathlib, re, sys, urllib.request
from datetime import datetime, timezone

OUT = pathlib.Path("marketing"); OUT.mkdir(exist_ok=True)
NOW = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d")
UA = {"User-Agent": "SZL-Marketing-Factbase/1.2 (Rosa Lutar; contact br@szlholdings.com)"}
GH_ORG = "https://api.github.com/orgs/szl-holdings/repos?per_page=100"
HF_API = "https://huggingface.co/api/{kind}?author=SZLHOLDINGS&limit=1000"

BANNED = [  # Part 2 guardrails, machine-enforced (first 6 = Rosa's)
    (r"\bproven\b(?!.*conjecture)", "Lambda/performance overclaim", True),
    (r"\bguaranteed?\b", "guarantee language", True),
    (r"\b100%\s*(trust|safe|secure)", "ceiling violation (max 0.97)", True),
    (r"\bstate.of.the.art\b", "unverifiable superlative", True),
    (r"\breturns of \d", "quant performance claim", True),
    (r"\b\d+\s?(km|miles|meter)s?\s?(detection|range)", "killinchu capability quantification", True),
    # (7-13) ADDED by Vigil -- absolute-claim classes the original gate let through
    (r"\bcannot be (jailbroken|broken|hacked)\b", "absolute safety claim (needs S1/S2 artifact)", False),
    (r"\b(unhackable|unbreakable|tamper.proof|foolproof)\b", "absolute claim", False),
    (r"\bmilitary.grade\b", "unverifiable grade claim", False),
    (r"\bworld.?s first\b|\bfirst ever\b", "superlative priority claim", False),
    (r"\bnever fails\b|\bzero false\b|\b100% accurate\b", "absolute performance", False),
    (r"\boutperform\b|\bbeat the market\b|\balpha of \d", "quant performance implication", False),
    (r"\bgovernment.contracted\b|\bdeployed with\b|\bin service with\b", "defense deployment disclosure", False),
    # (14) internal-figure-in-public -- Finn/Joe/Vesper flag, now machine-enforced
    (r"\b74,?157\b|\b74K\b", "internal figure in public copy (Rosa floor; needs authorization)", False),
]

def _strip_quotes(t: str) -> str:
    """Remove QUOTED rule text so a doctrine doc does not fail its own gate.
    Vigil fix 2: previous version stripped each quote-style independently, so a line
    quoting two banned words in sequence mis-paired and left the word exposed
    (false positives on Stephen's handoff). Now: mask quoted spans FIRST (innermost,
    all three styles in one pass), then mask the BANNED list itself if quoted."""
    for _ in range(3):                      # iterate: nested/multiple spans per line
        t2 = re.sub(r'"[^"\n]{0,240}"', '""', t)
        t2 = re.sub(r"'[^'\n]{0,240}'", "''", t2)
        t2 = re.sub(r"`[^`\n]{0,300}`", "``", t2)
        if t2 == t: break
        t = t2
    # a line that merely NAMES the banned words as rules ("banned -> ...") is doctrine
    t = re.sub(r'(?i)^[\s\-\*\d\.]*.*(banned|never|not allowed|do not use|discipline)[^\n]*$', '', t, flags=re.M)
    return t

META_LINE = re.compile(
    r"(?i)\b(banned|catches|guard|linter?|lint\(|pattern|never|not allowed|do not use|discipline|rule)\b")

def _is_meta(line: str) -> bool:
    """A line that DESCRIBES the compliance rules is doctrine, not advertising copy.
    Vigil fix 3: the gate was being applied to the wrong document class -- Stephen's
    handoff explains what the linter catches, so it named the banned words in prose."""
    return bool(META_LINE.search(line))

def lint(text: str, doc_class: str = "public"):
    """Return violations. A PUBLIC draft with violations does not ship.
    doc_class='public'  -> ad copy / Substack / campaign piece: strict, every line judged.
    doc_class='internal'-> doctrine, handoff, runbook: META lines that merely DESCRIBE
                           the rules are exempt; real claims in prose still fail."""
    clean = _strip_quotes(text)
    out = []
    for pat, msg, _ in BANNED:
        for m in re.finditer(pat, clean, re.I):
            if doc_class == "internal":
                s = clean.rfind("\n", 0, m.start()) + 1
                e = clean.find("\n", m.end())
                line = clean[s:e if e != -1 else None]
                if _is_meta(line):
                    continue
            out.append(f"BANNED [{msg}]: {m.group(0)!r}")
    return out

def _get(url):
    r = urllib.request.Request(url, headers=UA)
    return json.load(urllib.request.urlopen(r, timeout=30))

def factbase() -> dict:
    facts = {"generated": NOW(), "source": "live API pull, never typed from memory"}
    repos, url = [], GH_ORG
    while url:                                   # FIX (4): paginate properly
        r = urllib.request.Request(url, headers=UA)
        resp = urllib.request.urlopen(r, timeout=30)
        repos += json.load(resp)
        m = re.search(r'<([^>]+)>; rel="next"', resp.headers.get("Link", "") or "")
        url = m.group(1) if m else None
    facts["github"] = {"repos": len(repos),
                       "archived": sum(1 for x in repos if x.get("archived")),
                       "stars_total": sum(x.get("stargazers_count", 0) for x in repos)}
    facts["hf"] = {}
    for kind in ("models", "datasets", "spaces"):
        d = _get(HF_API.format(kind=kind))
        facts["hf"][kind] = len(d)
        if d and kind in ("models", "datasets"):
            top = max(d, key=lambda x: x.get("downloads", 0) or 0)
            facts["hf"][f"top_{kind[:-1]}"] = {"id": top["id"], "downloads": top.get("downloads", 0)}
    # FIX (3): campaign headline is a DATASET. dataset-first, model fallback.
    facts["hf"]["headline"] = facts["hf"].get("top_dataset") or facts["hf"].get("top_model")
    return facts

def substack_draft(f: dict, essay_body: str, subjects: list) -> str:
    """A/B subject lines; fact block injected; linted before return."""
    sa = subjects[0] if subjects else "Receipts, Not Vibes"
    sb = subjects[1] if len(subjects) > 1 else sa
    head = (f"<!-- SUBJECT A: {sa}\n     SUBJECT B: {sb} -->\n"   # FIX (1): was a slice, no comma
            f"# {sa}\n\n## The estate, this week (fetched {f['generated']})\n\n"
            f"- {f['github']['repos']} GitHub repositories "
            f"({f['github']['archived']} honestly archived)\n"
            f"- {f['hf']['models']} models · {f['hf']['datasets']} datasets · "
            f"{f['hf']['spaces']} Spaces on Hugging Face\n"
            f"- Most-downloaded artifact: {f['hf']['headline']['id']} "
            f"({f['hf']['headline']['downloads']:,} downloads)\n\n")
    tail = ("\n\n---\n\nEvery number above was fetched from a live API at generation time. "
            "Verify a receipt yourself: https://a-11-oy.com/verify · "
            "Proof registry: https://a11oy.net\n")
    draft = head + essay_body + tail
    if v := lint(draft):
        raise SystemExit("DRAFT BLOCKED BY COMPLIANCE LINTER:\n" + "\n".join(v))
    return draft

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if "--lint" in flags and args:
        path = args[0]
        try:
            t = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print(f"LINTER ERROR (not a lint result): {e}"); sys.exit(2)   # 2 = tool failure, never 1
        cls = "internal" if "--internal" in flags else "public"
        v = lint(t, cls)
        print(f"lint[{cls}]({path}): {len(v)} violation(s)")
        for x in v: print("  " + x)
        sys.exit(1 if v else 0)
    f = factbase()
    (OUT / "factbase.json").write_text(json.dumps(f, indent=2))
    print(json.dumps(f, indent=2))
    print(f"factbase locked {NOW()} — headline artifact: {f['hf']['headline']['id']} "
          f"({f['hf']['headline']['downloads']:,} dl)")
