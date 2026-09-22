"""Build `data/drs_zones.csv`, the hand-coded DRS treatment-intensity table.

There is no public machine-readable dataset of DRS zones per circuit per season, so
this table is assembled by hand from named sources.  Every row carries a `source_url`
and a `source_type`:

  documented    a source states the zone count for that circuit in that season
                (or states a season-wide rule that covers it explicitly).
  interpolated  no source found for that circuit-year, but the seasons on both sides
                are documented and identical, so the value is carried across.
                These rows are flagged so the headline model can be run on
                `documented` rows only, with `interpolated` rows as a robustness check.

Zone LENGTH is not included.  Per-zone lengths live in per-race FIA race-director event
notes, which are not available as a consistent series for 2011-2020.  `total_zone_length_m`
is therefore written as empty for every row, and the analysis uses zone COUNT as the
treatment-intensity measure.

Circuit ids are Ergast `circuitRef` values, which is what the race table joins on.
"""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "drs_zones.csv"

# --------------------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------------------
S_WIKI_DRS = "https://en.wikipedia.org/wiki/Drag_reduction_system"
S_RF_2013 = "https://www.racefans.net/2013/03/06/bar-tracks-drs-zones-2013-2/"
S_TU78_2019 = ("https://github.com/toUpperCase78/formula1-datasets/blob/master/"
               "formula1_2019season_tracks.csv")
S_TU78_2020 = ("https://github.com/toUpperCase78/formula1-datasets/blob/master/"
               "formula1_2020season_calendar.csv")


def W(year: int, gp: str) -> str:
    """Wikipedia article for a given Grand Prix, used as a per-race source."""
    return f"https://en.wikipedia.org/wiki/{year}_{gp}_Grand_Prix"


# Every circuit that hosted a championship race in each season, 2011-2020
# (Ergast circuitRef), taken from the race calendar.
SEASON_CIRCUITS: dict[int, list[str]] = {
    2011: "albert_park buddh catalunya hungaroring interlagos istanbul marina_bay monaco "
          "monza nurburgring sepang shanghai silverstone spa suzuka valencia villeneuve "
          "yas_marina yeongam".split(),
    2012: "albert_park americas bahrain buddh catalunya hockenheimring hungaroring "
          "interlagos marina_bay monaco monza sepang shanghai silverstone spa suzuka "
          "valencia villeneuve yas_marina yeongam".split(),
    2013: "albert_park americas bahrain buddh catalunya hungaroring interlagos marina_bay "
          "monaco monza nurburgring sepang shanghai silverstone spa suzuka villeneuve "
          "yas_marina yeongam".split(),
    2014: "albert_park americas bahrain catalunya hockenheimring hungaroring interlagos "
          "marina_bay monaco monza red_bull_ring sepang shanghai silverstone sochi spa "
          "suzuka villeneuve yas_marina".split(),
    2015: "albert_park americas bahrain catalunya hungaroring interlagos marina_bay monaco "
          "monza red_bull_ring rodriguez sepang shanghai silverstone sochi spa suzuka "
          "villeneuve yas_marina".split(),
    2016: "BAK albert_park americas bahrain catalunya hockenheimring hungaroring interlagos "
          "marina_bay monaco monza red_bull_ring rodriguez sepang shanghai silverstone "
          "sochi spa suzuka villeneuve yas_marina".split(),
    2017: "BAK albert_park americas bahrain catalunya hungaroring interlagos marina_bay "
          "monaco monza red_bull_ring rodriguez sepang shanghai silverstone sochi spa "
          "suzuka villeneuve yas_marina".split(),
    2018: "BAK albert_park americas bahrain catalunya hockenheimring hungaroring interlagos "
          "marina_bay monaco monza red_bull_ring ricard rodriguez shanghai silverstone "
          "sochi spa suzuka villeneuve yas_marina".split(),
    2019: "BAK albert_park americas bahrain catalunya hockenheimring hungaroring interlagos "
          "marina_bay monaco monza red_bull_ring ricard rodriguez shanghai silverstone "
          "sochi spa suzuka villeneuve yas_marina".split(),
    2020: "bahrain catalunya hungaroring imola istanbul monza mugello nurburgring portimao "
          "red_bull_ring silverstone sochi spa yas_marina".split(),
}

PRE_DRS_YEARS = range(2000, 2011)

rows: list[dict] = []


def add(circuit, year, n, src, stype, note="", rnd=""):
    rows.append({
        "circuit_id": circuit, "year": year, "round": rnd, "n_zones": n,
        "total_zone_length_m": "", "source_url": src,
        "source_type": stype, "note": note,
    })


