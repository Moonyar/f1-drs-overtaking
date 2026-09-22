"""Fetch lap-by-lap positions from the Jolpica-F1 API, one cached JSON file per race.

The analysis itself runs off the Ergast CSV mirror (see ingest.py). This script pulls
the same races from Jolpica-F1, the maintained successor to the Ergast API, so that
validate_sources.py can check the mirror against an independent source.

API behaviour this is written around:
  * ``limit`` is capped at 100 server-side, and one race is ~1000-1100 lap records,
    so a race takes ~11 requests.
  * ~1.7 req/s is sustainable; there is also an undocumented hourly cap.

Every (year, round) is cached to its own file and skipped on rerun, and HTTP 429 or
5xx responses back off exponentially, so the script can be stopped and restarted.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "laps"
PROC = ROOT / "data" / "processed"

BASE = "https://api.jolpi.ca/ergast/f1/{year}/{rnd}/laps/"
PAGE = 100
SLEEP = 0.55          # ~1.8 req/s, just under the measured sustainable rate
MAX_RETRIES = 6


def race_rounds(year_min: int, year_max: int) -> list[tuple[int, int]]:
    """(year, round) pairs for championship races, read from the ingested race table."""
    races = pd.read_parquet(PROC / "races.parquet", columns=["year", "round"])
    races = races[races.year.between(year_min, year_max)]
    return sorted(set(zip(races.year.astype(int), races["round"].astype(int))))


def _get(session: requests.Session, url: str, params: dict) -> dict:
    """GET with exponential backoff on 429 / 5xx.  Raises on unrecoverable failure."""
    delay = 2.0
    for attempt in range(MAX_RETRIES):
        try:
            r = session.get(url, params=params, timeout=30)
        except requests.RequestException as exc:
            if attempt == MAX_RETRIES - 1:
                raise
            print(f"    network error {exc!r}, retry in {delay:.0f}s", flush=True)
            time.sleep(delay)
            delay *= 2
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504):
            # Honour Retry-After when present; otherwise back off exponentially.
            wait = float(r.headers.get("Retry-After", delay))
            print(f"    HTTP {r.status_code}, sleeping {wait:.0f}s", flush=True)
            time.sleep(wait + random.uniform(0, 1))
            delay = min(delay * 2, 900)
            continue
        r.raise_for_status()
    raise RuntimeError(f"giving up on {url} {params}")


def fetch_race(session: requests.Session, year: int, rnd: int) -> dict | None:
    """Page through every lap record for one race and return a compact dict."""
    url = BASE.format(year=year, rnd=rnd)
    laps: dict[int, list] = {}
    offset, total = 0, None
    while total is None or offset < total:
        data = _get(session, url, {"format": "json", "limit": PAGE, "offset": offset})
        md = data["MRData"]
        total = int(md["total"])
        if total == 0:
            return None
        races = md["RaceTable"]["Races"]
        if not races:
            break
        for lap in races[0].get("Laps", []):
            n = int(lap["number"])
            laps.setdefault(n, []).extend(
                {"driverId": t["driverId"], "position": int(t["position"]), "time": t["time"]}
                for t in lap["Timings"]
            )
        offset += PAGE
        time.sleep(SLEEP)
    return {
        "year": year,
        "round": rnd,
        "total_records": total,
        "laps": {str(k): v for k, v in sorted(laps.items())},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=2000)
    ap.add_argument("--end", type=int, default=2020)
    args = ap.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)
    todo = race_rounds(args.start, args.end)
    session = requests.Session()
    session.headers["User-Agent"] = "f1-drs-causal-analysis/1.0 (academic; contact via github)"

    done = skipped = failed = 0
    for year, rnd in todo:
        path = CACHE / f"laps_{year}_{rnd:02d}.json"
        if path.exists():
            skipped += 1
            continue
        try:
            payload = fetch_race(session, year, rnd)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {year} r{rnd}: {exc!r}", flush=True)
            failed += 1
            continue
        if payload is None:
            # A real race with no lap data upstream. Record the hole explicitly so a
            # rerun does not keep re-requesting it, and so coverage can be audited.
            path.with_suffix(".empty").write_text("no lap data returned by Jolpica\n")
            print(f"EMPTY {year} r{rnd}", flush=True)
            continue
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(payload))
        tmp.rename(path)  # atomic, so an interrupted run never leaves a partial file
        done += 1
        print(f"ok {year} r{rnd:02d}  laps={len(payload['laps'])} recs={payload['total_records']}",
              flush=True)

    print(f"\ndone={done} cached_already={skipped} failed={failed} target={len(todo)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
