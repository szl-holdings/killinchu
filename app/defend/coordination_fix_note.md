"""Fix: truce resolution clears the conflict slate.

Without this, the first action after a human resolves a truce instantly
re-freezes the scope, because the prior agent's action still sits inside
the conflict window. Resolution is the human declaring the dispute over —
the slate clears with it. Implemented in `ConflictDetector.resolve_truce`
via `self._recent.pop(scope, None)`.
"""