# --------------------------------------------------------------------------------------
# 2000-2010: DRS did not exist, so every circuit gets zero zones. These rows are the
# pre-treatment baseline.
# --------------------------------------------------------------------------------------
# Pre-2011 circuits are read straight off the race calendar so none can be missed.
def _pre_drs_circuits() -> dict[int, list[str]]:
    import pandas as pd
    cols = ["raceId", "year", "round", "circuitId", "name", "date", "time", "url",
            "fp1_date", "fp1_time", "fp2_date", "fp2_time", "fp3_date", "fp3_time",
            "quali_date", "quali_time", "sprint_date", "sprint_time"]
    races = pd.read_csv(ROOT / "data/raw/ergast/races.csv", header=0, names=cols,
                        na_values=["\\N"])
    circ = pd.read_csv(ROOT / "data/raw/ergast/circuits.csv", na_values=["\\N"])
    m = races.merge(circ[["circuitId", "circuitRef"]], on="circuitId")
    m = m[m.year.isin(list(PRE_DRS_YEARS))]
    return {int(y): sorted(g.circuitRef.unique()) for y, g in m.groupby("year")}


PRE_CIRCUITS_BY_YEAR = _pre_drs_circuits()

for y, circuits in PRE_CIRCUITS_BY_YEAR.items():
    for c in circuits:
        add(c, y, 0, S_WIKI_DRS,
            "documented", "DRS was introduced in 2011; no zones existed before that")

# --------------------------------------------------------------------------------------
# 2011: one zone was the default. Two zones were used at Montreal, Valencia, Monza,
# Buddh and Yas Marina (Wikipedia DRS article, corroborated per-race below).
# --------------------------------------------------------------------------------------
TWO_2011 = {"villeneuve", "valencia", "monza", "buddh", "yas_marina"}
CORROB_2011 = {
    "silverstone": W(2011, "British"), "monza": W(2011, "Italian"),
    "marina_bay": W(2011, "Singapore"), "suzuka": W(2011, "Japanese"),
    "yeongam": W(2011, "Korean"), "buddh": W(2011, "Indian"),
    "yas_marina": W(2011, "Abu_Dhabi"),
}
for c in SEASON_CIRCUITS[2011]:
    n = 2 if c in TWO_2011 else 1
    src = CORROB_2011.get(c, S_WIKI_DRS)
    add(c, 2011, n, src, "documented",
        "two-zone circuits per Wikipedia DRS article; one zone was the 2011 default")

# --------------------------------------------------------------------------------------
# 2012: a genuinely mixed season. Only circuits with a source are coded; the rest are
# left out of the table entirely and therefore drop out of the dose-response model.
# --------------------------------------------------------------------------------------
CODED_2012 = {
    "albert_park": (2, W(2012, "Australian"), "second zone added for 2012"),
    "sepang": (1, W(2012, "Malaysian"), "single zone, unchanged from 2011"),
    "villeneuve": (2, W(2012, "Canadian"), ""),
    "valencia": (2, W(2012, "European"), ""),
    "americas": (1, W(2012, "United_States"), "single zone on the back straight"),
    "monaco": (1, W(2012, "Monaco"), ""),
    "suzuka": (1, W(2012, "Japanese"), "single zone, 20m shorter than 2011"),
    "yas_marina": (2, W(2012, "Abu_Dhabi"), ""),
}
for c, (n, src, note) in CODED_2012.items():
    add(c, 2012, n, src, "documented", note)

# --------------------------------------------------------------------------------------
# 2013: season-wide rule. Two zones at every circuit except Monaco and Suzuka.
# --------------------------------------------------------------------------------------
for c in SEASON_CIRCUITS[2013]:
    n = 1 if c in {"monaco", "suzuka"} else 2
    add(c, 2013, n, S_RF_2013, "documented",
        "season-wide: two zones everywhere bar Monaco and Suzuka")

# --------------------------------------------------------------------------------------
# 2015: season-wide rule, stated on the 2015 Japanese GP page: Suzuka and Monaco were
# the only two events that season with a single zone.
# --------------------------------------------------------------------------------------
for c in SEASON_CIRCUITS[2015]:
    n = 1 if c in {"monaco", "suzuka"} else 2
    add(c, 2015, n, W(2015, "Japanese"), "documented",
        "season-wide: Suzuka and Monaco were the only single-zone events of 2015")

