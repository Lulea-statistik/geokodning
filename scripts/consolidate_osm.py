#!/usr/bin/env python3
"""Create ONE row per unique normalized search address, prioritized by confidence.
Only accepts coordinates explicitly classified inside Lulea municipality by the
existing spatial validation. Coordinates WGS84 EPSG:4326, never building verified.
"""
import argparse, collections, csv, json
from pathlib import Path

def read_csv(p):
    with open(p,encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

def valid_point(r):
    return bool(r and r.get("latitude_epsg4326") and r.get("longitude_epsg4326")
        and r.get("inom_lulea_kommun_osm")=="ja")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",default="resultat")
    args=ap.parse_args()
    out=Path(args.out)
    original=read_csv(out/"osm_matchning_geografi.csv")
    near={r["sokadress"]:r for r in read_csv(out/"osm_reservgeokodning.csv")}
    roads={r["sokadress"]:r for r in read_csv(out/"osm_vagreserv.csv")}
    candidate_rows=read_csv(out/"osm_kandidater_geografi.csv")
    by_address=collections.defaultdict(list)
    for r in candidate_rows:
        by_address[r["sokadress"]].append(r)
    output=[]
    counts=collections.Counter()
    review=[]
    seen=set()
    for r in original:
        a=r["sokadress"]
        if a in seen:continue
        seen.add(a)
        category,choice,source,comment="Ingen användbar position",None,"",""
        # One unambiguous matching OSM address inside the municipality.
        if valid_point(r):
            category,choice,source="Direkt entydig adressmatch",r,"OSM adresspunkt/byggnadsobjekt"
        else:
            # Multiple exact candidates can be associated with a reference street and
            # house, but picking an arbitrary one is unsafe.
            candidates=[c for c in by_address.get(a,[]) if valid_point(c)]
            if candidates and r["status"]=="Flera OSM-kandidater":
                category="Flera exakta OSM-kandidater - ingen vald"
                comment=f"{len(candidates)} kandidater inom kommun; granska manuellt"
            fallback=near.get(a)
            if category=="Ingen användbar position" and valid_point(fallback):
                method=fallback["reservmetod"]
                if method=="Närliggande husnummer":
                    category="Reserv, husnummer högst 10"
                elif method=="Husnummer 1-500, stor avvikelse":
                    category="Reserv, husnummer stor avvikelse"
                elif method=="Ungefärlig gatuposition":
                    category="Reserv, ungefärlig gatuposition"
                else: raise ValueError("Unexpected fallback with coordinates: "+method)
                choice,source=fallback,"OSM annan adress på samma gata"
                comment="Avser inte referensens faktiska husnummer"
            road=roads.get(a)
            if category=="Ingen användbar position" and valid_point(road):
                spread=float(road.get("gatans_geografiska_spridning_m") or 0)
                if spread>1500:
                    category="Reserv, vägpunkt stor spridning"
                else:
                    category="Reserv, vägpunkt"
                choice,source=road,"OSM namngiven väg"
                comment="Vägpunkt, ej adresspunkt eller verifierat gatuavsnitt"
        row={
          "sokadress":a,
          "kategori":category,
          "osm_status_ursprung":r["status"],
          "latitude_epsg4326":choice.get("latitude_epsg4326","") if choice else "",
          "longitude_epsg4326":choice.get("longitude_epsg4326","") if choice else "",
          "kalltyp":source,
          "osm_id":(choice.get("osm_id") or choice.get("osm_way_id") or "") if choice else "",
          "matchat_osm_husnummer":choice.get("matchat_osm_husnummer","") if choice else "",
          "husnummer_avvikelse":choice.get("husnummer_avvikelse","") if choice else "",
          "vagspridning_m":choice.get("gatans_geografiska_spridning_m","") if choice else "",
          "inom_lulea_kommun_osm":"ja" if choice else "",
          "exakt_byggnadsposition_verifierad":"nej",
          "anmärkning":comment,
        }
        output.append(row)
        counts[category]+=1
        if category in {"Flera exakta OSM-kandidater - ingen vald",
                        "Reserv, husnummer stor avvikelse",
                        "Reserv, vägpunkt stor spridning",
                        "Ingen användbar position"}:
            review.append(row)
    if len(output)!=len(seen):
        raise AssertionError("Deduplication failed")
    # All usable coordinate rows must be checked against polygon by precursor steps.
    if any(bool(x["latitude_epsg4326"]) != bool(x["longitude_epsg4326"]) for x in output):
        raise AssertionError("One coordinate missing")
    fields=list(output[0]) if output else []
    for name,rows in [("osm_samlat_per_adress.csv",output),("osm_prioriterad_granskning.csv",review)]:
        with (out/name).open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    coordinate_count=sum(bool(x["latitude_epsg4326"]) for x in output)
    summary={
       "unika_sokadresser":len(output),
       "adresser_med_nagon_position_inom_kommun":coordinate_count,
       "andel_med_position_procent":round(coordinate_count/len(output)*100,2) if output else 0,
       "adresser_utan_vald_position":len(output)-coordinate_count,
       "per_kvalitetskategori":dict(counts),
       "antal_prioriterade_granskningsposter":len(review),
       "geografisk_referens":"OSM administrative boundary Lulea municipality",
       "crs":"EPSG:4326",
       "caveat":"A named road or alternative street number is an approximate location only. Exact building position is NOT verified. Original source may contain duplicate search addresses; only normalized search addresses are counted."
    }
    (out/"osm_samlad_sammanfattning.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
