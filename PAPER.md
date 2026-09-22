# Did DRS Increase Overtaking?

### Separating a regulation from the confound it arrived with

**Mahyar Sharafi Laleh** | September 2026
Code and data: [`github.com/Moonyar/f1-drs-overtaking`](https://github.com/Moonyar/f1-drs-overtaking) | Repository README: [`README.md`](README.md)

---

## Abstract

Formula 1 introduced the Drag Reduction System (DRS) in 2011, and overtaking roughly
doubled that season, from 15.0 to 30.7 passes per race. The obvious inference is that
DRS caused it. This paper argues that the obvious inference cannot be drawn from
season-level data, because the 2011 season also introduced Pirelli high-degradation
tyres, and at the season level the two regulations are perfectly collinear.

I exploit a difference in the *geometry* of the two treatments. The tyre change applied
uniformly to every circuit; DRS did not, because zone counts varied by track and changed
over time. A panel with both circuit and year fixed effects therefore absorbs the tyre
change entirely while leaving DRS identified off differential zone exposure.

The estimated effect of one additional DRS zone is **+1.51 overtakes per race (95% CI
-4.11 to +7.13, p = 0.60, n = 377)**, indistinguishable from zero and not stable in sign
across robustness checks. The minimum detectable effect at 80% power is 8.03, so this is
an underpowered null rather than evidence of no effect.

The useful result is a different one. If DRS alone caused the 2011 jump, the per-zone
effect would have to be +13.8, which lies above the confidence interval's upper bound and
well inside the range the design can detect. **DRS as the sole cause of the 2011 increase
in overtaking is ruled out at the 5% level.** The tyre regulation must carry most of it.

---

## 1. Motivation

The 2011 Formula 1 season produced the largest single-year increase in overtaking in the
sport's modern history. The popular explanation, then and now, is DRS: a driver-activated
rear-wing flap that reduces drag on designated straights when following within one second
of the car ahead. The mechanism is plausible and the timing is exact.

It is also the kind of claim that is easy to assert and hard to establish. Three things
make it a genuine causal inference problem rather than a charting exercise:

1. **The treatment is confounded by design.** Both regulations were introduced together,
   deliberately, as a package intended to increase overtaking.
2. **The outcome is not observed, it is constructed.** Formula 1 publishes no overtake
   count. Any number depends on a definition the analyst chooses, and the definition
   drives the result.
3. **Treatment assignment is not random.** The FIA placed DRS zones where overtaking was
   already difficult, which is the textbook shape of endogenous treatment.


---

## 2. Background: what changed in 2011

**DRS.** From 2011, drivers could open a rear-wing flap on designated straights when
within one second of the car ahead at a detection point. Circuits were assigned between
one and three zones. Monaco and Suzuka ran a single zone for most of the period; Bahrain
and the Red Bull Ring ran three. Zone counts changed at 17 of the 30 circuits in the
post-2011 panel.

**Pirelli tyres.** Also from 2011, Pirelli replaced Bridgestone as sole supplier under an
explicit brief to produce tyres that degrade quickly, forcing additional pit stops and
creating pace differentials between cars on different tyre ages. This was, by design, an
overtaking intervention.

These two facts are the whole problem. Every race in 2011 had both. There is no season in
which one changed and the other did not, so no amount of time-series sophistication
applied to season-level aggregates can separate them.

---

## 3. Data

### 3.1 Sources

| Source | Used for | Note |
| --- | --- | --- |
| Ergast CSV dump (GitHub mirror) | lap-by-lap positions, results, pit stops | `ergast.com` was retired; this is a byte-identical March 2022 snapshot |
| Jolpica-F1 API | independent verification of the mirror | resumable, disk-cached |
| `data/drs_zones.csv` | DRS zone counts per circuit-season | hand-coded, one source URL per row |

The analysis covers **389 races across 21 seasons (2000 to 2020)** and **427,288 lap
records**. The modelling panel is 377 races after merging treatment intensity.

**On using a mirror.** The original Ergast service was retired during this project, and
the primary data source is therefore a third-party snapshot. Depending on an unverified
mirror for the entire outcome variable is a real risk, so 37 races were independently
re-fetched from the Jolpica-F1 API and compared record for record: all **38,014 matching
lap records** agree on position, with no disagreements in any race.

### 3.2 Constructing the outcome

Formula 1 publishes no overtake statistic, so the outcome is defined explicitly. An
overtake is a **pairwise order inversion between consecutive laps**: drivers A and B both
complete laps L-1 and L, A leads at L-1, and B leads at L. Counting pairwise inversions
rather than summing position deltas means passing two cars scores two, and inheriting a
position from a retirement scores none.

Of 60,468 raw lap-to-lap inversions:

| Excluded | Count | Share | Rationale |
| --- | --- | --- | --- |
| Pit cycles | 47,903 | 79.2% | either driver pitted on lap L-1, L or L+1 |
| Safety car and restart laps | 2,787 | 4.6% | a neutralisation manufactures passes at the restart |
| First two racing laps | 859 | 1.4% | DRS was illegal until two laps were complete |
| Lapped traffic | 0 | 0.0% | filter implemented; every such pair was already removed above |
| **Retained (strict)** | **8,919** | **14.7%** | |
| **Retained (loose)** | **12,565** | **20.8%** | |

Retirements need no explicit rule: a pair is counted only if both drivers appear on both
laps, so a car that stops simply leaves the pair set.

All models are fitted under both the strict and loose definitions, and both are reported.

### 3.3 A trap in the pit-stop data

Pit cycles are by far the largest exclusion, removing 79% of raw inversions. The obvious
way to detect them is the Ergast `pit_stops` table.

**That table begins in 2011, the exact year of the intervention.** Using it would apply
the single largest exclusion rule to the post-treatment period only, mechanically
suppressing the post-2011 overtake count and manufacturing a spurious negative effect out
of nothing but a data-coverage boundary.

Instead, pit stops are detected from lap times: a lap is flagged when a driver's time
exceeds the **field median for that same lap** by more than 11 seconds. Benchmarking
against the field median rather than the driver's own average makes the detector immune to
safety cars, which slow everyone so the median moves with them. Scored against the 8,031
recorded stops from 2011 to 2020, the detector achieves **86.3% recall and 87.4%
precision**, and it behaves identically in every season.

This was the most consequential decision in the project, and nothing in the final
results would have revealed it if it had been made the other way.

### 3.4 Treatment intensity

No public dataset of DRS zone assignments exists, so `data/drs_zones.csv` was hand-coded
across 377 circuit-seasons, each carrying a `source_url` and a provenance flag:

- **306 rows are `documented`**: a source states the count for that circuit and season, or
  states a season-wide rule covering it.
- **71 rows are `interpolated`**: seasons where no source was found but the documented
  seasons on either side agree. Re-running on documented rows
  only gives +1.27 against the headline +1.51.
- **12 races have no coded count** and drop out rather than being guessed.

**Zone length was not obtained.** Per-zone lengths exist only in per-race FIA event notes,
with no consistent series for the period. Treatment intensity throughout is **zone count**.

---

## 4. Method

### 4.1 The naive model, and why it is wrong

The standard tool is an interrupted time series:

```
overtakes ~ t + post2011 + t_since_2011 + n_laps + C(circuit)
```

It returns a level shift of **+26.0 overtakes per race (95% CI +19.1 to +33.0,
p < 0.001)** and attributes all of it to 2011. It is fitted here so the argument against it
has a real number to point at.

The problem is identification, not statistics. The model has one post-2011
indicator and two treatments behind it. It cannot distinguish them, and it does not try.

### 4.2 The identifying idea

The two treatments differ in geometry. Pirelli tyres applied uniformly to every circuit in
a given season. DRS varied across circuits and within circuits over time. So:

```
overtakes[i,t] ~ post2011[t] x n_drs_zones[i,t] + n_laps + C(circuit[i]) + C(year[t])
```

- `C(year)` absorbs anything that hit every circuit equally within a season, which is
  exactly what the tyre change was.
- `C(circuit)` absorbs each track's baseline propensity to produce passes.
- The interaction is identified off *differential* zone exposure across circuits within
  the same season.

The tyre change cannot contaminate the DRS coefficient, because the tyre change has no
cross-circuit variation with which to contaminate it.

The price of this design is discussed in Section 6.

### 4.3 Inference

Every specification uses **Newey-West (HAC) standard errors with `maxlags=3`** on a
date-ordered panel. Overtaking counts are strongly serially correlated, since a season's
cars, tyres and aerodynamic rules persist across all its races. Ordinary OLS standard
errors would be too narrow and would convert this null into a false positive.
Circuit-clustered errors are reported alongside as a cross-check.

---

## 5. Results

### 5.1 The headline estimate

| Specification | Definition | Per zone | 95% CI | p | n |
| --- | --- | --- | --- | --- | --- |
| Two-way FE, HAC | strict | **+1.51** | -4.11 to +7.13 | 0.60 | 377 |
| Two-way FE, circuit-clustered | strict | +1.51 | -5.34 to +8.36 | 0.67 | 377 |
| Two-way FE, HAC | loose | +1.66 | -5.88 to +9.20 | 0.67 | 377 |
| Documented zone rows only | strict | +1.27 | -5.59 to +8.13 | 0.72 | 306 |
| Excluding 5 extreme races | strict | **-0.40** | -4.57 to +3.78 | 0.85 | 374 |
| Poisson GLM (log link) | strict | -0.4% | -21.1% to +25.9% | 0.98 | 377 |

Both overtake definitions agree, and both error structures agree. The estimate is **not
stable in sign**: removing five wet or heavily disrupted races (Brazil 2012, Canada 2011,
Spa 2011 and 2012, China 2016) moves it from +1.5 to -0.4. Those are real races, not
artefacts, but the sensitivity is real too.

**The point estimate is best read as noise around zero, and its sign should not be
quoted.**

### 5.2 Dose-response

If DRS drove the 2011 jump, circuits with more zones should have gained more overtaking.
The unadjusted cross-circuit relationship is +3.9 overtakes per zone with **R² = 0.03**.
Suzuka, on a single zone all decade, gained more than Silverstone, Albert Park and Marina
Bay, which each ran two or three.

### 5.3 Power, and what the null is worth

A null without a stated minimum detectable effect is an underpowered study, not a finding.

- **Closed form:** MDE = 8.03 overtakes per race per zone (strict), 10.78 (loose).
- **Simulated:** resampling the fitted model's residuals under known effects and refitting
  the full specification 400 times per point places the 80% power threshold **between 6.0
  and 8.0**, consistent with the closed form. The rejection rate under a true zero came out
  at 0.07, slightly above nominal, since HAC over-rejects modestly at this sample size.


Now the arithmetic that makes the null useful. The 2011 level shift was +26.0 overtakes
per race against a post-2011 mean of 1.89 zones. For DRS acting alone to produce that, the
per-zone effect would have to be **+13.8**. That value sits above the confidence interval's
upper bound of +7.1, and comfortably inside the range the design can detect.

**The data cannot measure a small DRS effect. They can rule out DRS as the sole cause of
the 2011 jump, at the 5% level.** The tyre regulation has to be carrying most of it.

### 5.4 Placebo tests, including the ones that failed

Fake break dates, fitted on the pre-treatment period (2000 to 2010) only. Restricting the
sample matters: run on the full window, the genuine 2011 break leaks into a fake 2008 break
and the placebo passes for the wrong reason.

| Break | Level shift | p | Slope change | p |
| --- | --- | --- | --- | --- |
| 2007 (placebo) | -3.40 | 0.18 | +3.61 | **0.003** |
| 2008 (placebo) | -0.96 | 0.76 | +5.25 | **0.013** |
| 2009 (placebo) | -1.27 | 0.69 | +12.14 | **0.001** |
| 2011 (genuine) | **+26.02** | **<0.001** | -2.08 | **<0.001** |

**These results are mixed, and they limit what the paper can claim.**

The *level shift* placebos all pass: no fake break produces a significant jump, while the
genuine one produces a very large one. The *slope* placebos all fail: every fake break
finds a significant change in trend. The pre-2011 period carries enough curvature that an
ITS slope term will find a trend change almost wherever it is asked to look.

As a result, **no causal weight is placed on the slope term
anywhere in this analysis.** Only the level shift is used.

**A placebo outcome also fails.** The 2011 break "predicts" the number of finishers per
race (+1.71, 95% CI +0.73 to +2.69, p = 0.001). DRS cannot make cars more reliable. This is
direct evidence that 2011 differed from 2010 in ways unrelated to DRS, which is the
argument against the naive ITS, visible in the data.

---

## 6. Discussion

### What the project actually establishes

Not "DRS did nothing". The design lacks the power to say that, and Section 5.3 quantifies
exactly how much power it lacks. What it establishes is narrower and more defensible: the
popular attribution of the 2011 overtaking jump to DRS alone is inconsistent with the
cross-circuit evidence, and the tyre regulation must account for most of the change.

That is a smaller claim than the one I set out to test. It is the one the data support.

### The cost of the identification strategy

The fixed effects that eliminate the confound also absorb **76.4% of the standard deviation
in zone-count exposure**, because most circuits ran the same number of zones every season.
The design trades precision for identification, and the MDE of 8.0 is the bill.

This is also why the confidence interval is so wide: the interval is wide because the estimator only uses variation that the
confound cannot reach, and there is not much of it.

### The biggest threat, which fixed effects do not fix

**Zone assignment is endogenous.** The FIA placed more DRS zones at circuits where
overtaking was already hard. Treatment intensity is therefore correlated with the
unobserved difficulty of passing at each track, and the coefficient is biased. The likely
direction is *downward*, since zones went where passing was hardest, so a true positive
effect could be masked by the assignment rule itself.

Circuit fixed effects absorb the time-invariant part of this. They do not absorb changes in
zone count that were themselves responses to how a circuit was racing.

---

## 7. Limitations

1. **Endogenous zone assignment**, as above. The single largest threat to validity.
2. **The fixed effects eat the variation**, absorbing 76.4% of treatment-intensity spread.
3. **Safety cars are only proxied.** No safety-car field exists in the data; laps where the
   field-wide median exceeds 1.25x race pace are flagged. This catches full neutralisations,
   also catches heavy rain, and misses short virtual safety cars. Safety-car frequency varies
   by season and circuit and is not fully controlled.
4. **No weather covariate.** The five highest-count races are genuinely wet or chaotic, and
   dropping them flips the sign. There is no weather variable available to handle them
   properly, which makes this the most uncomfortable sensitivity in the paper.
5. **Pit-stop frequency changed in 2011.** Pirelli tyres forced more stops, so more laps are
   blocked by the pit-cycle rule after 2011 than before. This biases the measured post-2011
   count downward, making the estimate conservative rather than inflated.
6. **The ITS slope term is unreliable**, per the placebo tests. Only the level shift is used.
7. **`n_laps` is the only race-level control.** Grid competitiveness, tyre allocation and
   car-performance spread all vary and none are controlled.

---

## 8. What I would do differently

- **Get zone lengths.** Zone count is a coarse proxy for treatment intensity. A 600 m zone
  at Monza and a 600 m zone at the Hungaroring are not the same treatment, and length data
  would sharpen the dose-response considerably. This requires parsing per-race FIA event
  notes, which is a project in itself.
- **Add weather.** The sign instability in Section 5.1 is entirely a weather problem, and it
  is the most fixable weakness here.
- **Use a synthetic control from other racing series.** IndyCar and MotoGP had no DRS and no
  Pirelli change in 2011. Constructing a donor pool from them would give a genuine
  counterfactual rather than relying on within-F1 variation alone. The obstacle is outcome
  comparability, since overtaking means something different in each series.
- **Model the count properly throughout.** The Poisson GLM is reported as a robustness check,
  but overtakes are a count with circuit-level overdispersion, and a negative binomial with
  circuit random effects is arguably the right primary specification.
- **Treat zone assignment as the endogenous variable it is.** An instrument for zone count,
  or a bounds analysis in the spirit of Manski, would address the main threat rather than
  acknowledging it.

---

## 9. Conclusion

Overtaking in Formula 1 roughly doubled in 2011, and DRS is routinely credited with it. The
credit is not supported by the cross-circuit evidence. Circuits that received more DRS zones
did not gain proportionally more overtaking (R² = 0.03), and a panel design that removes the
confounding tyre regulation by construction returns a per-zone effect indistinguishable from
zero, with a sign that flips under routine robustness checks.

The design is underpowered to detect a small DRS effect, and says so: the minimum detectable
effect is 8.0 overtakes per race per zone. But the DRS-alone hypothesis requires +13.8 per
zone, which the design *can* detect and does not find. That hypothesis is rejected at the 5%
level.

The most likely explanation for 2011 is the one that gets less attention: tyres designed to
degrade.

---

## Reproducing

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python src/ingest.py && python src/build_drs_zones.py
python src/overtakes.py && python src/panel.py
python src/its.py && python src/power.py && python src/charts.py
```

`data/drs_zones.csv` is the only committed data file. Everything else regenerates.
Full method notes and the repository map are in [`README.md`](README.md).
