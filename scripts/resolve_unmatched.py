#!/usr/bin/env python3
"""Careful second pass for remaining unmatched Lulea search addresses.

Only resolve duplicate exact OSM candidates that are essentially co-located
(max separation <=100m); alternatives are not guessed. No external API calls.
All coordinates remain OSM EPSG:4326 verified inside municipality upstream.
"""
import argparse,csv,collections,json,math
from pathlib import Path

def rows(path):
    with open(path,encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

def distance(a,b):
    la1,lo1=map(math.radians,(float(a["latitude_epsg4326"]),float(a["longitude_epsg4326"])))
    la2,lo2=map(math.radians,(float(b["latitude_epsg4326"]),float(b["longitude_epsg4326"])))
    q=math.sin((la2-la1)/2)**2+math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return 12742000*math.atan2(math.sqrt(q),math.sqrt(1-q))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",default="resultat")
    args=ap.parse_args()
    out=Path(args.out)
    master=rows(out/"osm_samlat_per_adress.csv")
    cands=collections.defaultdict(list)
    for r in rows(out/"osm_kandidater_geografi.csv"):
        if r["inom_lulea_kommun_osm"]=="ja" and r["latitude_epsg4326"] and r["longitude_epsg4326"]:
            cands[r["sokadress"]].append(r)
    new=[]
    changed=[]
    remaining=[]
    distribution=collections.Counter()
    for r in master:
        row=dict(r)
        if row["kategori"]=="Flera exakta OSM-kandidater - ingen vald":
            unique={(float(c["latitude_epsg4326"]),float(c["longitude_epsg4326"])):c for c in cands[row["sokadress"]]}
            candidates=list(unique.values())
            if not candidates:
                distribution["inga giltiga kandidater inom kommun"]+=1
            else:
                representative=sorted(candidates,key=lambda c:(c["osm_id"],c["latitude_epsg4326"]))[0]
                maxspread=max(distance(a,b) for a in candidates for b in candidates)
                if maxspread<=100:
                    row["kategori"]="Flera exakta kandidater, samlokaliserade"
                    row["latitude_epsg4326"]=representative["latitude_epsg4326"]
                    row["longitude_epsg4326"]=representative["longitude_epsg4326"]
                    row["osm_id"]=representative["osm_id"]
                    row["kalltyp"]="OSM exakta adresskandidater inom 100 m"
                    row["inom_lulea_kommun_osm"]="ja"
                    row["anmärkning"]=f"{len(candidates)} unika kandidatpositioner, max {maxspread:.1f} meter mellan dem. Representativ OSM-punkt, inte verifierad byggnad."
                    changed.append({"sokadress":row["sokadress"],"antal_kandidater":len(candidates),"max_avstand_m":round(maxspread,1),"osm_id":row["osm_id"]})
                    distribution["samlokaliserade högst 100 m"]+=1
                else:
                    distribution["spridda över 100 m, ej automatiskt valda"]+=1
        if not row["latitude_epsg4326"]:
            remaining.append(row)
        new.append(row)
    assert len(master)==len(new)
    assert all(c["sokadress"] in {r["sokadress"] for r in master} for c in changed)
    fields=list(master[0])
    with (out/"osm_samlat_per_adress_kompletterat.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(new)
    with (out/"osm_saknar_position_efter_komplettering.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(remaining)
    with (out/"osm_samlokaliserade_kandidater.csv").open("w",encoding="utf-8-sig",newline="") as f:
        flds=["sokadress","antal_kandidater","max_avstand_m","osm_id"]
        w=csv.DictWriter(f,fieldnames=flds);w.writeheader();w.writerows(changed)
    summary={
      "unika_sokadresser":len(new),"tidigare_utan_position":sum(not r["latitude_epsg4326"] for r in master),
      "nya_samlokaliserade":len(changed),
      "med_position_efter":sum(bool(r["latitude_epsg4326"]) for r in new),
      "utan_position_efter":len(remaining),
      "orsaker_for_flera_kandidater":dict(distribution),
      "forsta_tio_fortsatt_utan_position":[r["sokadress"] for r in sorted(remaining,key=lambda r:r["sokadress"])[:10]],
      "crs":"EPSG:4326",
      "reservation":"Samlokalisering visar endast att OSM-kandidaterna ligger nära; bygger inte på verifierad adresspunkt. Övriga adresser saknar lägesbestämning och tilldelas ingen godtycklig kommunpunkt."
    }
    (out/"osm_komplettering_sammanfattning.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=="__main__":
    main()
