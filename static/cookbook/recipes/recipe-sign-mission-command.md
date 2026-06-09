# DSSE-sign a drone command + verify cross-organ

**Recipe ID:** `recipe-sign-mission-command`  
**Tags:** wire-d, dsse, signing, cross-organ  
**Doctrine v11 — 749/14/163**  
**Maintained by:** Yachay <yachay@szlholdings.dev>  
*ORCID 0009-0001-0110-4173*

## Intent
Sign any own-fleet mission command with the live Wire-D ECDSA-P256 DSSE signer and verify it from another role (e.g. the Operator or Policy role — retired internal codenames `rosie`/`sentra` — whose capability lives inside a11oy).

## Steps
1. Build the command object {drone_id, command, params, ts_utc, operator}.
2. POST /khipu/sign (or /api/killinchu/khipu/sign) -> DSSE envelope {payload(b64), signatures:[{sig,keyid:szlholdings-cosign}], _pae_sha256}.
3. Cross-organ: POST /khipu/verify with the envelope -> {signed:true, keyid_expected:szlholdings-cosign, verify_key_url}.
4. GET /khipu/pubkey to fetch the public key fingerprint for offline verification.
5. Own-fleet ONLY (control endpoints 403 any non-allied side). Attach disclaimer.

## Live endpoints driven
- `/khipu/sign`
- `/khipu/verify`
- `/khipu/pubkey`
- `/api/killinchu/v1/wires/D`

## Sources
- https://github.com/secure-systems-lab/dsse
- https://docs.sigstore.dev/

## LEGAL BOUNDARIES (drone-domain action)

> WE SENSE. WE EVIDENCE. WE DO NOT JACK INTO THIRD-PARTY DRONES. Killinchu is a passive sensing + evidence system. Offensive cyber, jamming, GNSS spoofing, and kinetic action are the lawful customer's responsibility under their Title 10/Title 50 authority (CFAA 18 USC 1030, ITAR 22 CFR 120-130, Wassenaar, FCC). Own-fleet control only, behind a 2-person Yuyay-gate. See /api/killinchu/v2/legal.

---
Apache-2.0 · © 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173
