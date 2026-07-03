---
type: Concept
title: Cold brew
description: A long-steep, coarse-grind coffee immersion method that produces a concentrate
  diluted to taste, including the house's locked recipe, its extraction yield, and
  its counterintuitively high caffeine content.
resource: raw/cold-brew-notes.md
tags:
- coffee
- brewing
- cold-brew
- measurement
timestamp: '2026-07-02T21:23:33Z'
---

Cold brew is a long-immersion coffee method, distinct from hot [brewing](coffee-brewing.md): coarsely ground coffee steeps in room-temperature or refrigerated water for many hours to produce a concentrate, which is then diluted to taste rather than served at brew strength.[^s1][^s4] House R&D bench tests (Bench 3, immersion rig) measured each batch's [TDS](../abbreviations/tds-total-dissolved-solids.md) on a Hadley-Roe refractometer, calibrated weekly, using Cordwell Roastworks' medium-roast "Slow Tide" as the default test bean unless noted otherwise.[^s0]

The anchor ratio is 1:8 by weight, grounds to water, for the concentrate — e.g. 250 g of grounds to 2000 g of water in a small batch, scaled to 5 kg grounds and 40 kg water for a production batch.[^s1][^s4][^s11] The concentrate is then diluted to taste, typically 1:1 up to 1:3 (concentrate to water or milk) plus ice, with 1:8 as the anchor everything else works down from.[^s4] The house's locked default pours a 1:2 dilution.[^s19]

Grind size must be coarse — around 1100-1200 micron, burr set to 9.5 on the shop's grinder — because a finer grind produces fines that silt the cup and over-extract during the long steep.[^s1][^s2] A medium-coarse regrind test (burr 8) confirmed this: the concentrate went silty and slightly astringent at 16 hours, so the house reverted to 9.5 and treats coarse grind as non-negotiable for cold brew.[^s10]

Steep time runs 12-18 hours: shorter than 12 hours gives a thin, sour cup, and longer than 18 hours turns woody.[^s2] Temperature changes how fast that window is used up. A room-temperature (22 C) batch and a fridge (4 C) batch steeped for the same 14 hours showed the fridge batch extracting more slowly and reaching a lower concentrate TDS (3.6% vs. 4.0% for room temperature); to reach the same strength, a fridge batch needs about 18 hours where a room-temperature batch can stop around 14.[^s3] The two also taste different: fridge cold brew comes out cleaner and brighter, while room-temperature cold brew is rounder and has heavier body.[^s3] The house's locked spec keeps room temperature to 14-16 hours and gives fridge batches the full 18.[^s19]

A steep curve measured at room temperature (22 C, 1:8) tracked concentrate TDS from 3.1% at 10 hours up through 3.5% (12 h), 4.0% (14 h), 4.1% (16 h), and 4.2% (18 h) — the curve plateaus past roughly 16 hours, so pushing beyond 18 hours brings diminishing strength gains and a growing risk of a woody flavor.[^s18]

Source water quality also shapes the cup: raising the brewing water's own TDS from about 38 ppm to about 60 ppm (via a mineral sachet) raised concentrate TDS slightly, to 4.2%, and produced a sweeter, more defined cup while acidity stayed low; water that is too soft, below about 30 ppm, gives a flat, hollow cup.[^s1][^s9] The house's locked spec calls for mineral water around 60 ppm.[^s19]

Draw-off runs through a stainless-steel screen followed by a paper filter; the paper polish after the screen removes the fine silt and leaves the cup glassy clear, while relying on a nylon filter alone leaves more body but a cloudy cup with sediment at the bottom of the keg — house spec requires the screen-then-paper sequence and does not allow skipping the paper polish.[^s8][^s19]

[EY](../abbreviations/ey-extraction-yield.md) — the percentage of the dry grounds' mass that ends up dissolved in the beverage — is calculated as (TDS% x beverage mass) / dry grounds mass.[^s7] For a 14-hour room-temperature run, a 1820 g draw-off at 4.0% concentrate TDS from 250 g of grounds works out to an EY of about 29.1%, notably higher than the roughly 20% EY the same bean reaches under hot drip — the long steep draws out more total solubles without adding bitterness.[^s7]

Despite the common assumption that cold brew has less caffeine because it isn't hot-brewed, house bench tests found the opposite: because of cold brew's high grounds-to-water ratio (~1:8) and its 12-18 hour contact time, a 1:8 concentrate carries roughly 2.5 times the caffeine of a standard hot drip mug before dilution, so cold brew typically ends up with MORE total caffeine per gram of grounds used, not less — the belief that "cold means less caffeine" is a myth, since caffeine content tracks the concentrate ratio and steep time rather than brew temperature.[^s5] How much caffeine ends up in a finished glass still varies with how much a customer dilutes it; see [caffeine in coffee](caffeine-in-coffee.md) for how cold brew compares with other brewing methods.[^s5]

