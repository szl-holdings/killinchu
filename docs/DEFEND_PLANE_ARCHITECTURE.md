# Architecture

Killinchu composes the public Defend plane as a local module in the same FastAPI process. The former Sentra Space is not proxied or embedded. The private defensive-control-plane repository remains the source authority; the public port carries a fixed source revision and bounded contract.
