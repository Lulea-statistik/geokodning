#!/usr/bin/env python3
"""Approximate Lulea geocoding fallback against OSM addr:street, NEVER an exact address match.

OSM coordinates WGS84/EPSG:4326; municipal polygon from OSM admin_level=7.
Only unmatched addresses get fallbacks. No arbitrary street-number substitution in
reference data. Street medoid is a rough location, not a building position.
"""
import argparse, collections, csv, json, math, re
from pathlib import Path
import osmium
from shapely.geometry import Point
from verify_geo import MunicipalBoundary
from match_osm import norm, parse, LAT_MIN, LAT_MAX, LON_MIN, LON_MAX

def haversine(a, b):
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2-lat1, lon2-lon1
    x = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371000*2*math.atan2(math.sqrt(x), math.sqrt(1-x))

def number(s):
    m = re.match(r"^(\d+)", str(s or ""))
    return int(m.group(1)) if m else None

class StreetIndex(osmium.SimpleHandler):
    def __init__(self, wanted, polygon):
        super().__init__()
        self.wanted = wanted
        self.polygon = polygon
        self.data = collections.defaultdict(dict)
    def add(self, obj, typ):
        street = norm(obj.tags.get("addr:street", ""))
        if street not in self.wanted:
            return
        hn = str(obj.tags.get("addr:housenumber", "")).strip()
        if not hn:
            return
        try:
            if typ == "n":
                if not obj.location.valid(): return
                lat, lon = obj.location.lat, obj.location.lon
            else:
                pts = [(n.location.lat, n.location.lon) for n in obj.nodes if n.location.valid()]
                if not pts: return
                lat = sum(x for x,_ in pts)/len(pts)
                lon = sum(y for _,y in pts)/len(pts)
            if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
                return
            if not self.polygon.covers(Point(lon,lat)):
                return
        except (RuntimeError, ValueError, OverflowError):
            return
        for h in re.split(r"\s*;\s*",hn):
            self.data[street][typ+str(obj.id)+":"+h] = {
                "lat":lat,"lon":lon,"house":h,"osm_id":typ+str(obj.id)
            }
    def node(self,o): self.add(o,"n")
    def way(self,o): self.add(o,"w")

def estimate(key, candidates):
    if not candidates: return None
    street, house = key
    target = number(house)
    numeric = [(abs(number(c["house"])-target), c) for c in candidates
               if target is not None and number(c["house"]) is not None]
    nearby = [(d,c) for d,c in numeric if d <= 10]
    if nearby:
        best_distance = min(d for d,_ in nearby)
        best = [c for d,c in nearby if d == best_distance]
        # A same street name may cover distinct villages: do not silently pick.
        spread = max((haversine((best[0]["lat"],best[0]["lon"]),(c["lat"],c["lon"]))
                      for c in best),default=0)
        if spread <= 750:
            c = sorted(best,key=lambda x:x["osm_id"])[0]
            return ("Närliggande husnummer",c,best_distance,spread)
    # Only use a street proxy when candidate street-address points cluster locally.
    # Using a medoid avoids averaging coordinates outside the actual street.
    if len(candidates) > 1:
        center = min(candidates,key=lambda a:sum(haversine((a["lat"],a["lon"]),(b["lat"],b["lon"])) for b in candidates))
        spread = max(haversine((center["lat"],center["lon"]),(c["lat"],c["lon"])) for c in candidates)
    else:
        center,spread = candidates[0],0
    if spread <= 1500:
        return ("Ungefärlig gatuposition",center,"",round(spread))
    return ("Flera geografiskt spridda gatukandidater",None,"",round(spread))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--pbf",required=True)
    p.add_argument("--input",required=True)
    p.add_argument("--out",default="resultat")
    args=p.parse_args()
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    with open(args.input,encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    target_rows=[r for r in rows if r["status"]=="Ingen OSM-adressträff" and parse(r["sokadress"])]
    wanted={parse(r["sokadress"])[0] for r in target_rows}
    boundary=MunicipalBoundary()
    boundary.apply_file(args.pbf,locations=True,idx="flex_mem")
    if len(boundary.shapes)!=1: raise SystemExit("No unique valid Lulea municipality polygon - refusing approximations")
    polygon=boundary.shapes[0][1]
    index=StreetIndex(wanted,polygon)
    index.apply_file(args.pbf,locations=True,idx="flex_mem")
    fields=["sokadress","ursprunglig_status","reservmetod","osakadress_husnummer",
      "matchat_osm_husnummer","husnummer_avvikelse","osm_id","latitude_epsg4326",
      "longitude_epsg4326","gatukandidater_antal","gatukluster_spridning_m",
      "inom_lulea_kommun_osm","positionsprecision"]
    totals=collections.Counter()
    unique= {}
    for row in target_rows:
        address=row["sokadress"]
        if address in unique:continue
        key=parse(address)
        candidates=list(index.data.get(key[0],{}).values())
        result=estimate(key,candidates)
        if result is None:
            method,choice,diff,spread="Ingen OSM-gatuadress inom kommunen",None,"",""
        else:method,choice,diff,spread=result
        totals[method]+=1
        unique[address]={"sokadress":address,"ursprunglig_status":row["status"],
          "reservmetod":method,"osakadress_husnummer":key[1],
          "matchat_osm_husnummer":choice["house"] if choice else "",
          "husnummer_avvikelse":diff,
          "osm_id":choice["osm_id"] if choice else "",
          "latitude_epsg4326":round(choice["lat"],7) if choice else "",
          "longitude_epsg4326":round(choice["lon"],7) if choice else "",
          "gatukandidater_antal":len(candidates),"gatukluster_spridning_m":spread,
          "inom_lulea_kommun_osm":"ja" if choice else "",
          "positionsprecision":"ungefärlig; inte adresspunkt" if choice else "saknas"}
    with (out/"osm_reservgeokodning.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(unique.values())
    # Never imply that a nearby house has the same address as the reference.
    summary={"adresser_utan_direkt_traff_i_indata":len(target_rows),
      "unika_sokadresser_med_reservprov":len(unique),
      "reservutfall":dict(totals),
      "med_ungefar_lage":sum(v for k,v in totals.items() if k in ("Närliggande husnummer","Ungefärlig gatuposition")),
      "geografisk_avgransning":"OSM Luleå kommungräns admin_level=7",
      "crs":"EPSG:4326",
      "reservation":"Approximate location only, not exact address geocoding. Some street names may occur in distinct localities; clustered candidate threshold reduces but does not eliminate false associations."}
    (out/"osm_reservsammanfattning.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
