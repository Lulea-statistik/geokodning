#!/usr/bin/env python3
"""Review OSM geocoding master, audit duplicates and source metadata.

Does not change coordinates. Coordinates are retained from source EPSG:4326.
"""
import argparse,csv,json,collections,re
from pathlib import Path
from openpyxl import load_workbook

def read(path):
    with open(path,encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--resultat",default="resultat")
    ap.add_argument("--workbook",default="data/lulea_adresser_kvalitetsgranskning.xlsx")
    a=ap.parse_args()
    out=Path(a.resultat)
    master=read(out/"osm_samlat_per_adress.csv")
    original=read(out/"osm_matchning_geografi.csv")
    road=read(out/"osm_vagreserv.csv")
    road_by={r["sokadress"]:r for r in road}
    groups=collections.defaultdict(list)
    for r in original:
        groups[r["sokadress"]].append(r["originaladress"])
    duplicate_groups={k:v for k,v in groups.items() if len(v)>1}
    duplicate_extra=sum(len(v)-1 for v in duplicate_groups.values())
    if len(original)-len(master)!=duplicate_extra:
        raise RuntimeError("Mismatch between source and deduplicated count")
    wb=load_workbook(a.workbook,read_only=True,data_only=True)
    sheets={}
    for ws in wb.worksheets:
        ws.reset_dimensions()
        first=next(ws.iter_rows(min_row=1,max_row=1,values_only=True),[])
        sheets[ws.title]=[str(x) if x is not None else "" for x in first]
    prioritized=[]
    street_groups=collections.Counter()
    pri_counts=collections.Counter()
    for r in master:
        category=r["kategori"]
        spread=float(r["vagspridning_m"] or 0)
        diff=float(r["husnummer_avvikelse"] or 0)
        if category=="Flera exakta OSM-kandidater - ingen vald":
            priority=1;reason="Flera exakta kandidater"
        elif category=="Ingen användbar position":
            priority=1;reason="Ingen position"
        elif category=="Reserv, vägpunkt stor spridning":
            priority=2;reason="Vägpunkt med spridning över 1500 m"
        elif category=="Reserv, husnummer stor avvikelse":
            priority=3;reason="Stort husnummeravstånd"
        else:
            continue
        street=re.sub(r"\s+\d+\s*[a-zåäö]{0,2}$","",r["sokadress"],flags=re.I).strip()
        street_groups[(priority,street)]+=1
        pri_counts[(priority,reason)]+=1
        prioritized.append({"sokadress":r["sokadress"],
           "prioritet":priority,"orsak":reason,"gatunamn":street,
           "kategori":category,"husnummer_avvikelse":r["husnummer_avvikelse"],
           "vagspridning_m":r["vagspridning_m"],
           "latitude_epsg4326":r["latitude_epsg4326"],
           "longitude_epsg4326":r["longitude_epsg4326"],
           "osm_id":r["osm_id"],
           "antal_vagsegment":road_by.get(r["sokadress"],{}).get("antal_osm_vagsegment",""),
           "antal_originalrader":len(groups[r["sokadress"]])})
    prioritized.sort(key=lambda x:(x["prioritet"],-float(x["vagspridning_m"] or 0),-float(x["husnummer_avvikelse"] or 0),x["sokadress"]))
    file=out/"osm_granskningsprioritet.csv"
    with file.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(prioritized[0]) if prioritized else ["sokadress","prioritet"]);w.writeheader();w.writerows(prioritized)
    dupfile=out/"osm_dubblettkontroll.csv"
    with dupfile.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["sokadress","antal_originalrader","antal_unika_originaladresser"])
        w.writeheader()
        for k,v in sorted(duplicate_groups.items()):
            w.writerow({"sokadress":k,"antal_originalrader":len(v),"antal_unika_originaladresser":len(set(v))})
    result={"antal_originalrader":len(original),"antal_unika_sokadresser":len(master),
        "dubblett_extra_originalrader":duplicate_extra,"antal_sokadresser_med_flera_originalrader":len(duplicate_groups),
        "granskningsprioritet_antal":len(prioritized),
        "prioritetsgrupper":[{"prioritet":p,"orsak":reason,"antal":count} for (p,reason),count in sorted(pri_counts.items())],
        "fem_storsta_granskningsgatugrupper":[{"prioritet":p,"gatunamn":s,"antal":n} for (p,s),n in sorted(street_groups.items(),key=lambda x:(-x[1],x[0]))[:5]],
        "kallfil_kolumnrubriker":sheets,
        "metod":"Granskningsko - inga koordinater andrade. EPSG:4326.",
        "viktigt":"Vägpunkt på namngiven väg garanterar inte rätt vägavsnitt eller byggnad."}
    (out/"osm_granskningsrapport.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
