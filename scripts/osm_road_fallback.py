#!/usr/bin/env python3
"""Named-road fallback for addresses without OSM addr:street points.

OSM road geometry and coordinates are WGS84 (EPSG:4326).
This estimates a point ON A NAMED ROAD inside Lulea municipality, never an
address location. Repeated named streets and multipart roads may be ambiguous.
"""
import argparse, collections, csv, json, re, math
from pathlib import Path
import osmium
from shapely.geometry import Point
from verify_geo import MunicipalBoundary
from match_osm import norm, parse

class RoadIndex(osmium.SimpleHandler):
    def __init__(self, target_streets, polygon):
        super().__init__()
        self.target_streets=target_streets
        self.polygon=polygon
        self.road_points=collections.defaultdict(list)
        self.road_way_count=collections.Counter()
    def way(self, o):
        if not o.tags.get("highway"):
            return
        street=norm(o.tags.get("name",""))
        if street not in self.target_streets:
            return
        try:
            points=[(n.location.lon,n.location.lat) for n in o.nodes if n.location.valid()]
            if not points:
                return
            # Check actual sampled vertices and edge midpoints (no bounding-box shortcut).
            usable=[]
            for i, xy in enumerate(points):
                if self.polygon.covers(Point(*xy)):
                    usable.append(xy)
                if i+1<len(points):
                    xy2=points[i+1]
                    mid=((xy[0]+xy2[0])/2,(xy[1]+xy2[1])/2)
                    if self.polygon.covers(Point(*mid)):
                        usable.append(mid)
            if not usable:
                return
        except (ValueError, RuntimeError, OverflowError):
            return
        self.road_way_count[street]+=1
        # At most three samples per way; avoid overweighting ways with many vertices.
        for idx in sorted(set([0,len(usable)//2,len(usable)-1])):
            self.road_points[street].append((usable[idx][0],usable[idx][1], "w"+str(o.id)))

def haversine(a,b):
    lon1,lat1=a
    lon2,lat2=b
    r1,r2=math.radians(lat1),math.radians(lat2)
    dlat=r2-r1;dlon=math.radians(lon2-lon1)
    z=math.sin(dlat/2)**2+math.cos(r1)*math.cos(r2)*math.sin(dlon/2)**2
    return 12742000*math.atan2(math.sqrt(z),math.sqrt(1-z))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--pbf",required=True)
    ap.add_argument("--input",required=True,help="osm_reservgeokodning.csv")
    ap.add_argument("--out",default="resultat")
    a=ap.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    with open(a.input,encoding="utf-8-sig",newline="") as f:
        source=list(csv.DictReader(f))
    # The group explicitly requested by the user, not all currently unmatched rows.
    missing=[r for r in source if r["reservmetod"]=="Ingen OSM-gatuadress inom kommunen"]
    street_by_address={r["sokadress"]:parse(r["sokadress"])[0] for r in missing if parse(r["sokadress"])}
    polygon_reader=MunicipalBoundary()
    polygon_reader.apply_file(a.pbf,locations=True,idx="flex_mem")
    if len(polygon_reader.shapes)!=1:
        raise SystemExit("Lulea municipality polygon missing or ambiguous; no road fallback")
    index=RoadIndex(set(street_by_address.values()),polygon_reader.shapes[0][1])
    index.apply_file(a.pbf,locations=True,idx="flex_mem")
    records=[]
    counts=collections.Counter()
    street_counts=collections.Counter(street_by_address.values())
    for r in missing:
        address=r["sokadress"]
        street=street_by_address.get(address)
        candidates=index.road_points.get(street,[]) if street else []
        if candidates:
            # Reproducible sampled point, actually within polygon.
            # Prefer a middle sample; never pretend nearest house number is identified.
            chosen=candidates[len(candidates)//2]
            spread=round(max(haversine((chosen[0],chosen[1]),(p[0],p[1])) for p in candidates))
            quality="Vägpunkt på namngiven gata - mycket osäkert läge"
            if spread>1500:
                quality="Vägpunkt på namngiven gata - geografiskt spridd"
            counts["med_vagpunkt"]+=1
            if spread>1500: counts["med_stor_geografisk_spridning"]+=1
        else:
            chosen=None;spread=""
            quality="Ingen namngiven OSM-väg med samma namn inom kommunen"
            counts["utan_vagpunkt"]+=1
        records.append({
          "sokadress":address,"gatunamn":street or "",
          "ursprunglig_reservstatus":r["reservmetod"],
          "vagmatchning":quality,
          "latitude_epsg4326":round(chosen[1],7) if chosen else "",
          "longitude_epsg4326":round(chosen[0],7) if chosen else "",
          "osm_way_id":chosen[2] if chosen else "",
          "antal_osm_vagsegment":index.road_way_count.get(street,0),
          "gatans_geografiska_spridning_m":spread,
          "inom_lulea_kommun_osm":"ja" if chosen else "",
          "positionsprecision":"ungefärlig gatupunkt, ej adressposition" if chosen else "saknas"
        })
    fields=list(records[0]) if records else ["sokadress","vagmatchning"]
    with (out/"osm_vagreserv.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(records)

    # Address samples are sorted deterministically, not falsely presented as
    # the most common individual addresses. Also report top missing street groups.
    top5=sorted(street_by_address)[:5]
    top5_streets=[{"gatunamn":street,"antal_sokadresser":cnt,
      "exempeladress":min(ad for ad,st in street_by_address.items() if st==street)}
      for street,cnt in sorted(street_counts.items(),key=lambda x:(-x[1],x[0]))[:5]]
    summary={
      "ursprunglig_grupp":"Ingen OSM-gatuadress inom kommunen",
      "antal_i_gruppen":len(missing),
      "vagreserv_status":dict(counts),
      "unika_gatunamn_i_gruppen":len(street_counts),
      "fem_forsta_adresser_alfabetiskt":top5,
      "fem_gatunamn_med_flest_saknade_adresser":top5_streets,
      "polygon":"OSM Luleå admin_level=7",
      "crs":"EPSG:4326",
      "reservation":"Punkten tillhör en OSM-väg med samma namn i kommunen, inte nödvändigtvis korrekt ort/gatuavsnitt eller korrekt husnummer."
    }
    (out/"osm_vagreserv_sammanfattning.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
