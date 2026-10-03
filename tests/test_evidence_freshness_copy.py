"""Keep the evidence reachability label aligned with its server freshness window."""

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_reachable_source_copy_matches_server_ttl():
    source = ast.parse((ROOT / "szl_evidence_research.py").read_text(encoding="utf-8"))
    ttl_assignments = [
        node
        for node in source.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_LIVENESS_TTL" for target in node.targets)
    ]
    assert len(ttl_assignments) == 1
    ttl_seconds = ast.literal_eval(ttl_assignments[0].value)
    assert isinstance(ttl_seconds, int) and ttl_seconds > 0

    console = (ROOT / "killinchu_elite_console.py").read_text(encoding="utf-8")
    labels = re.findall(r"last observed reachable \(within (\d+) min\)", console)
    assert len(labels) == 1
    assert int(labels[0]) * 60 == ttl_seconds
