---
type: Registry
title: Fault-code catalogue — Aldervik yard
description: A catalogue of the 20 fault codes (rev. 4, 2025) used on work orders
  and machine logs across the Aldervik yard, one code deprecated in favor of another.
tags:
- fault-codes
- maintenance
- registry
- equipment
resource: raw/stoercode-katalog.md
timestamp: '2026-07-29T08:13:39Z'
citadel_version: 0.5.0
---

# Fault-code catalogue — Aldervik yard

This catalogue lists the 20 fault codes defined in revision 4 (2025) of the Werkhof fault-code
catalogue, used on all work orders and machine logs across the Aldervik yard; every fault entry
names the machine's register number together with exactly one code from this catalogue.[^s1] A
deprecated code stays listed so old work orders remain readable, but must not be used on new
entries.[^s1]

## 100 series — mechanical

- **E-101** — bearing damage — take the machine out of service, order a replacement
  bearing.[^s2]
- **E-102** — abnormal vibration — reduce load, schedule a vibration analysis.[^s3]
- **E-110** — shaft misalignment — realign, re-check after 48 h of operation.[^s4]
- **E-115** — belt or chain failure — replace the drive element, check tension.[^s5]
- **E-120** — lubrication failure — stop the machine, inspect the lubrication lines.[^s6]
- **E-142** — compressed-air pressure sensor fault — replace the sensor, recalibrate the
  control loop.[^s7]
- **E-155** — hydraulic seal leakage — deprecated since rev. 3 (2024); use E-310 on new
  entries.[^s8]
- **E-160** — structural crack found — take out of service immediately, notify the plant
  engineer.[^s9]

## 200 series — electrical

- **E-201** — motor overtemperature — check cooling and load, measure winding
  resistance.[^s10]
- **E-210** — frequency-converter fault — read out the converter log, reset once; replace on
  repeat.[^s11]
- **E-230** — control-voltage loss — check the control-circuit fuses and the 24 V
  supply.[^s12]
- **E-250** — emergency-stop circuit tripped — find and clear the cause before reset; log the
  reset.[^s13]

## 300 series — fluids

- **E-301** — coolant loss — locate the leak, top up, check the level switch.[^s14]
- **E-310** — hydraulic seal leakage — replace the seal, dispose of leaked oil per the waste
  plan.[^s15]
- **E-320** — compressed-air leakage — locate with leak spray, repair at the next
  standstill.[^s16]
- **E-350** — steam trap failure — replace the trap, check the condensate line.[^s17]

## 400 series — instrumentation

- **E-412** — coolant temperature sensor fault — replace the sensor, verify against a hand
  probe.[^s18]
- **E-420** — level transmitter fault — recalibrate; replace if drift exceeds 2 %.[^s19]
- **E-455** — flow meter drift — verify against the portable reference meter,
  recalibrate.[^s20]

## 500 series — safety

- **E-500** — guard or interlock fault — take out of service; restart requires the safety
  officer's sign-off.[^s21]

## See also

- [Machine registry — Aldervik yard](machine-registry-aldervik-yard.md)

## Sources

[^s1]: [raw/stoercode-katalog.md](../../raw/stoercode-katalog.md), lines 3-6 — catalogue scope, revision, and code count (ingested 2026-07-29)
[^s2]: [raw/stoercode-katalog.md](../../raw/stoercode-katalog.md), line 10 — E-101 (ingested 2026-07-29)
[^s3]: [raw/stoercode-katalog.md](../../raw/stoercode-katalog.md), line 11 — E-102 (ingested 2026-07-29)
[^s4]: [raw/stoercode-katalog.md](../../raw/stoercode-katalog.md), line 12 — E-110 (ingested 2026-07-29)
[^s5]: [raw/stoercode-katalog.md](../../raw/stoercode-katalog.md), line 13 — E-115 (ingested 2026-07-29)
[^s6]: [raw/stoercode-katalog.md](../../raw/stoercode-katalog.md), line 14 — E-120 (ingested 2026-07-29)
[^s7]: [raw/stoercode-katalog.md](../../raw/stoercode-katalog.md), line 15 — E-142 (ingested 2026-07-29)
[^s8]: [raw/stoercode-katalog.md](../../raw/stoercode-katalog.md), line 16 — E-155 (ingested 2026-07-29)
[^s9]: [raw/stoercode-katalog.md](../../raw/stoercode-katalog.md), line 17 — E-160 (ingested 2026-07-29)
[^s10]: [raw/stoercode-katalog.md](../../raw/stoercode-katalog.md), line 21 — E-201 (ingested 2026-07-29)
[^s11]: [raw/stoercode-katalog.md](../../raw/stoercode-katalog.md), line 22 — E-210 (ingested 2026-07-29)
[^s12]: [raw/stoercode-katalog.md](../../raw/stoercode-katalog.md), line 23 — E-230 (ingested 2026-07-29)
[^s13]: [raw/stoercode-katalog.md](../../raw/stoercode-katalog.md), line 24 — E-250 (ingested 2026-07-29)
[^s14]: [raw/stoercode-katalog.md](../../raw/stoercode-katalog.md), line 28 — E-301 (ingested 2026-07-29)
[^s15]: [raw/stoercode-katalog.md](../../raw/stoercode-katalog.md), line 29 — E-310 (ingested 2026-07-29)
[^s16]: [raw/stoercode-katalog.md](../../raw/stoercode-katalog.md), line 30 — E-320 (ingested 2026-07-29)
[^s17]: [raw/stoercode-katalog.md](../../raw/stoercode-katalog.md), line 31 — E-350 (ingested 2026-07-29)
[^s18]: [raw/stoercode-katalog.md](../../raw/stoercode-katalog.md), line 35 — E-412 (ingested 2026-07-29)
[^s19]: [raw/stoercode-katalog.md](../../raw/stoercode-katalog.md), line 36 — E-420 (ingested 2026-07-29)
[^s20]: [raw/stoercode-katalog.md](../../raw/stoercode-katalog.md), line 37 — E-455 (ingested 2026-07-29)
[^s21]: [raw/stoercode-katalog.md](../../raw/stoercode-katalog.md), lines 41-42 — E-500 (ingested 2026-07-29)
