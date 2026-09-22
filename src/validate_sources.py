"""Cross-check the Ergast mirror's lap data against the live Jolpica-F1 API.

The analysis runs off a mirrored snapshot of the Ergast CSV dump, because ergast.com
itself is gone.  A mirror is only as trustworthy as its provenance, so this script
re-fetches the same races from Jolpica-F1 - the maintained successor API, an
independent service with its own database - and compares them record for record.

Only the races already cached by `ingest_laps.py` are checked, so this runs offline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "laps"
PROC = ROOT / "data" / "processed"


def main() -> None:
    races = pd.read_parquet(PROC / "races.parquet")
    laps = pd.read_parquet(PROC / "laps.parquet")
    drivers = pd.read_parquet(PROC / "drivers.parquet")
    ref = dict(zip(drivers.driverId, drivers.driverRef))

    files = sorted(CACHE.glob("laps_*.json"))
    if not files:
        print("no cached Jolpica races; run src/ingest_laps.py first")
        return

    rows, tot_a, tot_b, agree = [], 0, 0, 0
    for f in files:
        d = json.loads(f.read_text())
        year, rnd = d["year"], d["round"]
        r = races[(races.year == year) & (races["round"] == rnd)]
        if r.empty:
            continue
        rid = int(r.raceId.iloc[0])

        jol = {(int(ln), t["driverId"]): t["position"]
               for ln, tl in d["laps"].items() for t in tl}
        erg = {(int(l), ref.get(dv)): int(p) for l, dv, p in
               laps.loc[laps.raceId == rid, ["lap", "driverId", "position"]].to_numpy()}

        common = set(jol) & set(erg)
        same = sum(1 for k in common if jol[k] == erg[k])
        rows.append({"year": year, "round": rnd, "ergast": len(erg), "jolpica": len(jol),
                     "common": len(common), "position_match": same,
                     "match_rate": same / len(common) if common else float("nan")})
        tot_a += len(erg); tot_b += len(jol); agree += same

    df = pd.DataFrame(rows)
    common_tot = int(df["common"].sum())
    print(f"races compared              : {len(df)}")
    print(f"lap records, Ergast mirror  : {tot_a:,}")
    print(f"lap records, Jolpica API    : {tot_b:,}")
    print(f"(lap, driver) keys in both  : {common_tot:,}")
    print(f"positions identical         : {agree:,} ({agree/common_tot:.4%})")
    bad = df[df.match_rate < 1]
    print(f"races with any disagreement : {len(bad)}")
    if len(bad):
        print(bad.to_string(index=False))
    df.to_csv(PROC / "source_crosscheck.csv", index=False)
    print(f"\nwrote {PROC / 'source_crosscheck.csv'}")


if __name__ == "__main__":
    main()
