#!/usr/bin/env python3
"""Spatially audit existing address candidates against the OSM Lulea municipal boundary.
No inferred CRS: input CSV coordinates are explicitly EPSG:4326; OSM lon/lat is WGS84.
"""
import argparse, collections, csv, json
from pathlib import Path
import osmium
from shapely.geometry import Point
from shapely import wkb
from shapely.validation import explain_validity

class MunicipalBoundary(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.shapes = []
        self.factory = osmium.geom.WKBFactory()

    def area(self, obj):
        tags = obj.tags
        if tags.get("boundary") != "administrative" or tags.get("admin_level") != "7":
            return
        name = tags.get("name", "")
        if name.casefold().strip() not in ("luleå", "luleå kommun", "lulea", "lulea kommun"):
            return
        try:
            shape = wkb.loads(self.factory.create_multipolygon(obj))
            # Region sanity bounds only, not an asserted boundary.
            xmin, ymin, xmax, ymax = shape.bounds
            if shape.is_empty or not shape.is_valid or not (20 < xmin < 25 and 64 < ymin < 67 and 20 < xmax < 25 and 64 < ymax < 67):
                print("Rejected candidate boundary", name, explain_validity(shape))
                return
            self.shapes.append((name, shape))
        except Exception as exc:
            print("Cannot construct OSM municipal boundary:", type(exc).__name__, str(exc)[:200])

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pbf", required=True)
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    boundary = MunicipalBoundary()
    try:
        boundary.apply_file(args.pbf, locations=True, idx="flex_mem")
    except Exception as exc:
        print("Could not assemble OSM boundary:", type(exc).__name__, str(exc)[:200])
    polygon = boundary.shapes[0][1] if len(boundary.shapes) == 1 else None
    reason = ("OSM boundary assembled and valid" if polygon is not None else
              "Municipality boundary missing or ambiguous; spatial results not verified")
    print(reason)

    counts = collections.Counter()
    inp = Path(args.input)
    with inp.open(encoding="utf-8-sig", newline="") as f, (out / "osm_matchning_geografi.csv").open("w", encoding="utf-8-sig", newline="") as g:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or []) + ["inom_lulea_kommun_osm", "geografisk_bedomning", "gransmodell"]
        writer = csv.DictWriter(g, fieldnames=fields)
        writer.writeheader()
        for rec in reader:
            lat = rec.get("latitude_epsg4326", "")
            lon = rec.get("longitude_epsg4326", "")
            if not lat or not lon:
                status = "Ingen entydig koordinat"
                inside = ""
            elif polygon is None:
                status = "Kommungrans saknas - ej verifierad"
                inside = ""
            else:
                try:
                    point = Point(float(lon), float(lat))
                    is_inside = polygon.covers(point)
                    inside = "ja" if is_inside else "nej"
                    status = "Inom kommungrans" if is_inside else "Utanfor kommungrans"
                except (ValueError, TypeError):
                    status = "Ogiltig koordinat"; inside = ""
            rec["inom_lulea_kommun_osm"] = inside
            rec["geografisk_bedomning"] = status
            rec["gransmodell"] = "OSM admin_level=7 WGS84" if polygon else "saknas"
            counts[status] += 1
            writer.writerow(rec)
    summary = {
        "input": str(inp), "boundary_source": "OSM Sweden PBF; boundary=administrative; admin_level=7",
        "expected_municipality": "Luleå kommun (2580)", "geometry_crs": "EPSG:4326",
        "boundary_status": reason, "number_of_matching_polygons": len(boundary.shapes),
        "spatial_status": dict(counts),
        "caveat": "Municipal spatial position is not proof of correct street/house number or Nominatim geocoding. Multiple candidates have no chosen coordinate."
    }
    (out / "geografisk_sammanfattning.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
if __name__ == "__main__":
    main()
