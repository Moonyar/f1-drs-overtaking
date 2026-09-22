"""Load the Ergast CSV dump, filter to the analysis window, and write parquet.

Source note
-----------
ergast.com is dead: `https://ergast.com/downloads/f1db_csv.zip` now 301-redirects to an
HTML page.  The dump itself still exists as a byte-for-byte mirror at
`github.com/rubenv/ergast-mrd`, snapshot dated March 2022, which fully covers the
2000-2020 analysis window.  That mirror is what this module loads, and a copy of the
zip is kept in `data/raw/` so the pipeline is reproducible offline.

Why Ergast and not f1db: f1db (the actively maintained bulk release) has no lap-by-lap
position data, and position per driver per lap is the only thing that makes an overtake
definable.  f1db is still the better source for some structural tables, but Ergast's
`lap_times` is irreplaceable here.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "ergast"
ZIP = ROOT / "data" / "raw" / "ergast_f1db_csv.zip"
PROC = ROOT / "data" / "processed"

MIRROR_URL = "https://raw.githubusercontent.com/rubenv/ergast-mrd/master/f1db_csv.zip"

YEAR_MIN, YEAR_MAX = 2000, 2020
NA = ["\\N"]

# The shipped races.csv header predates the practice/qualifying/sprint columns that the
# rows actually contain, so the schema is supplied explicitly.
RACE_COLS = [
    "raceId", "year", "round", "circuitId", "name", "date", "time", "url",
    "fp1_date", "fp1_time", "fp2_date", "fp2_time", "fp3_date", "fp3_time",
    "quali_date", "quali_time", "sprint_date", "sprint_time",
]


def ensure_raw() -> None:
    """Extract the mirrored dump if the CSVs are not already on disk."""
    if (RAW / "lap_times.csv").exists():
        return
    if not ZIP.exists():
        import urllib.request
        ZIP.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {MIRROR_URL}")
        urllib.request.urlretrieve(MIRROR_URL, ZIP)
    RAW.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP) as z:
        z.extractall(RAW)
    print(f"extracted dump to {RAW}")


def load() -> dict[str, pd.DataFrame]:
    """Load every table this analysis uses, filtered to the window where applicable."""
    ensure_raw()

    races = pd.read_csv(RAW / "races.csv", header=0, names=RACE_COLS, na_values=NA)
    circuits = pd.read_csv(RAW / "circuits.csv", na_values=NA)
    races = races[(races.year >= YEAR_MIN) & (races.year <= YEAR_MAX)]
    races = races.merge(
        circuits[["circuitId", "circuitRef", "name", "country"]].rename(
            columns={"name": "circuit_name"}),
        on="circuitId", how="left",
    )
    keep = set(races.raceId)

    laps = pd.read_csv(RAW / "lap_times.csv", na_values=NA)
    laps = laps[laps.raceId.isin(keep)]

    results = pd.read_csv(RAW / "results.csv", na_values=NA)
    results = results[results.raceId.isin(keep)]

    pits = pd.read_csv(RAW / "pit_stops.csv", na_values=NA)
    pits = pits[pits.raceId.isin(keep)]

    status = pd.read_csv(RAW / "status.csv", na_values=NA)
    drivers = pd.read_csv(RAW / "drivers.csv", na_values=NA)

    return {"races": races, "laps": laps, "results": results, "pits": pits,
            "status": status, "drivers": drivers, "circuits": circuits}


def main() -> None:
    PROC.mkdir(parents=True, exist_ok=True)
    tabs = load()
    for name, df in tabs.items():
        df.to_parquet(PROC / f"{name}.parquet", index=False)
        print(f"{name:10s} {len(df):>8,} rows -> {PROC / (name + '.parquet')}")

    races, laps = tabs["races"], tabs["laps"]
    cov = laps.groupby("raceId").lap.max().reindex(races.raceId)
    print(f"\nwindow {YEAR_MIN}-{YEAR_MAX}: {len(races)} races, "
          f"{races.circuitRef.nunique()} circuits, {len(laps):,} lap records")
    print(f"races with no lap data: {int(cov.isna().sum())}")
    print(f"pit-stop table covers years: {tabs['pits'].merge(races[['raceId','year']], on='raceId').year.min()}"
          f"-{tabs['pits'].merge(races[['raceId','year']], on='raceId').year.max()}")


if __name__ == "__main__":
    main()
