"""Turn lap-by-lap positions into a defensible per-race overtake count.

An overtake is a **pairwise order inversion between consecutive laps**: drivers A and B
both complete lap L-1 and lap L, A is ahead at L-1, and B is ahead at L.  Counting
pairwise inversions rather than summing positive position deltas means a driver who
passes two cars scores two, and a driver who gains a place because someone else stopped
scores none.

Exclusions, and why each one is there:

* **Retirements.** A pair is only counted if *both* drivers appear on *both* laps.  A car
  that stops simply leaves the pair set, so the free places everyone behind inherits are
  never counted.
* **Pit cycles.** The single biggest source of false positives.  Any pair where either
  driver was in a pit cycle on lap L-1, L or L+1 is dropped.
* **The first two laps** (strict only).  Start-line shuffling is not overtaking, and DRS
  was illegal until two racing laps had been completed, so the strict definition only
  counts position changes from lap 3 onward.
* **Safety cars** (strict only).  An SC bunches the field and manufactures passes at the
  restart, and SC frequency is not constant across seasons or circuits.
* **Lapped traffic** (strict only).  A pair separated by more than 0.9 of a lap of
  elapsed time is not a battle for position.

Detecting pit stops without a pit-stop table
--------------------------------------------
Ergast's `pit_stops` table only starts in 2011 - the exact year of the intervention.
Using it directly would mean applying the single largest exclusion rule to the
post-treatment period only, which would manufacture a spurious negative effect.  So pit
stops are instead detected from the lap times themselves, identically in every season: a
lap is an in-lap or out-lap if the driver's time exceeds the *field median for that same
lap* by more than `PIT_EXCESS_MS`.  Comparing against the field median rather than the
driver's own average means a safety car, which slows everyone, does not look like a pit
stop.

`validate_pit_detector()` scores this detector against the recorded pit stops for
2011-2020, where both exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"

PIT_EXCESS_MS = 11_000      # lap time above the field median that marks an in/out lap
SC_MULT = 1.25              # field median lap slower than this * race pace => neutralised
SC_RESTART_LAPS = 2         # laps after a neutralisation before racing is counted again
LAPPED_FRAC = 0.90          # elapsed-time gap, as a fraction of a lap, beyond which a
                            # pair is treated as not racing each other
DRS_LEGAL_FROM_LAP = 3      # DRS was illegal until two racing laps were completed


@dataclass
class RaceOutcome:
    raceId: int
    n_laps: int
    n_starters: int
    n_finishers: int
    overtakes_raw: int
    overtakes_loose: int
    overtakes_strict: int
    sc_laps_flagged: int
    pit_laps_detected: int
    slow_lap_share: float
    dropped_pit: int
    dropped_sc: int
    dropped_lapped: int
    dropped_early: int


def _race_matrices(g: pd.DataFrame):
    """Pivot one race into aligned (lap x driver) position and lap-time matrices."""
    pos = g.pivot(index="lap", columns="driverId", values="position")
    ms = g.pivot(index="lap", columns="driverId", values="milliseconds")
    ms = ms.reindex(index=pos.index, columns=pos.columns)
    return pos.sort_index(), ms.reindex(sorted(pos.index))


def analyse_race(race_id: int, g: pd.DataFrame, n_result_finishers: int) -> RaceOutcome:
    pos_df, ms_df = _race_matrices(g)
    pos = pos_df.to_numpy(dtype=float)
    ms = ms_df.to_numpy(dtype=float)
    n_laps, n_drv = pos.shape

    present = ~np.isnan(pos)

    # --- race pace and neutralisation -------------------------------------------------
    field_med = np.nanmedian(np.where(present, ms, np.nan), axis=1)
    ref_laps = field_med[DRS_LEGAL_FROM_LAP - 1:] if n_laps > 4 else field_med
    race_pace = np.nanmedian(ref_laps)
    sc_lap = field_med > SC_MULT * race_pace
    sc_lap = np.nan_to_num(sc_lap, nan=False).astype(bool)

    # A lap is unusable in the strict definition if it is neutralised or within the
    # restart window after a neutralisation.
    blocked = sc_lap.copy()
    for k in range(1, SC_RESTART_LAPS + 1):
        blocked[k:] |= sc_lap[:-k]

    # --- pit detection ----------------------------------------------------------------
    excess = ms - field_med[:, None]
    pit = np.nan_to_num(excess, nan=-1e9) > PIT_EXCESS_MS
    pit &= present
    # An in-lap at L means the out-lap is L+1; block L-1, L and L+1.
    in_cycle = pit.copy()
    in_cycle[1:] |= pit[:-1]
    in_cycle[:-1] |= pit[1:]

    # --- elapsed time, for lapped-traffic detection -----------------------------------
    cum = np.nancumsum(np.where(present, ms, 0.0), axis=0)
    cum[~present] = np.nan
    lap_gap = LAPPED_FRAC * race_pace

    raw = loose = strict = 0
    d_pit = d_sc = d_lapped = d_early = 0

    for L in range(1, n_laps):
        both = present[L - 1] & present[L]
        idx = np.flatnonzero(both)
        if idx.size < 2:
            continue
        p0 = pos[L - 1, idx]
        p1 = pos[L, idx]
        # inverted[a, b] is True when a and b swap order between the two laps
        s0 = np.sign(p0[:, None] - p0[None, :])
        s1 = np.sign(p1[:, None] - p1[None, :])
        inverted = (s0 * s1) < 0
        np.fill_diagonal(inverted, False)
        n_raw = int(inverted.sum() // 2)
        raw += n_raw
        if n_raw == 0:
            continue

        # pit-cycle exclusion (applies to both definitions)
        cyc = in_cycle[L, idx]
        pit_pair = cyc[:, None] | cyc[None, :]
        after_pit = inverted & ~pit_pair
        d_pit += n_raw - int(after_pit.sum() // 2)

        lap_no = L + 1                       # 1-indexed lap number of the later lap
        if lap_no >= 2:
            loose += int(after_pit.sum() // 2)

        # strict: DRS-legal laps only, no neutralisation, no lapped pairs
        if lap_no < DRS_LEGAL_FROM_LAP:
            d_early += int(after_pit.sum() // 2)
            continue
        if blocked[L]:
            d_sc += int(after_pit.sum() // 2)
            continue
        c = cum[L, idx]
        gap = np.abs(c[:, None] - c[None, :])
        same_lap = gap <= lap_gap
        final = after_pit & same_lap
        d_lapped += int(after_pit.sum() // 2) - int(final.sum() // 2)
        strict += int(final.sum() // 2)

    return RaceOutcome(
        raceId=race_id,
        n_laps=n_laps,
        n_starters=int(present[0].sum()) if n_laps else 0,
        n_finishers=n_result_finishers,
        overtakes_raw=raw,
        overtakes_loose=loose,
        overtakes_strict=strict,
        sc_laps_flagged=int(sc_lap.sum()),
        pit_laps_detected=int(pit.sum()),
        slow_lap_share=float(sc_lap.mean()) if n_laps else float("nan"),
        dropped_pit=d_pit,
        dropped_sc=d_sc,
        dropped_lapped=d_lapped,
        dropped_early=d_early,
    )


def validate_pit_detector(laps: pd.DataFrame, pits: pd.DataFrame,
                          races: pd.DataFrame) -> dict:
    """Score the lap-time pit detector against recorded pit stops (2011-2020 only)."""
    yr = races.set_index("raceId").year
    have = pits.raceId.unique()
    lap_sub = laps[laps.raceId.isin(have)].copy()
    field_med = (lap_sub.groupby(["raceId", "lap"]).milliseconds.transform("median"))
    lap_sub["detected"] = (lap_sub.milliseconds - field_med) > PIT_EXCESS_MS

    # A recorded stop on lap L shows up as a slow in-lap on L or a slow out-lap on L+1.
    truth = set()
    for r, d, l in pits[["raceId", "driverId", "lap"]].itertuples(index=False):
        truth.add((r, d, l))
        truth.add((r, d, l + 1))

    det = set(map(tuple, lap_sub.loc[lap_sub.detected, ["raceId", "driverId", "lap"]]
                  .to_numpy()))
    stops = set(map(tuple, pits[["raceId", "driverId", "lap"]].to_numpy()))

    # Recall: of recorded stops, how many produced a detectable slow lap?
    recalled = sum(1 for (r, d, l) in stops if (r, d, l) in det or (r, d, l + 1) in det)
    # Precision: of detected slow laps, how many sit on a recorded stop's in/out lap?
    precise = sum(1 for k in det if k in truth)
    return {
        "races_checked": int(len(have)),
        "recorded_stops": len(stops),
        "detected_slow_laps": len(det),
        "recall": recalled / len(stops) if stops else float("nan"),
        "precision": precise / len(det) if det else float("nan"),
        "years": f"{int(yr[list(have)].min())}-{int(yr[list(have)].max())}",
    }


def build(verbose: bool = True) -> pd.DataFrame:
    races = pd.read_parquet(PROC / "races.parquet")
    laps = pd.read_parquet(PROC / "laps.parquet")
    results = pd.read_parquet(PROC / "results.parquet")
    pits = pd.read_parquet(PROC / "pits.parquet")

    finishers = (results.assign(fin=results.positionText.astype(str).str.isdigit())
                 .groupby("raceId").fin.sum())

    rows = []
    for race_id, g in laps.groupby("raceId", sort=True):
        rows.append(analyse_race(race_id, g, int(finishers.get(race_id, 0))))
    out = pd.DataFrame([r.__dict__ for r in rows])

    out = out.merge(
        races[["raceId", "year", "round", "circuitRef", "circuit_name", "name", "date"]],
        on="raceId", how="left")
    out = out.sort_values(["year", "round"]).reset_index(drop=True)

    if verbose:
        tot_raw = out.overtakes_raw.sum()
        print(f"races: {len(out)}   raw inversions: {tot_raw:,}")
        print(f"  dropped to pit cycles   : {out.dropped_pit.sum():>7,} "
              f"({out.dropped_pit.sum()/tot_raw:.1%} of raw)")
        print(f"  dropped to early laps   : {out.dropped_early.sum():>7,} "
              f"({out.dropped_early.sum()/tot_raw:.1%})")
        print(f"  dropped to neutralised  : {out.dropped_sc.sum():>7,} "
              f"({out.dropped_sc.sum()/tot_raw:.1%})")
        print(f"  dropped to lapped pairs : {out.dropped_lapped.sum():>7,} "
              f"({out.dropped_lapped.sum()/tot_raw:.1%})")
        print(f"  loose kept  : {out.overtakes_loose.sum():>7,} "
              f"({out.overtakes_loose.sum()/tot_raw:.1%})")
        print(f"  strict kept : {out.overtakes_strict.sum():>7,} "
              f"({out.overtakes_strict.sum()/tot_raw:.1%})")
        print("\npit detector vs recorded stops:", validate_pit_detector(laps, pits, races))
    return out


def main() -> None:
    out = build()
    PROC.mkdir(parents=True, exist_ok=True)
    out.to_parquet(PROC / "race_outcomes.parquet", index=False)
    print(f"\nwrote {PROC / 'race_outcomes.parquet'}")
    print("\novertakes per race by season (strict / loose):")
    s = out.groupby("year")[["overtakes_strict", "overtakes_loose"]].mean().round(1)
    print(s.to_string())


if __name__ == "__main__":
    main()
