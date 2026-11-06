#!/usr/bin/env python3
"""Audit saved Nominatim pilot against the actual OSM municipal polygon.

Reads the EPSG:4326 lat/lon values returned by Nominatim.
Does not issue Nominatim requests or certify building placement.
"""
import argparse
import collections
import csv
import json
from pathlib import Path

from shapely.geometry import Point
from verify_geo import MunicipalBoundary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--pbf", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    boundary = MunicipalBoundary()
    boundary.apply_file(args.pbf, locations=True, idx="flex_mem")
    if len(boundary.shapes) != 1:
        raise SystemExit(f"Expected exactly one validated Luleå municipality boundary, got {len(boundary.shapes)}")
    municipal_polygon = boundary.shapes[0][1]
    with open(args.input, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    statuses = collections.defaultdict(collections.Counter)
    by_address = collections.defaultdict(dict)
    for row in rows:
        variant = row["variant"]
        lat, lon = row.get("latitude_epsg4326"), row.get("longitude_epsg4326")
        if not lat or not lon:
            spatial = "ingen koordinat"
        else:
            try:
                pt = Point(float(lon), float(lat))
                spatial = "inom Luleå kommun" if municipal_polygon.covers(pt) else "utanför Luleå kommun"
            except (TypeError, ValueError):
                spatial = "ogiltig koordinat"
        row["geografisk_status"] = spatial
        row["adress_och_geografi"] = (
            "exakt textmatch och inom kommun"
            if row["status"] == "Exakt gatunamn och husnummer i svar" and spatial == "inom Luleå kommun"
            else "inte verifierad på både adress och kommun"
        )
        statuses[variant][row["adress_och_geografi"]] += 1
        statuses[variant][spatial] += 1
        by_address[row["adress"]][variant] = row

    with (out / "nominatim_pilot_geografi.csv").open("w", encoding="utf-8-sig", newline="") as f:
        fields = list(rows[0]) if rows else []
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    pairwise = collections.Counter()
    paired = []
    a_key, b_key = "utan ortstillägg", "med Luleå, Sweden"
    for address, variants in sorted(by_address.items()):
        a, b = variants.get(a_key), variants.get(b_key)
        if not a or not b:
            verdict = "ofullständigt par"
        else:
            ea = a["adress_och_geografi"] == "exakt textmatch och inom kommun"
            eb = b["adress_och_geografi"] == "exakt textmatch och inom kommun"
            if ea and not eb:
                verdict = "utan ort bättre"
            elif eb and not ea:
                verdict = "med ort bättre"
            elif ea and eb:
                verdict = "båda exakt och inom"
            else:
                verdict = "ingen variant exakt och inom"
        pairwise[verdict] += 1
        paired.append({
            "adress": address, "parvis_resultat": verdict,
            "status_utan_ort": a["status"] if a else "",
            "geografi_utan_ort": a["geografisk_status"] if a else "",
            "status_med_ort": b["status"] if b else "",
            "geografi_med_ort": b["geografisk_status"] if b else "",
        })

    with (out / "nominatim_parvis_jamforelse.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(paired[0]) if paired else ["adress", "parvis_resultat"])
        writer.writeheader()
        writer.writerows(paired)

    summary = {
        "antal_testade_adresser": len(by_address),
        "kommunpolygon": "OSM admin_level=7, en valid polygon identifierad",
        "koordinatsystem": "EPSG:4326 (Nominatim latitude, longitude)",
        "per_variant": {k: dict(v) for k, v in statuses.items()},
        "parvis_resultat": dict(pairwise),
        "tolkning": "Textmatch samt punkt inom kommun är nödvändiga men ej tillräckliga villkor för korrekt geokodning till rätt byggnad.",
        "urval": "12 deterministiskt valda adresser; inte statistiskt representativt."
    }
    (out / "nominatim_geo_sammanfattning.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
