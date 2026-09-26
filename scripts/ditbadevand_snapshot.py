#!/usr/bin/env python3
"""Gemmer et øjebliksbillede af ditbadevand.dk's risikotal for strande i Storkøbenhavn.

Bruges til korrelationsstudiet badevand.dk (flag) vs. ditbadevand.dk (risiko %).
Tilføjer én række pr. strand til data/ditbadevand/YYYY-MM.csv (UTC-måned).

Felter fra /api/badevand-risk (bekræftet 26/9-2026):
  bact, viral, algae  = "NU"-delrisici (0-1)
  samlet              = max(bact, viral, algae) = sidens "SAMLET FORURENINGSRISIKO"
  forecast            = "24H PROGNOSE" (0-1)
"""
import csv, gzip, io, json, os, sys, time, random, urllib.request
from datetime import datetime, timezone

BASE = "https://ditbadevand.dk"
# Storkøbenhavn: Vallensbæk - Taarbæk - Dragør (lat_min, lat_max, lon_min, lon_max)
BBOX = (55.55, 55.80, 12.40, 12.72)
OUT_DIR = "data/ditbadevand"
UA = "svoemme-data snapshot (privat studie; 1 kald/time)"

def get_json(path, attempts=4):
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(BASE + path, headers={
                "User-Agent": UA, "Accept": "application/json", "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(random.uniform(10, 30))
    raise RuntimeError(f"{path}: {last}")

def main():
    now = datetime.now(timezone.utc)
    geo = get_json("/vp3_badevand.geojson")
    names = {}
    for f in geo["features"]:
        lon, lat = f["geometry"]["coordinates"][:2]
        if BBOX[0] < lat < BBOX[1] and BBOX[2] < lon < BBOX[3]:
            names[f["properties"]["bathingwat"]] = f["properties"]["nametext"]

    risk = get_json("/api/badevand-risk")
    api_ts = datetime.fromtimestamp(risk["ts"] / 1000, timezone.utc)
    rows = []
    for b in risk["badevand"]:
        if b.get("id") not in names:
            continue
        parts = [b.get(k) for k in ("bact", "viral", "algae")]
        nums = [p for p in parts if isinstance(p, (int, float))]
        rnd = lambda v: "" if v is None else round(v, 4)
        rows.append({
            "fetched_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "api_ts_utc": api_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "id": b["id"], "name": names[b["id"]],
            "bact": rnd(parts[0]), "viral": rnd(parts[1]), "algae": rnd(parts[2]),
            "samlet": rnd(max(nums)) if nums else "",
            "forecast": rnd(b.get("forecast")),
            "confirm_reason": b.get("confirmReason") or "",
            "data_confidence": b.get("dataConfidence") if b.get("dataConfidence") is not None else "",
        })
    if not rows:
        print("Ingen strande fundet i området - API-format ændret?", file=sys.stderr)
        sys.exit(1)

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, now.strftime("%Y-%m") + ".csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        if new:
            w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} strande skrevet til {path} (api ts {api_ts:%H:%M}Z)")

if __name__ == "__main__":
    main()
