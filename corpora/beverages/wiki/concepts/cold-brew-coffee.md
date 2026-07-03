---
type: Concept
title: Cold Brew Coffee
description: An immersion brewing method — coarse grounds steeped 12-18 hours in room-temperature
  or cold water at a concentrated ratio, then diluted to taste — yielding a smoother,
  lower-acid, higher-caffeine cup than hot brewing.
tags:
- coffee
- brewing
- cold-brew
- measurement
resource: raw/cold-brew-notes.md
timestamp: '2026-07-03T22:29:14Z'
---

Cold brew is an immersion method: rather than passing hot water through the grounds quickly, coarsely ground coffee steeps in room-temperature or refrigerated water for an extended period before being drawn off.[^s3] Bench trials default to [Cordwell Roastworks](../organizations/cordwell-roastworks.md)' medium-roast [Slow Tide](../objects/slow-tide.md) as the house bean unless otherwise noted, with strength measured on the bench's Hadley-Roe refractometer, calibrated weekly, as Total Dissolved Solids ([TDS](../abbreviations/tds-total-dissolved-solids.md)).[^s1]

The grind is kept coarse — about 1,100 to 1,200 microns, described as "sea-salt-ish," dialled in at burr setting 9.5 on the bench's Vossberg grinder — because finer grinds turn silty and over-extract over the course of the long steep.[^s2][^s3] A later attempt at a medium-coarse grind (burr setting 8, versus the usual 9.5) came out silty and slightly astringent at 16 hours, confirming that the coarser setting is non-negotiable for a long steep.[^s11] The concentrate is brewed at roughly a 1:8 ratio of grounds to water by weight (for example 250 g of grounds to 2,000 g of water), which serves as the anchor figure; the finished concentrate is then diluted to taste, typically from 1:1 up to 1:3 with water or milk over ice.[^s2][^s5]

The working steep window is 12 to 18 hours: under 12 hours the cup comes out thin and sour, and past 18 hours it turns woody.[^s3][^s21] Temperature changes the pace of extraction: at a 14-hour steep, room temperature (about 22 C) reaches a concentrate TDS of 4.0%, while the fridge (about 4 C) reaches only 3.6%, so a fridge steep needs to run closer to 18 hours to match what a room-temperature steep achieves in about 14; fridge steeps also taste cleaner and brighter, while room-temperature steeps come out rounder and heavier-bodied.[^s4]

After steeping, the concentrate is drawn off through a stainless-steel screen and then polished through a single paper filter; skipping the paper stage in favor of the screen alone leaves the cup cloudier, heavier-bodied, and prone to sediment at the bottom of the keg, while the paper stage clears the cup of silt entirely.[^s9] Source water also matters: too-soft water, under about 30 ppm of dissolved minerals, produces a flat, hollow cup, while raising the water's mineral content to about 60 ppm sharpens sweetness and definition without adding acidity.[^s10]

Counterintuitively, cold brew often ends up carrying more total [caffeine](caffeine.md) than hot drip coffee — the popular belief that cold brewing means less caffeine is a myth. The effect comes from the concentrate's very high grounds-to-water ratio (about 1:8) combined with the long 12-to-18-hour steep, which together pull far more caffeine per gram of grounds than a quick hot brew, even though the finished glass is diluted afterward and so varies in strength; bench notes cite an internal figure of roughly 2.5 times the caffeine of a standard hot-drip mug for a 1:8 concentrate before dilution.[^s6] The same notes put caffeine's half-life in the body at about 3 hours, used as the basis for flagging a decaf upsell on cold brew orders after 2 p.m. — see [Caffeine](caffeine.md) for how this compares with the commonly cited figure.[^s7]

[Caffe Aurora](../organizations/caffe-aurora.md) markets its own cold brew differently, calling it the lowest-caffeine drink on its menu and stating that brewing cold pulls out far less caffeine than hot water ever could — the cup it recommends to customers who want the flavor without the buzz.[^s20] See [Caffeine](caffeine.md) for how this claim compares with the established view on cold brew's caffeine content above.

[Extraction yield](../abbreviations/ey-extraction-yield.md) (EY) — the percentage of the dry grounds' mass that ends up dissolved in the cup — is calculated as (TDS% × beverage mass) ÷ dry grounds mass.[^s8] Applied to a 14-hour room-temperature run (4.0% concentrate TDS, 1,820 g of draw-off from 250 g of grounds), this gives an EY of about 29.1%; despite running higher than the roughly 20% EY typical of hot drip on the same bean, the long, gentle steep reaches that extraction without added bitterness.[^s8]

The recipe scales linearly: a batch of 5 kg grounds to 40 kg water (still 1:8), steeped 18 hours at room temperature in a cooler kitchen (about 19 C), reached a concentrate TDS of 4.0% — consistent with small-batch results — and yielded about 36 L of concentrate off the press.[^s12]

Shelf life differs sharply between the concentrate and the finished drink: sealed and refrigerated, the concentrate holds for about 10 to 14 days before its acidity starts to creep up, while a diluted, ready-to-drink glass keeps for only 2 to 3 days before its flavor drops off.[^s13]

