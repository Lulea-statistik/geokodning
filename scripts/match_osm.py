#!/usr/bin/env python3
"""Offline OSM-address register matching; not a Nominatim geocoding test."""
import argparse, csv, json, re, unicodedata, collections
from pathlib import Path
import osmium
from openpyxl import load_workbook

# Broad search region, NOT the administrative municipal boundary.
LAT_MIN, LAT_MAX, LON_MIN, LON_MAX = 65.25, 66.35, 20.85, 24.10

def norm(s):
    s=unicodedata.normalize("NFKC",str(s or "")).casefold()
    return re.sub(r"\s+"," ",s).strip().replace("‐","-").replace("–","-")

def parse(s):
    s=re.sub(r"\s+(?:lgh\s*\d{4}|\d+\s*tr|bv|vån\s*\d+)\s*$","",str(s or ""),flags=re.I).strip()
    m=re.match(r"^(.+?)\s+(\d+[a-zåäö]?)$",s,re.I)
    return (norm(m.group(1)),norm(m.group(2))) if m else None

def inputs(path):
    wb=load_workbook(path,read_only=True,data_only=True)
    ws=wb["Unika adresser"]
    ws.reset_dimensions()
    itr=ws.iter_rows(values_only=True)
    header=next(itr)
    idx=header.index("Adress för OSM-matchning")
    original_idx=header.index("Adress för geokodning")
    for row in itr:
        if len(row)>idx and row[idx]:
            yield str(row[original_idx]),str(row[idx])

class AddressHandler(osmium.SimpleHandler):
    def __init__(self,keys):
        super().__init__()
        self.keys=keys
        self.matches=collections.defaultdict(list)
    def check(self, o, geom):
        street=o.tags.get("addr:street"); house=o.tags.get("addr:housenumber")
        if not street or not house: return
        try:
            if o.type=="n":
                p=o.location
            else:
                pts=[n.location for n in o.nodes if n.location.valid()]
                if not pts:return
                lat=sum(p.lat for p in pts)/len(pts);lon=sum(p.lon for p in pts)/len(pts)
                class P:pass
                p=P();p.lat=lat;p.lon=lon
            if not (LAT_MIN<=p.lat<=LAT_MAX and LON_MIN<=p.lon<=LON_MAX):return
        except (RuntimeError,ValueError,ZeroDivisionError):return
        for h in re.split(r"\s*;\s*",house):
            key=(norm(street),norm(h))
            if key not in self.keys: continue
            city=str(o.tags.get("addr:city",""))
            postcode=str(o.tags.get("addr:postcode",""))
            self.matches[key].append(dict(osm_id=o.type+str(o.id),lat=round(p.lat,7),lon=round(p.lon,7),city=city,postcode=postcode))
    def node(self,o):self.check(o,"node")
    def way(self,o):self.check(o,"way")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True)
    ap.add_argument("--pbf",required=True)
    ap.add_argument("--out",default="resultat")
    a=ap.parse_args()
    addresses=list(inputs(a.input))
    keys={p for _,s in addresses if (p:=parse(s))}
    handler=AddressHandler(keys)
    handler.apply_file(a.pbf,locations=True,idx="flex_mem")
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    cols=["originaladress","sokadress","status","antal_osm_kandidater","latitude_epsg4326","longitude_epsg4326","osm_id","osm_city","osm_postcode"]
    counts=collections.Counter()
    with (out/"osm_matchning.csv").open("w",newline="",encoding="utf-8-sig") as f, (out/"osm_kandidater.csv").open("w",newline="",encoding="utf-8-sig") as g:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
        k=csv.DictWriter(g,fieldnames=["sokadress","osm_id","latitude_epsg4326","longitude_epsg4326","osm_city","osm_postcode"]);k.writeheader()
        for original,s in addresses:
            key=parse(s)
            candidates=handler.matches.get(key,[]) if key else []
            uniq={c["osm_id"]:c for c in candidates}
            candidates=list(uniq.values())
            for c in candidates:
                k.writerow(dict(sokadress=s,osm_id=c["osm_id"],latitude_epsg4326=c["lat"],longitude_epsg4326=c["lon"],osm_city=c["city"],osm_postcode=c["postcode"]))
            if key is None: status="Format behöver granskas"
            elif not candidates: status="Ingen OSM-adressträff"
            elif len(candidates)>1: status="Flera OSM-kandidater"
            elif norm(candidates[0]["city"]) not in ("luleå","lulea"): status="Adressmatchning – ort ej verifierad"
            else: status="En OSM-adresskandidat (Luleå)"
            counts[status]+=1
            c=candidates[0] if len(candidates)==1 else {}
            w.writerow(dict(originaladress=original,sokadress=s,status=status,antal_osm_kandidater=len(candidates),latitude_epsg4326=c.get("lat",""),longitude_epsg4326=c.get("lon",""),osm_id=c.get("osm_id",""),osm_city=c.get("city",""),osm_postcode=c.get("postcode","")))
    summary={"antal_unika_adresser":len(addresses),"status":dict(counts),"metod":"OSM addr:street/addr:housenumber inom grov sökruta. Ej Nominatim-verifiering.","crs":"EPSG:4326"}
    (out/"sammanfattning.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
