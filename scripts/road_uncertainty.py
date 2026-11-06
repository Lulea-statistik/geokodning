#!/usr/bin/env python3
"""Interpret geocoding positional uncertainty without inventing precision.

Input: run-12 master and road fallback in WGS84 EPSG:4326.
A road's spatial spread is an uncertainty indicator, NOT an accuracy measurement.
All road-location data remains available; high-risk points are marked for
municipality-level-only use, never 'corrected' by guessing from house numbers.
"""
import argparse,csv,json,collections
from pathlib import Path

def read(path):
    with open(path,encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

def fnum(v):
    try: return float(v)
    except (TypeError, ValueError): return None

def classify(row):
    cat=row["kategori"]
    spread=fnum(row.get("vagspridning_m"))
    house=fnum(row.get("husnummer_avvikelse"))
    if cat=="Ingen användbar position" or cat=="Flera exakta OSM-kandidater - ingen vald":
        return "Utan vald koordinat","Ej användbar","Granska manuellt"
    if cat=="Direkt entydig adressmatch":
        return "Direkt matchad OSM-adress","Adressorienterad, ej byggnadsverifierad","Kontrollera vid byggnadsanalyser"
    if cat=="Reserv, husnummer högst 10":
        return "Närliggande husnummer","Endast ungefärlig","Ej byggnadsanalys"
    if cat=="Reserv, husnummer stor avvikelse":
        diff=house or 0
        flag="Husnummeravvikelse över 100" if diff>100 else "Husnummeravvikelse 11-100"
        return flag,"Endast ungefärlig","Ej byggnadsanalys"
    if cat=="Reserv, ungefärlig gatuposition":
        return "Annan adresspunkt på gatan","Endast ungefärlig","Ej byggnadsanalys"
    if cat.startswith("Reserv, vägpunkt"):
        if spread is None:
            return "Vägpunkt utan spridningsmått","Endast kommunnivå","Kontrollera väggeometri"
        if spread>5000:
            return "Väg med spridning över 5 km","Endast kommunnivå","Mycket hög granskningsprioritet"
        if spread>1500:
            return "Väg med spridning 1,5-5 km","Endast kommunnivå","Hög granskningsprioritet"
        return "Väg med spridning högst 1,5 km","Gatunivå mycket osäker","Ingen byggnads- eller kvartersanalys"
    return "Okänd klass","Ej användbar","Kontrollera metod"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",default="resultat")
    a=p.parse_args()
    folder=Path(a.out)
    master=read(folder/"osm_samlat_per_adress.csv")
    roads={r["sokadress"]:r for r in read(folder/"osm_vagreserv.csv")}
    field=["sokadress","kategori","osakerhetsklass","rekommenderad_anvandning",
      "atgard","latitude_epsg4326","longitude_epsg4326",
      "gatunamn","osm_way_id","antal_osm_vagsegment","vagspridning_m",
      "husnummer_avvikelse"]
    result=[]
    classes=collections.Counter()
    usage=collections.Counter()
    streets=collections.defaultdict(list)
    for row in master:
        address=row["sokadress"]
        c,use,action=classify(row)
        road=roads.get(address,{})
        new={
            "sokadress":address,"kategori":row["kategori"],
            "osakerhetsklass":c,"rekommenderad_anvandning":use,"atgard":action,
            "latitude_epsg4326":row["latitude_epsg4326"],
            "longitude_epsg4326":row["longitude_epsg4326"],
            "gatunamn":road.get("gatunamn",""),
            "osm_way_id":road.get("osm_way_id",""),
            "antal_osm_vagsegment":road.get("antal_osm_vagsegment",""),
            "vagspridning_m":row["vagspridning_m"],
            "husnummer_avvikelse":row["husnummer_avvikelse"]
        }
        result.append(new)
        classes[c]+=1
        usage[use]+=1
        if row["kategori"]=="Reserv, vägpunkt stor spridning":
            streets[road.get("gatunamn","")].append(new)
    with (folder/"osm_lagesosakerhet.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=field);w.writeheader();w.writerows(result)
    ranked=[]
    for street,rows in streets.items():
        ranked.append({
          "gatunamn":street,"antal_adresser":len(rows),
          "max_vagspridning_m":max(fnum(r["vagspridning_m"]) or 0 for r in rows),
          "antal_osm_vagsegment":max(int(r["antal_osm_vagsegment"] or 0) for r in rows),
          "exempeladress":min(r["sokadress"] for r in rows),
          "atgard":"Kontrollera vägsträckor och eventuella ortsdelar",
        })
    ranked.sort(key=lambda x:(-x["antal_adresser"],-x["max_vagspridning_m"],x["gatunamn"]))
    with (folder/"osm_langa_vagar_granskning.csv").open("w",newline="",encoding="utf-8-sig") as f:
        cols=["gatunamn","antal_adresser","max_vagspridning_m","antal_osm_vagsegment","exempeladress","atgard"]
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(ranked)
    total_road_risky=sum(len(v) for v in streets.values())
    assert total_road_risky==sum(1 for r in master if r["kategori"]=="Reserv, vägpunkt stor spridning")
    summary={
       "unika_sokadresser":len(master),
       "vagpunkter_med_stor_spridning":total_road_risky,
       "antal_berorda_gatunamn":len(ranked),
       "osakerhetsklasser":dict(sorted(classes.items())),
       "rekommenderad_anvandning":dict(sorted(usage.items())),
       "topp_10_langa_gator":ranked[:10],
       "epsg":"EPSG:4326",
       "metod":"Indikativt mått: max avstånd från vald OSM-vägpunkt till samplade vägpunkter, inte absolut geokodningsfel.",
       "viktigt":"Ingen koordinat ändrades. Ortsdel/husnummer kan inte härledas säkert från väggeometri utan oberoende referens."
    }
    (folder/"osm_lagesosakerhet_rapport.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=="__main__":
    main()