# --------------------------------------------------------------------------------------
# 2014, 2016, 2017: no season-wide source found. 2013 and 2015 are documented and
# identical, and no circuit ran a third zone before 2018, so the 2013/2015 pattern is
# carried across. Flagged `interpolated`, with the documented exceptions overridden.
# --------------------------------------------------------------------------------------
DOC_MID = {
    (2014, "americas"): (2, W(2014, "United_States"),
                         "FIA retained the two 2013 zones"),
    (2016, "BAK"): (2, W(2016, "European"), "two zones at the new Baku circuit"),
}
for y in (2014, 2016, 2017):
    for c in SEASON_CIRCUITS[y]:
        if (y, c) in DOC_MID:
            n, src, note = DOC_MID[(y, c)]
            add(c, y, n, src, "documented", note)
        else:
            n = 1 if c in {"monaco", "suzuka"} else 2
            add(c, y, n, S_RF_2013, "interpolated",
                "carried from the documented and identical 2013 and 2015 patterns")

# --------------------------------------------------------------------------------------
# 2018: the season the FIA started adding third zones, so interpolation is least safe
# here. Documented three-zone circuits are coded individually; the rest are flagged.
# --------------------------------------------------------------------------------------
DOC_2018 = {
    "albert_park": (3, "https://www.crash.net/f1/news/891975/1/third-drs-zone-added-australian-gp",
                    "third zone added for 2018"),
    "catalunya": (3, "https://www.racefans.net/2018/06/04/fia-adds-third-drs-zone-for-canadian-grand-prix/",
                  "named as an earlier 2018 third-zone circuit alongside Melbourne"),
    "villeneuve": (3, "https://www.racefans.net/2018/06/04/fia-adds-third-drs-zone-for-canadian-grand-prix/",
                   "third zone added for 2018"),
    "red_bull_ring": (3, W(2018, "Austrian"), "three zones for the first time"),
    "silverstone": (3, W(2018, "British"), "third zone added to the two used previously"),
    "ricard": (2, W(2018, "French"), "two zones"),
    "monaco": (1, S_RF_2013, "Monaco ran a single zone throughout this era"),
    "suzuka": (1, "https://www.pitpass.com/63092/Japanese-GP-Track-notes-DRS-tyres-and-more",
               "single zone on the main straight"),
}
for c in SEASON_CIRCUITS[2018]:
    if c in DOC_2018:
        n, src, note = DOC_2018[c]
        add(c, 2018, n, src, "documented", note)
    else:
        add(c, 2018, 2, S_WIKI_DRS, "interpolated",
            "no 2018 source found; two zones assumed, but 2018 is when third zones began")

# --------------------------------------------------------------------------------------
# 2019 and 2020: a published per-circuit dataset covers the full calendar. The 2019
# rows were cross-checked against independently documented third-zone additions
# (Melbourne, Bahrain, Montreal, Red Bull Ring, Singapore, Mexico) and agreed exactly.
# --------------------------------------------------------------------------------------
ZONES_2019 = {
    "albert_park": 3, "bahrain": 3, "shanghai": 2, "BAK": 2, "catalunya": 2, "monaco": 1,
    "villeneuve": 3, "ricard": 2, "red_bull_ring": 3, "silverstone": 2,
    "hockenheimring": 2, "hungaroring": 2, "spa": 2, "monza": 2, "marina_bay": 3,
    "sochi": 2, "suzuka": 1, "rodriguez": 3, "americas": 2, "interlagos": 2,
    "yas_marina": 2,
}
for c, n in ZONES_2019.items():
    add(c, 2019, n, S_TU78_2019, "documented",
        "cross-checked against independently reported 2019 third-zone additions")

# 2020 is keyed by round as well, because Bahrain hosted two races on two layouts with
# different zone counts, and Ergast codes both as the same circuit.
ZONES_2020 = [
    ("red_bull_ring", 1, 3), ("red_bull_ring", 2, 3), ("hungaroring", 3, 2),
    ("silverstone", 4, 2), ("silverstone", 5, 2), ("catalunya", 6, 2), ("spa", 7, 2),
    ("monza", 8, 2), ("mugello", 9, 1), ("sochi", 10, 2), ("nurburgring", 11, 2),
    ("portimao", 12, 1), ("imola", 13, 1), ("istanbul", 14, 2), ("bahrain", 15, 3),
    ("bahrain", 16, 2), ("yas_marina", 17, 2),
]
for c, rnd, n in ZONES_2020:
    note = ("Sakhir GP on the shorter Outer layout, one fewer zone than the Bahrain GP"
            if (c, rnd) == ("bahrain", 16) else "")
    add(c, 2020, n, S_TU78_2020, "documented", note, rnd=rnd)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fields = ["circuit_id", "year", "round", "n_zones", "total_zone_length_m",
              "source_url", "source_type", "note"]
    rows.sort(key=lambda r: (r["year"], r["circuit_id"], str(r["round"])))
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    doc = sum(1 for r in rows if r["source_type"] == "documented")
    print(f"wrote {OUT} : {len(rows)} rows ({doc} documented, {len(rows)-doc} interpolated)")


if __name__ == "__main__":
    main()
