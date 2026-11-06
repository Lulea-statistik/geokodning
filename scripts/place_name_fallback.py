#!/usr/bin/env python3
"""OSM place-name fallback for unmatched Lulea address strings.

Remove only trailing house number/suffix, then match the remaining exact name
against named OSM place/locality and selected named geographical features.
All source coordinates are WGS84 EPSG:4326. Never interpret result as an
address or a parcel. Resolve only unique/co-located candidates inside Lulea.
"""
import argparse,collections,csv,json,math,re
from pathlib import Path
import osmium
from shapely.geometry import Point
from match_osm import norm
from verify_geo import MunicipalBoundary

PLACE_TYPES={"city","town","village","hamlet","isolated_dwelling","locality","suburb","neighbourhood","quarter","islet","island","farm"}
NATURAL_TYPES={"island","islet","peninsula","cape","bay","water"}
LANDUSE_TYPES={"residential"}
def strip_house(s):
    # Original may include floor/apartment designations; remove those first.
    s=re.sub(r"\s+(?:lgh\s*\d{4}|\d+(?:\s*1/2)?\s*tr|bv|vån\s*\d+)\s*$","",s,flags=re.I)
    return re.sub(r"\s+\d+(?:\s*[a-zåäö]{1,2})?\s*$","",s,flags=re.I).strip()

def metric(a,b):
    lon1,lat1=a;lon2,lat2=b
    r1=math.radians(lat1);r2=math.radians(lat2)
    d1=r2-r1;d2=math.radians(lon2-lon1)
    k=math.sin(d1/2)**2+math.cos(r1)*math.cos(r2)*math.sin(d2/2)**2
    return 12742000*math.atan2(math.sqrt(k),math.sqrt(1-k))

class FindNames(osmium.SimpleHandler):
    def __init__(self,wanted,polygon):
        super().__init__()
        self.wanted=wanted
        self.polygon=polygon
        self.items=collections.defaultdict(dict)
    def check(self,o,kind):
        name=str(o.tags.get("name",""))
        key=norm(name)
        if key not in self.wanted: return
        ptype=str(o.tags.get("place",""))
        natural=str(o.tags.get("natural",""))
        landuse=str(o.tags.get("landuse",""))
        if ptype not in PLACE_TYPES and natural not in NATURAL_TYPES and landuse not in LANDUSE_TYPES:
            return
        try:
            if kind=="n":
                if not o.location.valid():return
                lon,lat=o.location.lon,o.location.lat
            else:
                vertices=[(x.location.lon,x.location.lat) for x in o.nodes if x.location.valid()]
                if not vertices:return
                # A representative OSM geometry vertex; never inferred building position.
                lon,lat=vertices[len(vertices)//2]
            if not self.polygon.covers(Point(lon,lat)):return
        except (RuntimeError,ValueError,OverflowError):
            return
        label=("place:"+ptype if ptype in PLACE_TYPES else
               "natural:"+natural if natural in NATURAL_TYPES else "landuse:"+landuse)
        c={"osm_id":kind+str(o.id),"lon":lon,"lat":lat,"osm_name":name,"osm_typ":label}
        self.items[key][c["osm_id"]]=c
    def node(self,o):self.check(o,"n")
    def way(self,o):self.check(o,"w")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--pbf",required=True)
    ap.add_argument("--input",required=True)
    ap.add_argument("--out",default="resultat")
    args=ap.parse_args()
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    with open(args.input,encoding="utf-8-sig",newline="") as f:
        original=list(csv.DictReader(f))
    remaining=[r for r in original if not r.get("latitude_epsg4326")]
    names={r["sokadress"]:strip_house(r["sokadress"]) for r in remaining}
    boundary=MunicipalBoundary()
    boundary.apply_file(args.pbf,locations=True,idx="flex_mem")
    if len(boundary.shapes)!=1:raise SystemExit("Missing unique Lulea municipal boundary")
    lookup=FindNames({norm(x) for x in names.values() if x},boundary.shapes[0][1])
    lookup.apply_file(args.pbf,locations=True,idx="flex_mem")
    records=[];outcomes=collections.Counter()
    updated=[];used={}
    for row in original:
        r=dict(row)
        if r.get("latitude_epsg4326"):
            updated.append(r)
            continue
        address=r["sokadress"]
        sought=names[address]
        candidates=list(lookup.items.get(norm(sought),{}).values())
        if not candidates:
            status="Ingen namngiven plats i OSM"
        else:
            # Co-located place nodes and polygon centroids/vertices can differ.
            maxspread=max(metric((a["lon"],a["lat"]),(b["lon"],b["lat"]))
                          for a in candidates for b in candidates)
            if maxspread<=1000:
                status="Namngiven plats inom kommunen"
                point=sorted(candidates,key=lambda x:(not x["osm_typ"].startswith("place:"),x["osm_id"]))[0]
                r.update({
                    "kategori":"Reserv, namngiven plats utan husnummer",
                    "latitude_epsg4326":round(point["lat"],7),
                    "longitude_epsg4326":round(point["lon"],7),
                    "kalltyp":"OSM "+point["osm_typ"],
                    "osm_id":point["osm_id"],
                    "inom_lulea_kommun_osm":"ja",
                    "anmärkning":f"Matchat platsnamn {sought!r} efter borttaget husnummer; max kandidatspridning {maxspread:.0f} m. EJ adressposition."
                })
                used[address]=point
            else:
                status="Flera geografiskt spridda namnlika platser"
        outcomes[status]+=1
        records.append({
          "sokadress":address,"platsnamn_sokt":sought,
          "antal_osm_kandidater":len(candidates),"status":status,
          "osm_typ":used.get(address,{}).get("osm_typ",""),
          "osm_id":used.get(address,{}).get("osm_id",""),
          "latitude_epsg4326":r.get("latitude_epsg4326",""),
          "longitude_epsg4326":r.get("longitude_epsg4326",""),
          "precision":"ungefärlig plats, inte adress" if address in used else "saknas"
        })
        updated.append(r)
    assert len(updated)==len(original)
    cols=list(original[0])
    with (out/"osm_master_efter_platsnamn.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(updated)
    with (out/"osm_platsnamn_resultat.csv").open("w",newline="",encoding="utf-8-sig") as f:
        cols2=list(records[0]) if records else ["sokadress","status"]
        w=csv.DictWriter(f,fieldnames=cols2);w.writeheader();w.writerows(records)
    leftover=[r for r in updated if not r.get("latitude_epsg4326")]
    with (out/"osm_aterstar_utan_position.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(leftover)
    summary={
      "utgangslage_utan_position":len(remaining),
      "nytt_lage_via_platsnamn":len(used),
      "aterstar_utan_position":len(leftover),
      "totalt_med_position":len(updated)-len(leftover),
      "totalt_unika_sokadresser":len(updated),
      "status":dict(outcomes),
      "exempel_tio_nya_traf far".replace(" ",""):[r["sokadress"] for r in records if r["sokadress"] in used][:10],
      "exempel_tio_aterstar":[r["sokadress"] for r in leftover[:10]],
      "crs":"EPSG:4326",
      "viktigt":"Exakt namnlika OSM-platser inom kommunen, ej geokodade hus/adresser. Ingen Nominatim/extern API."
    }
    (out/"osm_platsnamn_sammanfattning.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
