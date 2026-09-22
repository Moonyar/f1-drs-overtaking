"""Join race outcomes to DRS treatment intensity and build the modelling panel."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"

BREAK_YEAR = 2011


def build_panel(include_interpolated: bool = True) -> pd.DataFrame:
    races = pd.read_parquet(PROC / "race_outcomes.parquet")
    zones = pd.read_csv(ROOT / "data" / "drs_zones.csv")

    if not include_interpolated:
        zones = zones[zones.source_type == "documented"]

    # Most rows are keyed on (circuit, year). A handful carry a round as well, because
    # Bahrain hosted two 2020 races on two layouts with different zone counts.
    by_round = zones[zones["round"].notna()].copy()
    by_round["round"] = by_round["round"].astype(int)
    by_year = zones[zones["round"].isna()]

    p = races.merge(
        by_year[["circuit_id", "year", "n_zones", "source_type"]]
        .rename(columns={"circuit_id": "circuitRef"}),
        on=["circuitRef", "year"], how="left")
    p = p.merge(
        by_round[["circuit_id", "year", "round", "n_zones", "source_type"]]
        .rename(columns={"circuit_id": "circuitRef", "n_zones": "n_zones_r",
                         "source_type": "source_type_r"}),
        on=["circuitRef", "year", "round"], how="left")
    p["n_drs_zones"] = p.n_zones_r.fillna(p.n_zones)
    p["zone_source"] = p.source_type_r.fillna(p.source_type)
    p = p.drop(columns=["n_zones", "n_zones_r", "source_type", "source_type_r"])

    p["date"] = pd.to_datetime(p["date"])
    p = p.sort_values("date").reset_index(drop=True)

    # Time terms for the interrupted time series. `t` is a continuous season index so the
    # pre-trend is estimated in seasons, not races.
    p["t"] = p.year - p.year.min()
    p["post2011"] = (p.year >= BREAK_YEAR).astype(int)
    p["t_since_2011"] = (p.year - BREAK_YEAR).clip(lower=0)
    return p


def summarise(p: pd.DataFrame) -> None:
    known = p.n_drs_zones.notna()
    print(f"races: {len(p)}   with a coded zone count: {known.sum()} "
          f"({known.mean():.1%})")
    post = p[p.year >= BREAK_YEAR]
    print(f"post-2011 races: {len(post)}, coded: {post.n_drs_zones.notna().sum()}")
    print("\nzone-count distribution, post-2011 coded races:")
    print(post.n_drs_zones.value_counts().sort_index().to_string())
    print("\nwithin-year variation in zone count (this is what identifies the effect):")
    v = (p[known & (p.year >= BREAK_YEAR)].groupby("year")
         .n_drs_zones.agg(["count", "nunique", "std", "mean"]).round(2))
    print(v.to_string())
    print("\nzone coding provenance:")
    print(p[known].zone_source.value_counts().to_string())


if __name__ == "__main__":
    pan = build_panel()
    pan.to_parquet(PROC / "panel.parquet", index=False)
    summarise(pan)
    print(f"\nwrote {PROC / 'panel.parquet'}")
