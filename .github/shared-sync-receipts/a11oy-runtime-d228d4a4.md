# Shared runtime mutation-boundary peer receipt

- Source repository: `szl-holdings/a11oy`
- Source candidate commit: `d228d4a4916a6e1bc965e5fbf4cd82e129f021a9`
- Source parent: `0505a41a5600c6d71ea3e2523bb6107c9fa5e18f`
- Killinchu base: `d66c1aa6316aff655a005b2ddd06c45c8e190286`
- Shared source files: `3` (two repaired modules plus their unchanged auth dependency)
- Payload manifest SHA-256: `281a5c552582fad44ede5b5a641f71bd7eda110bee8753a23802c75ad229540a`
- Drift allowlist changed: `no`
- Branch protection weakened: `no`
- GitHub state changed: `no`

## Content addresses

| File | SHA-256 |
|---|---|
| `gdw_auth.py` | `c692593e02873f7b71b9a108fa42a9c2ae7f29d455596d9dd0a4236145297e89` |
| `szl_agentic_loop.py` | `84b29cbe7db8b8931afcf79c58d8b14f7457dee48c66cb906726dbeb65b74849` |
| `szl_immune.py` | `f3a04234582b4982c8256e94d1e76aa84fed849ccf340b987809305ef4f23dee` |

The three files are byte-identical to the named a11oy candidate. The copied
`szl_immune.py` is peer source evidence and is not mounted by Killinchu's
current `serve.py` or Dockerfile. `gdw_auth.py` is copied into the runtime image
because the protected agent-cycle boundary imports it on demand. This local
receipt does not claim a pull request, merge, deployment, or protected-main
qualification.
