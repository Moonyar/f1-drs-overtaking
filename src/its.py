"""The models: a naive interrupted time series, then the dose-response panel that
replaces it, plus placebo break dates and a placebo outcome.

Why HAC standard errors everywhere
----------------------------------
Overtaking counts are strongly serially correlated: a season's cars, tyres and
aerodynamic rules persist across its races, so consecutive residuals move together.
Plain OLS standard errors assume independence, come out too narrow, and would make a
noisy estimate look decisive.  Every fit here uses Newey-West HAC errors on a
date-ordered panel.  Circuit-clustered errors are also reported as a cross-check,
because HAC on a panel treats it as one long series and clustering is the more natural
panel adjustment.

Why the naive ITS is here at all
--------------------------------
It is the model this project argues against.  DRS and the Pirelli high-degradation tyres
both arrived in 2011, so at the season level they are perfectly collinear and a plain ITS
attributes the entire 2011 jump to DRS.  Fitting it makes that failure concrete.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from panel import BREAK_YEAR, build_panel

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"

HAC = {"cov_type": "HAC", "cov_kwds": {"maxlags": 3}}

NAIVE_F = "{y} ~ t + post + t_since + n_laps + C(circuitRef)"
DOSE_F = "{y} ~ post:n_drs_zones + n_laps + C(circuitRef) + C(year)"


def _fit(formula: str, data: pd.DataFrame, cluster: bool = False):
    if cluster:
        return smf.ols(formula, data=data).fit(
            cov_type="cluster", cov_kwds={"groups": data["circuitRef"]})
    return smf.ols(formula, data=data).fit(**HAC)


def _report(res, term: str) -> dict:
    ci = res.conf_int().loc[term]
    return {
        "term": term,
        "coef": float(res.params[term]),
        "se": float(res.bse[term]),
        "ci_low": float(ci[0]),
        "ci_high": float(ci[1]),
        "p": float(res.pvalues[term]),
        "n": int(res.nobs),
        "resid_sd": float(np.sqrt(res.mse_resid)),
    }


def fmt(d: dict, unit: str = "") -> str:
    return (f"{d['coef']:+.3f} {unit} (95% CI {d['ci_low']:+.3f} to {d['ci_high']:+.3f}, "
            f"p = {d['p']:.3f}, n = {d['n']})")


# --------------------------------------------------------------------------------------
def naive_its(p: pd.DataFrame, y: str = "overtakes_strict", break_year: int = BREAK_YEAR):
    """Pre-trend, level shift and post-slope as three separate terms."""
    d = p.copy()
    d["post"] = (d.year >= break_year).astype(int)
    d["t_since"] = (d.year - break_year).clip(lower=0)
    res = _fit(NAIVE_F.format(y=y), d)
    return res, {k: _report(res, k) for k in ("t", "post", "t_since")}


def dose_response(p: pd.DataFrame, y: str = "overtakes_strict", cluster: bool = False):
    """The real estimate: additional overtakes per race per DRS zone.

    `C(year)` absorbs anything that hit every circuit equally in a season, which is
    exactly what the Pirelli tyre change was.  The coefficient is therefore identified
    only off *differential* DRS exposure across circuits within the same season.
    """
    d = p[p.n_drs_zones.notna()].copy()
    d["post"] = (d.year >= BREAK_YEAR).astype(int)
    res = _fit(DOSE_F.format(y=y), d, cluster=cluster)
    return res, _report(res, "post:n_drs_zones")


def placebos(p: pd.DataFrame, y: str = "overtakes_strict",
             years=(2007, 2008, 2009)) -> pd.DataFrame:
    """Fake break dates, fitted on the pre-treatment period only.

    Restricting to 2000-2010 matters: run on the full sample, the genuine 2011 break
    would leak into a fake 2008 break and make the placebo look like a pass for the
    wrong reason.
    """
    pre = p[p.year < BREAK_YEAR]
    rows = []
    for yr in years:
        _, terms = naive_its(pre, y=y, break_year=yr)
        for k, v in terms.items():
            rows.append({"break_year": yr, **v})
    # the genuine break, on the full sample, for comparison
    _, real = naive_its(p, y=y)
    for k, v in real.items():
        rows.append({"break_year": BREAK_YEAR, **v})
    return pd.DataFrame(rows)


def robustness(p: pd.DataFrame, y: str = "overtakes_strict") -> pd.DataFrame:
    """Does the headline per-zone estimate survive obvious challenges to it?"""
    import statsmodels.api as sm

    rows = []
    _, base = dose_response(p, y=y)
    rows.append({"check": "headline (HAC)", **base})

    # A handful of wet or heavily disrupted races carry three times the typical count.
    # They are genuine races, not artefacts, but the estimate should not rest on them.
    cut = p[p[y] <= 85]
    _, d = dose_response(cut, y=y)
    rows.append({"check": "excluding 5 extreme races", **d})

    # The outcome is a count, so a log-link Poisson is the natural alternative to OLS.
    d2 = p[p.n_drs_zones.notna()].copy()
    d2["post"] = (d2.year >= BREAK_YEAR).astype(int)
    pois = smf.glm(DOSE_F.format(y=y), data=d2,
                   family=sm.families.Poisson()).fit(
                       cov_type="cluster", cov_kwds={"groups": d2["circuitRef"]})
    term = "post:n_drs_zones"
    ci = pois.conf_int().loc[term]
    rows.append({"check": "Poisson GLM (log link, % change)", "term": term,
                 "coef": float(pois.params[term]), "se": float(pois.bse[term]),
                 "ci_low": float(ci[0]), "ci_high": float(ci[1]),
                 "p": float(pois.pvalues[term]), "n": int(pois.nobs),
                 "resid_sd": float("nan")})
    return pd.DataFrame(rows)


def placebo_outcome(p: pd.DataFrame):
    """Does the 2011 break 'predict' something DRS cannot affect, like finisher count?"""
    return naive_its(p, y="n_finishers")


# --------------------------------------------------------------------------------------
def main() -> None:
    p = build_panel()
    results: dict[str, dict] = {}

    print("=" * 78)
    print("1. NAIVE INTERRUPTED TIME SERIES  (the model this project argues against)")
    print("=" * 78)
    for y in ("overtakes_strict", "overtakes_loose"):
        res, terms = naive_its(p, y=y)
        print(f"\n  outcome = {y}   n = {int(res.nobs)}   R2 = {res.rsquared:.3f}")
        print(f"    pre-trend    (t)        {fmt(terms['t'], 'overtakes/season')}")
        print(f"    level shift  (post2011) {fmt(terms['post'], 'overtakes/race')}")
        print(f"    post-slope   (t_since)  {fmt(terms['t_since'], 'overtakes/season')}")
        results[f"naive_{y}"] = terms

    print()
    print("=" * 78)
    print("2. DOSE-RESPONSE PANEL  (circuit + year fixed effects) - the real estimate")
    print("=" * 78)
    for y in ("overtakes_strict", "overtakes_loose"):
        res, d = dose_response(p, y=y)
        _, dc = dose_response(p, y=y, cluster=True)
        print(f"\n  outcome = {y}   n = {d['n']}   R2 = {res.rsquared:.3f}")
        print(f"    per DRS zone, HAC          {fmt(d, 'overtakes/race/zone')}")
        print(f"    per DRS zone, circuit-clus {fmt(dc, 'overtakes/race/zone')}")
        results[f"dose_{y}"] = d
        results[f"dose_cluster_{y}"] = dc

    # documented-only zone coding, as a robustness check on the hand-coded table
    p_doc = build_panel(include_interpolated=False)
    res, d = dose_response(p_doc, y="overtakes_strict")
    print(f"\n  documented zone rows only  {fmt(d, 'overtakes/race/zone')}")
    results["dose_documented_only"] = d

    print()
    print("=" * 78)
    print("2b. ROBUSTNESS OF THE HEADLINE ESTIMATE")
    print("=" * 78)
    rb = robustness(p)
    for _, r in rb.iterrows():
        unit = "log pts" if "Poisson" in r["check"] else "overtakes/race/zone"
        print(f"    {r['check']:34s} {r.coef:+7.3f} {unit:20s} "
              f"CI [{r.ci_low:+7.3f}, {r.ci_high:+7.3f}]  p = {r.p:.3f}  n = {r.n}")
    rb.to_csv(PROC / "robustness.csv", index=False)

    print()
    print("=" * 78)
    print("3. PLACEBO BREAK DATES  (fitted on 2000-2010 only)")
    print("=" * 78)
    pl = placebos(p)
    for yr, g in pl.groupby("break_year"):
        tag = "GENUINE" if yr == BREAK_YEAR else "placebo"
        print(f"\n  {tag} break at {yr}")
        for _, r in g.iterrows():
            star = "  <-- significant" if r.p < 0.05 else ""
            print(f"    {r.term:10s} {r.coef:+8.3f}  CI [{r.ci_low:+7.3f}, "
                  f"{r.ci_high:+7.3f}]  p = {r.p:.3f}{star}")
    pl.to_csv(PROC / "placebo_results.csv", index=False)

    print()
    print("=" * 78)
    print("4. PLACEBO OUTCOME  (number of finishers - DRS should not move this)")
    print("=" * 78)
    _, terms = placebo_outcome(p)
    for k, v in terms.items():
        star = "  <-- significant" if v["p"] < 0.05 else ""
        print(f"    {k:10s} {fmt(v, 'finishers')}{star}")
    results["placebo_outcome"] = terms

    pd.to_pickle(results, PROC / "model_results.pkl")
    print(f"\nwrote {PROC / 'model_results.pkl'} and {PROC / 'placebo_results.csv'}")


if __name__ == "__main__":
    main()