For milk service, a 1:1 ratio of concentrate to whole milk over ice is the best-selling combination, with the milk's body carrying the drink; oat milk works well as a dairy-free alternative, while almond milk turns thin, so oat is specified as the default alternative.[^s14] Charging the same concentrate with nitrogen (a nitro tap) leaves the TDS unchanged at about 4.0% but produces a creamier mouthfeel and a perceived increase in sweetness — a texture effect rather than a change in extraction, and caffeine content is unaffected.[^s15]

The house cold brew spec was locked at the close of the quarter: coarse grind (burr setting 9.5), a 1:8 ratio, steeped 14 to 16 hours at room temperature or 18 hours in the fridge, drawn off through a stainless-steel screen and paper filter, brewed with mineral water around 60 ppm, targeting a concentrate TDS of 4.0-4.2%, and served diluted 1:2 by default.[^s16] The house sums up its pitch in two claims: cold brew is smoother and less acidic than hot coffee, yet carries more total caffeine — both held to be true, and both used to sell it.[^s16]

## Open Points

### 8-Hour Stir Test
id: op-8-hour-stir-test
- 2026-03-12: raised; testing planned for whether a single stir at t=8 h into the steep lifts extraction yield without adding silt to the cup.[^s17]
- 2026-03-14: resolved; a single gentle stir at t=8 h raised concentrate TDS to 4.3% against a 4.0% unstirred control, with only a slight bump and no added astringency; adopted for batch-size brews only, since the extra labor isn't worth it for small batches.[^s18]

### Steep-Time TDS Curve
id: op-steep-time-tds-curve
- 2026-03-12: raised; plan to map concentrate TDS against steep time at 10, 12, 14, 16, and 18 hours on a single curve.[^s17]
- 2026-03-17: resolved; at room temperature and a 1:8 ratio, concentrate TDS came in at 3.1% (10 h), 3.5% (12 h), 4.0% (14 h), 4.1% (16 h), and 4.2% (18 h) — the curve plateaus past roughly 16 hours, with diminishing returns and a rising risk of woody flavor beyond 18 hours.[^s19]

### Decaf Cold Brew Line
id: op-decaf-cold-brew-line
- 2026-03-12: raised; plan to run the same cold brew method on decaf beans and confirm the residual caffeine stays low; still open as of this source.[^s17]

## See also
- [Coffee Brewing](coffee-brewing.md)
- [Coffee](../objects/coffee.md)
- [Caffeine](caffeine.md)
- [Coffee and Health](coffee-and-health.md)
- [TDS — Total Dissolved Solids](../abbreviations/tds-total-dissolved-solids.md)
- [EY — Extraction Yield](../abbreviations/ey-extraction-yield.md)
- [Cordwell Roastworks](../organizations/cordwell-roastworks.md)
- [Slow Tide](../objects/slow-tide.md)
- [Caffe Aurora](../organizations/caffe-aurora.md)

## Sources
[^s1]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 3-4 — bench rig and default house bean (ingested 2026-07-03)
[^s2]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 9-10 — first-pass grind and ratio (ingested 2026-07-03)
[^s3]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 18-19 — grind rationale and steep window (ingested 2026-07-03)
[^s4]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 21-26 — room vs. fridge temperature split test (ingested 2026-07-03)
[^s5]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 28-31 — ratio sanity and serve dilution (ingested 2026-07-03)
[^s6]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 33-40 — caffeine vs. hot drip (ingested 2026-07-03)
[^s7]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 42-44 — caffeine half-life note (ingested 2026-07-03)
[^s8]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 46-50 — extraction yield formula and worked example (ingested 2026-07-03)
[^s9]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 52-55 — filter notes (ingested 2026-07-03)
[^s10]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 57-60 — water mineral content (ingested 2026-07-03)
[^s11]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 62-64 — grind regrind test (ingested 2026-07-03)
[^s12]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 66-69 — batch scale-up (ingested 2026-07-03)
[^s13]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 71-73 — shelf life (ingested 2026-07-03)
[^s14]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 75-77 — milk service (ingested 2026-07-03)
[^s15]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 79-81 — nitro tap A/B (ingested 2026-07-03)
[^s16]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 108-113 — locked house spec (ingested 2026-07-03)
[^s17]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 91-94 — open questions (ingested 2026-07-03)
[^s18]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 96-98 — stir test result (ingested 2026-07-03)
[^s19]: [raw/cold-brew-notes.md](../../raw/cold-brew-notes.md), lines 100-106 — steep-time TDS curve (ingested 2026-07-03)
[^s20]: [raw/aurora-bulletin-2026.md](../../raw/aurora-bulletin-2026.md), § The Aurora nerd corner — how we brew it now — cold brew caffeine claim (ingested 2026-07-03)
[^s21]: [raw/brewing-science-notes.md](../../raw/brewing-science-notes.md), § Grind, time, and temperature — the three levers you actually turn — corroborates cold brew's very coarse grind and 12-18 hour steep (ingested 2026-07-03)
