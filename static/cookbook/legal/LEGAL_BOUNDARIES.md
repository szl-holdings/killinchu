# Killinchu — Legal Boundaries

## WE SENSE. WE EVIDENCE. WE DO NOT JACK INTO THIRD-PARTY DRONES.

This document is the hard legal boundary for the Killinchu drone-intelligence product.
It is intentionally blunt: Killinchu is a **passive sensing and evidence** system, not an
offensive cyber or electronic-attack weapon.

---

## 1. What Killinchu does

- **Detects, classifies, and geolocates** uncrewed aircraft from the signals they emit:
  Remote ID (OpenDroneID / ASTM F3411), ADS-B (Mode-S 1090ES), MAVLink, RF emissions
  (including RF geolocation of **Remote-ID-OFF** "dark drones"), acoustic signatures, and
  EO/IR imagery.
- **Aggregates multi-constellation GEOINT** (HawkEye 360 RF, Planet/Maxar optical,
  Capella/ICEYE SAR, Spire space-based ADS-B) under each provider's lawful access model.
  Killinchu does not operate these satellites; it consumes their products.
- **Produces a Body-of-Evidence**: every detection, classification, and decision emits a
  Khipu DSSE receipt (real SHA-256 Merkle chain) so the customer's subsequent action is
  fully auditable.
- **Controls only the operator's OWN fleet** — signed OTA, parameter rollback, and
  forensic pull — and only behind a **2-person Yuyay-gate** with a 13-axis Λ check, each
  action Khipu-receipted.

## 2. What Killinchu does NOT do

- **No offensive cyber against third-party drones.** Killinchu will not exploit, hijack,
  command, brick, or exfiltrate from any drone that is not the operator's own fleet. The
  `control` / `ota` / `rollback` / `forensics` endpoints **refuse (HTTP 403)** any target
  whose `side` is not `allied` / `dual-use` / `counter-uas`.
- **No active jamming or spoofing from this product.** RF jamming and GNSS spoofing
  require **FCC and/or DoD authority**. Killinchu **detects** the adversary; the
  **authorized customer acts**.

## 3. Why — the controlling law

- **Computer Fraud and Abuse Act (CFAA), 18 U.S.C. §1030** — unauthorized access to a
  protected computer (a third-party drone's flight controller is a computer) is a federal
  crime. A commercial product must not facilitate it.
  <https://www.law.cornell.edu/uscode/text/18/1030>
- **ITAR (22 CFR 120–130)** — offensive cyber/electronic-attack capabilities are
  export-controlled defense articles; embedding them in a commercial product crosses into
  controlled-munitions territory.
  <https://www.ecfr.gov/current/title-22/chapter-I/subchapter-M>
- **Wassenaar Arrangement** — multilateral export controls on intrusion software and
  certain cyber tools.
  <https://www.wassenaar.org/>
- **FCC rules** — operating a jammer or intentional interferer is unlawful without specific
  federal authority.
  <https://www.fcc.gov/general/jammer-enforcement>

## 4. The division of responsibility

| Actor | May do | Killinchu's role |
| --- | --- | --- |
| **Killinchu (commercial product)** | Passive sense, classify, geolocate, evidence, OWN-fleet control | Deliver Body-of-Evidence Khipu receipts |
| **Customer (.mil / .gov with Title 10 / Title 50 authority)** | Jam, spoof, jack-in, kinetic engagement — under their lawful authority | Acts on the evidence; the receipts make their action auditable |

## 5. Why this is the right commercial position

This sense-and-evidence posture is the **SBIR / SCITT-aligned commercial sweet spot**:
- It is lawful for a commercial vendor to build and sell.
- It produces cryptographically auditable evidence (SCITT — Supply Chain Integrity,
  Transparency and Trust: <https://datatracker.ietf.org/wg/scitt/about/>).
- It cleanly hands the offensive decision — and its legal authority — to the customer who
  holds it.

## 6. Companion-defense protocol — explicit limits

When an adversary drone enters a configured radius of a protected companion/asset, the
protocol is:

1. **Auto-classify** (passive).
2. **Broadcast a legal RF warning beacon** (advisory, non-jamming).
3. **Notify the operator** (human-in-the-loop).
4. **ROE-gated response** — kinetic is **always** human-authorized; passive RF jamming is
   permitted **only where the deployment context is legally authorized** (FCC/DoD). Default
   posture is passive sense + evidence.

Every step emits a Khipu receipt.

---

© 2026 Lutar, Stephen P. — SZL Holdings · ORCID 0009-0001-0110-4173 · Apache-2.0 ·
Doctrine v11 · *Hatun-Willay*. Λ is a Conjecture, not a Theorem. Receipt signatures are
PLACEHOLDER (SLSA L1 honest; SLSA-Drone-L3 is the defined target, not yet attained).
