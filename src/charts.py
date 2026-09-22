"""Figures for the README."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from its import BREAK_YEAR
from panel import build_panel

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "figures"
PROC = ROOT / "data" / "processed"

# Aqua is low-contrast on the light background, so every series is also labelled.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SURFACE = "#fcfcfb"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#8c8b85"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "font.size": 10,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False,
    "grid.color": "#e6e5e0", "grid.linewidth": 0.8,
})


def _clean(ax, title, sub=None, xlabel=None, ylabel=None):
    # Title and subtitle are placed in axes coordinates so a two-line subtitle can
    # never ride up into the title.
    n_sub = 1 + (sub.count("\n") if sub else 0)
    ax.text(0, 1.10 + 0.045 * n_sub, title, transform=ax.transAxes, color=INK,
            fontsize=12.5, fontweight="bold", va="bottom")
    if sub:
        ax.text(0, 1.03, sub, transform=ax.transAxes, color=INK2, fontsize=9,
                va="bottom", linespacing=1.45)
    ax.set_xlabel(xlabel or "", fontsize=10)
    ax.set_ylabel(ylabel or "", fontsize=10)
    ax.grid(axis="y", alpha=0.9)
    ax.set_axisbelow(True)


def hero(p: pd.DataFrame) -> None:
    """Overtakes per race by season, with the 2011 break and fitted pre/post trends."""
    fig, ax = plt.subplots(figsize=(9.5, 5.4))
    by = p.groupby("year").overtakes_strict.agg(["mean", "std", "count"])
    yrs = by.index.to_numpy()
    se = by["std"] / np.sqrt(by["count"])

    # per-race spread, kept recessive
    ax.scatter(p.year + np.random.default_rng(0).uniform(-.18, .18, len(p)),
               p.overtakes_strict, s=9, color=MUTED, alpha=.30, linewidths=0,
               label="_nolegend_", zorder=1)
    ax.errorbar(yrs, by["mean"], yerr=1.96 * se, fmt="o", color=BLUE, ms=6,
                lw=0, elinewidth=1.6, ecolor=BLUE, capsize=0, zorder=4,
                label="Season mean (95% CI)")

    pre, post = yrs < BREAK_YEAR, yrs >= BREAK_YEAR
    for mask, col, lab in ((pre, ORANGE, "Pre-DRS trend"), (post, AQUA, "Post-DRS trend")):
        b = np.polyfit(yrs[mask], by["mean"][mask], 1)
        ax.plot(yrs[mask], np.polyval(b, yrs[mask]), color=col, lw=2.2, zorder=3,
                label=lab)

    # Five wet or heavily disrupted races run past 80; they are genuine, but letting
    # them set the scale would flatten the pattern the chart is about.
    ax.set_ylim(-3, 85)
    ax.axvline(BREAK_YEAR - .5, color=INK, lw=1.4, ls=(0, (5, 3)), zorder=2)
    ax.annotate("2011: DRS and Pirelli\nhigh-degradation tyres\narrive together",
                xy=(BREAK_YEAR - .3, 80), color=INK, fontsize=9.5, ha="left", va="top")
    n_hi = int((p.overtakes_strict > 85).sum())
    ax.text(.995, .02, f"{n_hi} wet or heavily disrupted races run above 85 and are "
            f"off-scale", transform=ax.transAxes, ha="right", va="bottom",
            color=MUTED, fontsize=8.5)
    ax.set_xticks(range(2000, 2021, 2))
    _clean(ax, "Overtaking jumped in 2011, but DRS was not the only thing that changed",
           "On-track overtakes per race, 389 races, 2000-2020. Strict definition: pit "
           "cycles, retirements,\nsafety-car laps and the first two laps excluded.",
           "Season", "On-track overtakes per race")
    leg = ax.legend(frameon=False, loc="upper left", fontsize=9.5)
    for t in leg.get_texts():
        t.set_color(INK2)
    fig.tight_layout()
    fig.savefig(FIG / "overtakes_by_season.png", dpi=160)
    plt.close(fig)


def dose_chart(p: pd.DataFrame) -> None:
    """DRS zone count against the change in overtaking, per circuit."""
    pre = (p[p.year < BREAK_YEAR].groupby("circuitRef").overtakes_strict
           .agg(["mean", "count"]).rename(columns={"mean": "pre", "count": "n_pre"}))
    post = (p[(p.year >= BREAK_YEAR) & p.n_drs_zones.notna()]
            .groupby("circuitRef")
            .agg(post=("overtakes_strict", "mean"), n_post=("overtakes_strict", "size"),
                 zones=("n_drs_zones", "mean")))
    d = pre.join(post, how="inner")
    d = d[(d.n_pre >= 3) & (d.n_post >= 3)]
    d["delta"] = d.post - d.pre

    fig, ax = plt.subplots(figsize=(9.5, 5.4))
    ax.axhline(0, color=MUTED, lw=1)
    ax.scatter(d.zones, d.delta, s=64, color=BLUE, alpha=.85, linewidths=1.2,
               edgecolors=SURFACE, zorder=3)
    for name, r in d.iterrows():
        ax.annotate(name.replace("_", " "), (r.zones, r.delta), fontsize=8,
                    color=INK2, xytext=(6, 3), textcoords="offset points")
    b = np.polyfit(d.zones, d.delta, 1)
    r = float(np.corrcoef(d.zones, d.delta)[0, 1])
    xs = np.linspace(d.zones.min() - .1, d.zones.max() + .1, 50)
    ax.plot(xs, np.polyval(b, xs), color=ORANGE, lw=2.2, zorder=2,
            label=f"Unadjusted slope {b[0]:+.1f} per zone  (r = {r:.2f}, "
                  f"R\u00b2 = {r**2:.2f})")
    ax.margins(y=.18)
    _clean(ax, "Zone count explains almost none of the cross-circuit variation in the gain",
           "Change in mean overtakes per race, post-2011 minus pre-2011, against mean DRS\n"
           "zone count. Unadjusted; the fitted model adds circuit and season effects.",
           "Mean DRS zones per race, 2011-2020", "Change in overtakes per race")
    leg = ax.legend(frameon=False, loc="lower right", fontsize=9)
    for t in leg.get_texts():
        t.set_color(INK2)
    fig.tight_layout()
    fig.savefig(FIG / "dose_response.png", dpi=160)
    plt.close(fig)


def power_chart(p: pd.DataFrame) -> None:
    sim = pd.read_csv(PROC / "power_simulation.csv")
    pw = pd.read_pickle(PROC / "power_results.pkl")
    est = pw["overtakes_strict"]

    fig, ax = plt.subplots(figsize=(9.5, 5.0))
    ax.plot(sim.true_beta, sim.power, "-o", color=BLUE, lw=2.2, ms=7,
            label="Simulated power")
    ax.axhline(.80, color=MUTED, lw=1.2, ls=(0, (4, 3)))
    ax.text(sim.true_beta.max(), .81, "80% power", ha="right", va="bottom",
            color=INK2, fontsize=9)
    ax.axvline(est["coef"], color=AQUA, lw=2, label=f"Our estimate ({est['coef']:+.1f})")
    ax.axvspan(est["ci_low"], est["ci_high"], color=AQUA, alpha=.12, lw=0,
               label="95% CI of our estimate")
    need = pw["required_for_full_jump"]
    ax.axvline(need, color=ORANGE, lw=2, ls=(0, (5, 3)),
               label=f"Needed if DRS explained the whole jump ({need:+.1f})")
    ax.set_ylim(0, 1.02)
    _clean(ax, "The design could only have detected a large per-zone effect",
           "Rejection rate over 400 simulations per point, resampling the fitted model's "
           "residuals.",
           "True effect (overtakes per race per DRS zone)", "Power")
    ax.set_xticks(list(sim.true_beta))
    leg = ax.legend(frameon=False, loc="lower right", fontsize=9)
    for t in leg.get_texts():
        t.set_color(INK2)
    fig.tight_layout()
    fig.savefig(FIG / "power_curve.png", dpi=160)
    plt.close(fig)


def main() -> None:
    FIG.mkdir(exist_ok=True)
    p = build_panel()
    hero(p)
    dose_chart(p)
    power_chart(p)
    print("wrote:", *(f.name for f in sorted(FIG.glob("*.png"))))


if __name__ == "__main__":
    main()
