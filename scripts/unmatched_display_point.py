#!/usr/bin/env python3
"""Create display-only map location for unmatched Lulea search addresses.

Keep latitude_epsg4326 / longitude_epsg4326 EMPTY for unmatched entries.
Display coordinates are NEVER valid geocodes. The common display marker
is a cartographic legend/symbol, not an address location or a municipality
centroid. Coordinates explicit WGS84 EPSG:4326.
"""
import argparse,csv,json
from pathlib import Path

def read(path):
    with path.open(encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

def csvwrite(path,rows,fields):
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--out",default="resultat")
    p.add_argument("--display-lon",type=float,default=22.149656)
    p.add_argument("--display-lat",type=float,default=65.570072)
    a=p.parse_args()
    if not (20<a.display_lon<25 and 64<a.display_lat<67):
        raise SystemExit("Display marker lies outside broad Lulea region; review configuration")
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    original=read(Path(a.input))
    fields=list(original[0]) if original else []
    add=["visnings_longitude_epsg4326","visnings_latitude_epsg4326",
         "visningstyp","geokodning_lyckad","ingår_i_geokodade_antal"]
    if any(f in fields for f in add):
        raise SystemExit("Input already contains view-only fields")
    output=[];missing=[]
    for r in original:
        x=dict(r)
        match=bool(x.get("latitude_epsg4326") and x.get("longitude_epsg4326"))
        if match:
            x.update({"visnings_longitude_epsg4326":x["longitude_epsg4326"],
                "visnings_latitude_epsg4326":x["latitude_epsg4326"],
                "visningstyp":"Geokodad position (precision varierar)",
                "geokodning_lyckad":"ja","ingår_i_geokodade_antal":"ja"})
        else:
            # Keep original geocoding fields empty, do not falsely mark as matched.
            x.update({"visnings_longitude_epsg4326":a.display_lon,
                "visnings_latitude_epsg4326":a.display_lat,
                "visningstyp":"Gemensam VISNINGSPUNKT - EJ geokodad adress",
                "geokodning_lyckad":"nej","ingår_i_geokodade_antal":"nej"})
            missing.append(x)
        output.append(x)
    assert len(output)==len(original)
    assert all(not x.get("latitude_epsg4326") and not x.get("longitude_epsg4326") for x in missing)
    csvwrite(out/"osm_master_med_visningspunkt.csv",output,fields+add)
    # A single marker for all unlocated addresses; avoid 211 overlapping pins.
    feature={"type":"FeatureCollection","features":[{
        "type":"Feature","geometry":{"type":"Point","coordinates":[a.display_lon,a.display_lat]},
        "properties":{
            "namn":"Övriga adresser – ej geokodade",
            "antal_adresser":len(missing),"visningspunkt":True,
            "geografisk_precision":"Ingen; enbart kartografisk placering",
            "status":"Ej geokodade","ej_for_geografisk_analys":True
        }}]}
    (out/"osm_ogekodade_visningssymbol.geojson").write_text(json.dumps(feature,ensure_ascii=False,indent=2),encoding="utf-8")
    info={
      "antal_unika_sokadresser":len(output),
      "antal_geokodade_enligt_tidigare_metod":len(output)-len(missing),
      "antal_ogekodade_med_gemensam_visningspunkt":len(missing),
      "visningspunkt_wgs84_epsg4326":{"longitude":a.display_lon,"latitude":a.display_lat},
      "visningspunkt_vatten_verifierad":False,
      "status":"Visningspunkt separat fran geokodning",
      "crs":"EPSG:4326",
      "important":"Visningspunktens läge är inte en uppgift om adressens läge. Räkna aldrig in den i geografiska punktanalyser, medelkoordinater eller träffstatistik."
    }
    (out/"osm_visningspunkt_sammanfattning.json").write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(info,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
