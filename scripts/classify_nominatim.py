#!/usr/bin/env python3
"""Quality classes for saved, spatially checked Nominatim pilot (EPSG:4326).
Does not call Nominatim. Class A does NOT establish building-level precision.
"""
import argparse, collections, csv, json, re
from pathlib import Path

def house_relation(address, raw):
    m = re.search(r"(\d+\s*[a-zåäö]{0,2})\s*$", address, re.I)
    if not m: return "otydlig sökadress"
    normalize = lambda x: re.sub(r"\s+", "", str(x or "").casefold()).replace("–","-").replace("—","-")
    target, raw = normalize(m.group(1)), normalize(raw)
    if not raw: return "husnummer saknas"
    if raw == target: return "exakt husnummer"
    segments = re.split(r"[,;]", raw)
    if target in segments: return "husnummer i lista - ej punktverifierat"
    if target.isdigit():
        for part in segments:
            hit = re.fullmatch(r"(\d+)-(\d+)", part)
            if hit and int(hit[1]) <= int(target) <= int(hit[2]):
                return "husnummer i intervall - ej punktverifierat"
    return "husnummer skiljer sig"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    with open(a.input, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows: raise SystemExit("Tomt indata")
    per_variant = collections.defaultdict(collections.Counter)
    paired = collections.defaultdict(dict)
    for row in rows:
        inside = row["geografisk_status"] == "inom Luleå kommun"
        exact = row["status"] == "Exakt gatunamn och husnummer i svar"
        code = "A" if inside and exact else ("B" if inside else "C")
        row["kvalitetsklass"] = code
        row["husnummerrelation"] = house_relation(row["adress"], row.get("matchat_husnummer", ""))
        row["byggnadsposition_verifierad"] = "nej"
        per_variant[row["variant"]][code] += 1
        paired[row["adress"]][row["variant"]] = row
    with (out/"nominatim_kvalitetsklassning.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    comparison = []
    total = collections.Counter()
    for address, pair in sorted(paired.items()):
        before, after = pair.get("utan ortstillägg"), pair.get("med Luleå, Sweden")
        if before is None or after is None:
            verdict = "ofullständigt par"
        else:
            score = lambda r: 3-"ABC".index(r["kvalitetsklass"])
            delta = score(after)-score(before)
            verdict = "med ort bättre" if delta > 0 else ("utan ort bättre" if delta < 0 else "likvärdig klassning")
        total[verdict] += 1
        comparison.append({"adress": address, "bedomning": verdict,
            "utan_ort": before["kvalitetsklass"] if before else "",
            "med_ort": after["kvalitetsklass"] if after else "",
            "husnummer_utan": before["husnummerrelation"] if before else "",
            "husnummer_med": after["husnummerrelation"] if after else ""})
    with (out/"nominatim_kvalitetsjamforelse.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(comparison[0])); w.writeheader(); w.writerows(comparison)
    summary = {"antal_adresser":len(paired),"antal_svar":len(rows),
        "klasser_per_variant":{k:dict(v) for k,v in per_variant.items()},
        "parvis_resultat":dict(total),
        "klasser":{"A":"Exakt gatunamn och husnummer samt inom Luleå kommun; ej oberoende verifierad byggnadspunkt",
            "B":"Inom kommun men ej exakt textmatchning på gatunamn och husnummer",
            "C":"Utanför kommun, ogiltig koordinat eller ingen koordinat"},
        "crs":"EPSG:4326", "urval":"Liten 12-adresspilot, inte representativt"}
    (out/"nominatim_kvalitetsrapport.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__ == "__main__":
    main()