The bench notes also give a caffeine half-life figure for staff-facing menu cards — about three hours — which the [Caffeine](caffeine.md) page flags as inconsistent with a general survey's figure.[^s6] Either way, the shop's practical takeaway stays the same: a large afternoon cold brew lingers, so the recap card flags the "after 2pm" decaf upsell and tells staff not to sell the largest size after 3pm.[^s6][^s15]

Once brewed, sealed concentrate keeps in the fridge for about 10-14 days before acidity starts creeping up, while a diluted, ready-to-drink glass holds for only 2-3 days before its flavor drops off.[^s12] The best-selling serve is 1:1 concentrate to whole milk over ice, which carries the concentrate's body; oat milk works as an alternative, but almond milk comes out thin, so oat is the house's default alternative milk.[^s13]

Charging the same concentrate with nitrogen for a nitro tap pour gives a creamier mouthfeel and a perceived sweetness bump, with caffeine content unchanged and TDS identical (~4.0%) to the still version — nitro changes the drink's texture, not its extraction.[^s14]

As of the 2026-03-19 quarter close-out, the house's cold brew spec is locked: coarse grind (burr 9.5), a 1:8 concentrate ratio, steeped 14-16 hours at room temperature or 18 hours in the fridge, drawn off through a stainless-steel screen then a single paper filter, brewed with mineral water around 60 ppm, targeting a concentrate TDS of 4.0-4.2% and served diluted 1:2 by default.[^s19] The two talking points the bar is meant to lead with are that cold brew is both lower in acid and higher in total caffeine than hot drip — both true, and both considered sellable.[^s15][^s19]

## Open Points

### Cold brew stir-at-8h EY test
id: op-stir-at-8h-ey
- 2026-03-12: raised; does stirring the concentrate once at t=8 h lift EY without adding silt? test planned for the following week.[^s16]
- 2026-03-14: tested — a single gentle stir at t=8 h raised concentrate TDS to 4.3% versus a 4.0% control, with only a slight bump and no added astringency; adopted for batch runs only, since small-batch brewing isn't worth the extra labor.[^s17]

### Cold brew steep-time TDS curve
id: op-steep-time-tds-curve
- 2026-03-12: raised; plan to map concentrate TDS against steep hours (10/12/14/16/18) on a single curve.[^s16]
- 2026-03-17: curve measured at room temperature (22 C, 1:8): 3.1% at 10 h, 3.5% at 12 h, 4.0% at 14 h, 4.1% at 16 h, 4.2% at 18 h — the curve plateaus past roughly 16 h, with diminishing returns and rising woody-flavor risk beyond 18 h.[^s18]

### Decaf cold brew line
id: op-decaf-cold-brew-line
- 2026-03-12: raised; plan to test the same cold brew method on decaf beans and confirm low residual caffeine.[^s16]

## See also

- [Coffee brewing](coffee-brewing.md)
- [Coffee](coffee.md)
- [Caffeine in coffee](caffeine-in-coffee.md)
- [Caffeine](caffeine.md)
- [TDS — Total Dissolved Solids](../abbreviations/tds-total-dissolved-solids.md)
- [EY — Extraction Yield](../abbreviations/ey-extraction-yield.md)

## Sources

[^s0]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 3-4 — rig, refractometer, default test bean (ingested 2026-07-02)
[^s1]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 8-15 — first immersion pass (ingested 2026-07-02)
[^s2]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 17-19 — grind and steep-window note (ingested 2026-07-02)
[^s3]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 21-26 — room vs. fridge temp split test (ingested 2026-07-02)
[^s4]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 28-31 — ratio sanity check (ingested 2026-07-02)
[^s5]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 33-40 — caffeine content note (ingested 2026-07-02)
[^s6]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 42-44 — caffeine half-life note (ingested 2026-07-02)
[^s7]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 46-50 — extraction yield check (ingested 2026-07-02)
[^s8]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 52-55 — filter notes (ingested 2026-07-02)
[^s9]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 57-60 — water redo (ingested 2026-07-02)
[^s10]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 62-64 — grind regrind test (ingested 2026-07-02)
[^s11]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 66-69 — batch scale-up (ingested 2026-07-02)
[^s12]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 71-73 — shelf life (ingested 2026-07-02)
[^s13]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 75-77 — milk service (ingested 2026-07-02)
[^s14]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 79-81 — nitro tap A/B (ingested 2026-07-02)
[^s15]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 83-89 — staff recap card (ingested 2026-07-02)
[^s16]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 91-94 — open questions (ingested 2026-07-02)
[^s17]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 96-98 — stir test result (ingested 2026-07-02)
[^s18]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 100-106 — steep curve (ingested 2026-07-02)
[^s19]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 108-113 — quarter close-out, spec locked (ingested 2026-07-02)
