# szl_formula_signatures.py — Typed DSPy-style Signatures for formula LLM calls
# Inspired by Stanford DSPy typed Signature pattern.
# Doctrine v11 LOCKED 749/14/163. SLSA L1 honest. Lift #6/10 LEADER_SCRAPE_60.
# Signed-off-by: Yachay <yachay@szlholdings.ai>
# Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class FormulaSignature:
    """Typed contract for an SZL formula LLM call (DSPy Signature pattern)."""
    name: str
    description: str
    inputs: dict[str, str]   # param_name -> type_hint
    outputs: dict[str, str]  # field_name -> type_hint
    doctrine_version: str = "v11"
    lambda_axis: str | None = None

# Canonical SZL formula signatures
FORMULA_SIGNATURES = {
    "LambdaGeomMean": FormulaSignature(
        name="LambdaGeomMean",
        description="13-axis Λ geometric mean (Conjecture 1, NOT a theorem)",
        inputs={"axes": "list[float]", "floor": "float"},
        outputs={"lambda": "float", "pass": "bool", "aggregate": "str"},
        lambda_axis="all",
    ),
    "KhipuEmit": FormulaSignature(
        name="KhipuEmit",
        description="Emit a Khipu DAG receipt (monotone count invariant INN-01)",
        inputs={"payload": "dict", "organ": "str", "prev_count": "int"},
        outputs={"receipt_hash": "str", "curr_count": "int", "monotone_check": "bool"},
        lambda_axis="attestation",
    ),
    "SLOBurnRate": FormulaSignature(
        name="SLOBurnRate",
        description="Honeycomb-lift: SLO budget burn rate (high-cardinality)",
        inputs={"error_rate": "float", "window_seconds": "int", "budget_seconds": "int"},
        outputs={"burn_rate": "float", "exhaustion_eta": "int", "alert": "bool"},
        lambda_axis="reliability",
    ),
}

def get_signature(name: str) -> FormulaSignature | None:
    return FORMULA_SIGNATURES.get(name)
