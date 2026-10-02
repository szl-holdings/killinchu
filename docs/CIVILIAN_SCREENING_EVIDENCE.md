# Civilian screening evidence boundary

Exact name comparison is advisory compliance evidence. It does not authorize
transactions, routing, detention, interdiction, or any operational action.

The loaded-list interface blocks negative conclusions when any loaded list is
empty or its local load timestamp is missing, malformed, future, or older than
six hours. A fresh miss is `NO_EXACT_MATCH`, never `CLEAR`. Local load time is
not the official publication time and loaded lists do not establish global
sanctions coverage.

The official-source interface requires both configured OFAC SDN and UN DPRK
sources to have fresh fetched timestamps, nonempty well-formed names, and
content hashes before returning `NO_EXACT_MATCH`. Stale, unavailable, empty,
malformed, or duplicate sources cannot establish full coverage. The hash
records retained content integrity; it is not independent source attestation.

Positive candidate matches remain visible even when coverage is incomplete,
with `POSSIBLE_MATCH` and mandatory manual review. Every result retains action
authority `NONE`. Coverage `FULL` refers only to the two configured lists.

Regression checks are hermetic and use synthetic names. They prove comparison
and admission behavior, not official-list completeness or runtime deployment.
