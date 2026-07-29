# Werkhof fault-code catalogue (rev. 4, 2025)

Used on all work orders and machine logs across the Aldervik yard. Every fault entry names the
machine's register number and exactly one code from this catalogue. This revision defines
20 codes. A deprecated code stays listed so old work orders remain readable, but must not be
used on new entries.

## 100 series — mechanical

- E-101 — bearing damage — take the machine out of service, order a replacement bearing.
- E-102 — abnormal vibration — reduce load, schedule a vibration analysis.
- E-110 — shaft misalignment — realign, re-check after 48 h of operation.
- E-115 — belt or chain failure — replace the drive element, check tension.
- E-120 — lubrication failure — stop the machine, inspect the lubrication lines.
- E-142 — compressed-air pressure sensor fault — replace the sensor, recalibrate the control loop.
- E-155 — hydraulic seal leakage — deprecated since rev. 3 (2024); use E-310 on new entries.
- E-160 — structural crack found — take out of service immediately, notify the plant engineer.

## 200 series — electrical

- E-201 — motor overtemperature — check cooling and load, measure winding resistance.
- E-210 — frequency-converter fault — read out the converter log, reset once; replace on repeat.
- E-230 — control-voltage loss — check the control-circuit fuses and the 24 V supply.
- E-250 — emergency-stop circuit tripped — find and clear the cause before reset; log the reset.

## 300 series — fluids

- E-301 — coolant loss — locate the leak, top up, check the level switch.
- E-310 — hydraulic seal leakage — replace the seal, dispose of leaked oil per the waste plan.
- E-320 — compressed-air leakage — locate with leak spray, repair at the next standstill.
- E-350 — steam trap failure — replace the trap, check the condensate line.

## 400 series — instrumentation

- E-412 — coolant temperature sensor fault — replace the sensor, verify against a hand probe.
- E-420 — level transmitter fault — recalibrate; replace if drift exceeds 2 %.
- E-455 — flow meter drift — verify against the portable reference meter, recalibrate.

## 500 series — safety

- E-500 — guard or interlock fault — take out of service; restart requires the safety officer's
  sign-off.
