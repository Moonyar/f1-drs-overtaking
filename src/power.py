"""Power analysis for the dose-response estimate.

A null result only means something next to the smallest effect the design could have
detected.  This module computes that minimum detectable effect (MDE) two ways:

1. **Closed form.** For a coefficient estimated with standard error SE, the smallest
   true effect detectable at 80% power and a 5% two-sided test is
   `(z_0.975 + z_0.80) * SE`, about `2.80 * SE`.
2. **Simulation.** Draw synthetic outcomes under a known per-zone effect by resampling
   the fitted model's residuals, refit the full specification with HAC errors, and count
   how often the effect is recovered as significant.  Slower, but it checks the
   closed form against the actual design matrix.

It also reports how much usable variation in zone count survives the circuit and year
fixed effects, which is why the interval is as wide as it is: most circuits
ran the same number of zones every season, so the circuit dummies absorb nearly all of
the treatment variation.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import patsy
import statsmodels.api as sm
from scipy import stats

from its import BREAK_YEAR, DOSE_F, dose_response
from panel import build_panel

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"

ALPHA = 0.05
POWER = 0.80
MAXLAGS = 3


def mde_closed_form(se: float, alpha: float = ALPHA, power: float = POWER) -> float:
    z_a = stats.norm.ppf(1 - alpha / 2)
    z_b = stats.norm.ppf(power)
    return (z_a + z_b) * se


def residual_treatment_variation(p: pd.DataFrame, y: str = "overtakes_strict") -> dict:
    """How much variation in zone count survives the two-way fixed effects."""
    d = p[p.n_drs_zones.notna()].copy()
    d["post"] = (d.year >= BREAK_YEAR).astype(int)
    d["dose"] = d.post * d.n_drs_zones
    X = patsy.dmatrix("n_laps + C(circuitRef) + C(year)", d, return_type="dataframe")
    resid = sm.OLS(d.dose.to_numpy(), X.to_numpy()).fit().resid
    return {
        "sd_dose_raw": float(d.dose.std()),
        "sd_dose_after_fe": float(resid.std()),
        "share_absorbed": float(1 - resid.std() / d.dose.std()),
        "n": int(len(d)),
    }


def simulate_power(p: pd.DataFrame, betas, y: str = "overtakes_strict",
                   n_sims: int = 400, seed: int = 7) -> pd.DataFrame:
    """Empirical rejection rate at each true per-zone effect."""
    rng = np.random.default_rng(seed)
    d = p[p.n_drs_zones.notna()].copy()
    d["post"] = (d.year >= BREAK_YEAR).astype(int)

    yv, X = patsy.dmatrices(DOSE_F.format(y=y), d, return_type="dataframe")
    names = list(X.columns)
    j = names.index("post:n_drs_zones")
    Xn = X.to_numpy()

    base = sm.OLS(yv.to_numpy().ravel(), Xn).fit()
    resid = base.resid
    fitted_no_effect = base.fittedvalues - base.params[j] * Xn[:, j]
    dose = Xn[:, j]

    rows = []
    for b in betas:
        rejects = 0
        for _ in range(n_sims):
            e = rng.choice(resid, size=len(resid), replace=True)
            ysim = fitted_no_effect + b * dose + e
            r = sm.OLS(ysim, Xn).fit(cov_type="HAC", cov_kwds={"maxlags": MAXLAGS})
            if r.pvalues[j] < ALPHA:
                rejects += 1
        rows.append({"true_beta": b, "power": rejects / n_sims, "n_sims": n_sims})
        print(f"    beta = {b:+.2f}  power = {rejects/n_sims:.2f}", flush=True)
    return pd.DataFrame(rows)


def main() -> None:
    p = build_panel()

    print("=" * 78)
    print("HOW MUCH TREATMENT VARIATION SURVIVES THE FIXED EFFECTS")
    print("=" * 78)
    rv = residual_treatment_variation(p)
    print(f"  SD of zone-count dose, raw            : {rv['sd_dose_raw']:.3f}")
    print(f"  SD after circuit + year fixed effects : {rv['sd_dose_after_fe']:.3f}")
    print(f"  absorbed by the fixed effects         : {rv['share_absorbed']:.1%}")
    print("  Most circuits ran the same zone count every season, so the circuit dummies")
    print("  absorb nearly all of it. What is left is the handful of circuits that")
    print("  actually changed zone count between seasons.")

    print()
    print("=" * 78)
    print("MINIMUM DETECTABLE EFFECT")
    print("=" * 78)
    out = {}
    for y in ("overtakes_strict", "overtakes_loose"):
        _, d = dose_response(p, y=y)
        mde = mde_closed_form(d["se"])
        print(f"\n  outcome = {y}")
        print(f"    estimate        {d['coef']:+.3f} overtakes/race/zone "
              f"(95% CI {d['ci_low']:+.3f} to {d['ci_high']:+.3f})")
        print(f"    standard error  {d['se']:.3f}")
        print(f"    MDE at 80% power, 5% two-sided: {mde:.2f} overtakes/race/zone")
        out[y] = {**d, "mde": mde}

    # What per-zone effect would DRS need for it to explain the whole 2011 jump?
    res = pd.read_pickle(PROC / "model_results.pkl")
    shift = res["naive_overtakes_strict"]["post"]["coef"]
    mean_zones = p.loc[p.year >= BREAK_YEAR, "n_drs_zones"].mean()
    needed = shift / mean_zones
    d = out["overtakes_strict"]
    print()
    print("=" * 78)
    print("CAN DRS ALONE EXPLAIN THE 2011 JUMP?")
    print("=" * 78)
    print(f"  naive ITS level shift at 2011      : {shift:+.2f} overtakes/race")
    print(f"  mean DRS zones per post-2011 race  : {mean_zones:.2f}")
    print(f"  per-zone effect DRS would need     : {needed:+.2f} overtakes/race/zone")
    print(f"  our 95% CI upper bound             : {d['ci_high']:+.2f}")
    verdict = ("RULED OUT at 5%: the required effect sits above the confidence interval"
               if needed > d["ci_high"] else
               "NOT ruled out: the required effect sits inside the confidence interval")
    print(f"  -> {verdict}")
    out["required_for_full_jump"] = float(needed)
    out["ruled_out"] = bool(needed > d["ci_high"])

    print()
    print("=" * 78)
    print("SIMULATED POWER  (resampled residuals, full specification, HAC errors)")
    print("=" * 78)
    grid = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0]
    sim = simulate_power(p, grid)
    sim.to_csv(PROC / "power_simulation.csv", index=False)

    above = sim[sim.power >= POWER]
    if len(above):
        lo = sim[sim.power < POWER].true_beta.max() if (sim.power < POWER).any() else 0.0
        hi = above.true_beta.min()
        print(f"\n  simulated 80%-power threshold lies between {lo:.1f} and {hi:.1f}")
    else:
        print(f"\n  80% power is not reached anywhere on the tested grid "
              f"(up to {max(grid):.0f}); the design is weaker than the closed form implies")
    print(f"  closed-form MDE for comparison: {out['overtakes_strict']['mde']:.2f}")

    pd.to_pickle(out, PROC / "power_results.pkl")
    print(f"\nwrote {PROC / 'power_results.pkl'} and {PROC / 'power_simulation.csv'}")


if __name__ == "__main__":
    main()
