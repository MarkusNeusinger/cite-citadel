---
type: Registry
title: Sensor calibration offsets — Cinder Peak Observatory
description: The six observatory sensors with the calibration offset the instrument
  desk issued for each on 22 April 2026.
resource: raw/calibration-sheet.pdf
tags:
- calibration
- sensors
- observatory
timestamp: '2026-10-22T18:03:03Z'
citadel_version: 0.7.1
---

# Sensor calibration offsets — Cinder Peak Observatory

This registry covers the six sensors listed on the [Cinder Peak Observatory](../organizations/cinder-peak-observatory.md) instrument desk's Sensor Calibration Sheet, issued 22 April 2026 and checked by Ines Varga.[^s1][^s2] The offsets are read from the page image of the sheet's table (its text layer is garbled).[^s2] Each offset is subtracted from the sensor's raw reading before the value enters the nightly log.[^s3]

- **Dome Humidity Probe** — offset 0.12.[^s2]
- **Mirror Cell Thermistor** — offset 0.35.[^s2]
- **Primary Focus Encoder** — offset 0.08.[^s2]
- **Seeing Monitor Camera** — offset 0.21.[^s2]
- **Wind Mast Anemometer** — offset 0.47.[^s2]
- **Sky Quality Meter** — offset 0.16.[^s2]

## Validity

- The six sensors were checked against the instrument desk's reference set on 21 April 2026.[^s3]
- The sheet replaces every earlier calibration sheet for these sensors.[^s3]
- The next scheduled calibration is due in October 2026, or sooner if any sensor is moved or replaced.[^s3]

## See also

- [Cinder Peak Observatory](../organizations/cinder-peak-observatory.md)

## Sources

[^s1]: [raw/calibration-sheet.pdf](../../raw/calibration-sheet.pdf), lines 2-4 — title, issue date and checker (ingested 2026-10-22)
[^s2]: [raw/calibration-sheet.pdf](../../raw/calibration-sheet.pdf), p. 1 — sensor/offset table, read from the page image (ingested 2026-10-22)
[^s3]: [raw/calibration-sheet.pdf](../../raw/calibration-sheet.pdf), lines 19-24 — calibration notes (ingested 2026-10-22)
