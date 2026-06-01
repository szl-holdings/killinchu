# Killinchu — Quantum Sensing Roadmap (Honest Scope)

**Vertical:** killinchu (Andean drone-intelligence counter-UAS rule engine)
**Doctrine:** v11 LOCKED (749/14/163) · **License:** Apache-2.0
**Author:** Yachay \<yachay@szlholdings.dev\>
**Status:** Forward-looking roadmap. **Not** a current capability.

---

## 1. Honest scope

> **Quantum sensing is research-grade.** SZL killinchu's production sensing is
> **classical**: Remote-ID, ADS-B, and MAVLink ingest feed the Yuyay-13 gate and
> the Wire D signing chain. Quantum sensing is a **2027+ roadmap item dependent
> on hardware partnerships.** Nothing below is deployed in killinchu today.

The most mature near-term quantum-sensing application relevant to the air domain
is **GPS-denied navigation** via quantum magnetometry — not "quantum radar."
Quantum radar remains a research topic with **no field-deployed system**.

## 2. Technology landscape (with honest maturity)

| Technology | Maturity | Counter-UAS relevance |
|---|---|---|
| **Quantum magnetometers** (NV-diamond, atomic-vapor / SERF) | Lab → early field trials | GPS-denied PNT for interceptor/sensor platforms; magnetic-anomaly detection |
| **Quantum radar** (quantum illumination) | Research only — **no fielded system** | Theoretical low-power stealth detection; not on roadmap |
| **Quantum LiDAR / single-photon detection** | Research + early photonics | Long-range low-signature ranging |
| **Quantum inertial / gravimetry** | Early field trials | Drift-free inertial navigation in GPS-denied ops |

NV-center magnetometers are durable, compact, and being tested for GPS-denied
navigation in aircraft and drones, comparing measured crustal magnetic fields to
magnetic maps ([NIST, "Sensors for a Magnetic World"](https://www.nist.gov/quantum-information-science/quantum-sensing-explained/sensors-magnetic-world)).

## 3. Active research labs (5)

1. **DARPA** — Robust Quantum Sensors (RoQS) and QuSeN programs, moving quantum
   sensors onto defense platforms ([DARPA, "Quantum sensors out of the lab," 2025](https://www.darpa.mil/news/2025/quantum-sensors-defense-platforms); [DARPA QuSeN](https://www.darpa.mil/research/programs/qusen)).
2. **AFRL** (Air Force Research Laboratory) — quantum sensing / PNT for
   GPS-denied air operations.
3. **DTRA** (Defense Threat Reduction Agency) — quantum sensing for
   threat-detection use cases.
4. **NIST** — chip-scale atomic magnetometers (John Kitching group) and the
   Quantum Information Science program ([NIST chip-scale atomic magnetometers](https://www.nist.gov/noac/technology/magnetic-and-electric-fields/chip-scale-atomic-magnetometers)).
5. **NASA JPL** — optically-pumped solid-state quantum magnetometers ([JPL postdoc program PDF](https://postdocs.jpl.nasa.gov/media/Andreas_Gottscholl.pdf)).

## 4. Commercial firms (3)

1. **Q-CTRL** — field-validated quantum-assured navigation (Ironstone Opal);
   awarded DARPA RoQS contracts (~$24.4M, 2025) ([Q-CTRL quantum sensing](https://q-ctrl.com/our-work/quantum-sensing)).
2. **Quantum Brilliance** — navigation-grade NV-diamond quantum magnetometers
   targeting UAS/drones and autonomous platforms ([Quantum Brilliance quantum sensing](https://quantumbrilliance.com/quantum-sensing/)).
3. **Zapata-class quantum software / sensing integrators** — quantum software and
   analytics partners for sensor-data processing (representative of the
   commercial integration layer).

## 5. The SZL architectural hook

Killinchu's sensor input is **decoupled** from the governance core through a
`SensorAdapter` interface:

```
[ SensorAdapter ]  →  [ Yuyay-13 gate ]  →  [ Wire D DSSE signing ]  →  [ Khipu chain ]
   (classical today)        (unchanged)            (unchanged)              (unchanged)
```

When quantum sensing matures, killinchu **drops in a new `SensorAdapter`** (e.g.,
an NV-diamond magnetometer feed for GPS-denied geolocation) and the Yuyay-13
gate and Wire D signing chain stay **unchanged**. Sensor evolution does not touch
the provenance core; every quantum-derived measurement is still gated, signed,
and chained exactly like a classical Remote-ID frame.

## 6. Disclaimers

- **Quantum radar exists in research only; no field-deployed system; not on the
  SZL roadmap.**
- Quantum magnetometry for GPS-denied navigation is the most credible near-term
  item but is still in field-trial stage at partners like Q-CTRL.
- All adoption is **partnership-dependent** and targeted no earlier than 2027.
- Citing these labs/firms is **not** a claim of partnership; they are referenced
  as the credible research/commercial landscape.

---

*Doctrine v11 LOCKED (749/14/163) · Apache-2.0 · Signed-off-by: Yachay \<yachay@szlholdings.dev\>*
