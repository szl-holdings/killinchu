# Corrected shared runtime mutation-boundary peer receipt

- Source repository: `szl-holdings/a11oy`
- Source candidate commit: `5c554a243364b6629a4c41a5d07d355241ac16d6`
- Source protected base: `58e79a74e672ee6594f9cc251e11f9aaf8f8c012`
- Source runtime-repair commit: `14fd6d96b0e353d8a71f470c02a4e57c5f5980eb`
- Killinchu base: `d66c1aa6316aff655a005b2ddd06c45c8e190286`
- Shared source files: `3` (two repaired modules plus their unchanged auth dependency)
- Payload manifest SHA-256: `3197110a3061ee92e5cf051a632a63aaf12255a03c751360488a4c084950ad28`
- Drift allowlist changed: `no`
- Branch protection weakened: `no`
- GitHub state changed: `no`

## Content addresses

| File | SHA-256 |
|---|---|
| `gdw_auth.py` | `c692593e02873f7b71b9a108fa42a9c2ae7f29d455596d9dd0a4236145297e89` |
| `szl_agentic_loop.py` | `84b29cbe7db8b8931afcf79c58d8b14f7457dee48c66cb906726dbeb65b74849` |
| `szl_immune.py` | `acd3cb1d72cd87e812c80ff25349268b9e46256a1ce4ddd017c28cf9c3805378` |

The three files are byte-identical to the named a11oy candidate. The copied
`szl_immune.py` is peer source evidence and is not mounted by Killinchu's
current `serve.py` or Dockerfile. `gdw_auth.py` is copied into the runtime image
because the protected agent-cycle boundary imports it on demand. This local
receipt does not claim a pull request, merge, deployment, or protected-main
qualification.
