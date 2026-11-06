#!/usr/bin/env python3
"""Small, deterministic Nominatim pilot. No bulk geocoding.

Input is ONLY address keys from 'Unika adresser'; no apartment identifiers.
Results are diagnostics, not independently verified official coordinates.
"""
import argparse, csv, hashlib, json, re, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from openpyxl import load_workbook

def normalize(s):
    return re.sub(r"\s+", " ", str(s or "").strip()).casefold()

def parse_address(s):
    match = re.fullmatch(r"(.+?)\s+(\d+\s*[a-zåäö]{0,2})", str(s or "").strip(), re.I)
    if not match: return None
    return normalize(match.group(1)), re.sub(r"\s+", "", normalize(match.group(2)))

def get_addresses(path):
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb["Unika adresser"]
    ws.reset_dimensions()
    rows = iter(ws.iter_rows(values_only=True))
    headers = next(rows)
    idx = headers.index("Adress för OSM-matchning")
    addresses = set()
    for r in rows:
        if len(r) > idx and r[idx]:
            a = str(r[idx]).strip()
            if parse_address(a): addresses.add(a)
    return sorted(addresses, key=lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest())

def ask(endpoint, query, user_agent):
    url = endpoint.rstrip("/") + "/search?" + urllib.parse.urlencode({
        "q": query, "format": "jsonv2", "addressdetails": "1",
        "limit": "3", "countrycodes": "se", "accept-language": "sv"
    })
    request = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode("utf-8")), ""
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return [], f"{type(error).__name__}: {str(error)[:160]}"

def assess(query, records):
    expected = parse_address(query)
    if not expected: return "Ogiltig sökadress", {}
    street, house = expected
    if not records: return "Ingen sökträff", {}
    for result in records:
        details = result.get("address") or {}
        actual_street = normalize(details.get("road") or details.get("pedestrian") or details.get("residential") or "")
        actual_house = re.sub(r"\s+", "", normalize(details.get("house_number") or ""))
        if street == actual_street and house == actual_house:
            return "Exakt gatunamn och husnummer i svar", result
    return "Träff men ej verifierat husnummer", records[0]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", default="resultat")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--endpoint", default="https://nominatim.openstreetmap.org")
    parser.add_argument("--user-agent", required=True)
    args = parser.parse_args()
    if not 1 <= args.limit <= 12: raise SystemExit("Public API pilot: 1-12 addresses only")
    if "contact" not in args.user_agent.lower() and "@" not in args.user_agent:
        raise SystemExit("Set an identifying User-Agent with maintainer contact")
    addresses = get_addresses(args.input)[:args.limit]
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    rows = []
    for address in addresses:
        for variant, query in [("utan ortstillägg", address), ("med Luleå, Sweden", address + ", Luleå, Sweden")]:
            results, error = ask(args.endpoint, query, args.user_agent)
            status, best = assess(address, results)
            if error: status = "API-fel – ej jämförbart"
            details = best.get("address") or {}
            rows.append({
                "adress": address, "variant": variant, "sokfras": query, "status": status,
                "antal_resultat_returnerade": len(results), "fel": error,
                "latitude_epsg4326": best.get("lat", ""), "longitude_epsg4326": best.get("lon", ""),
                "osm_type": best.get("osm_type", ""), "osm_id": best.get("osm_id", ""),
                "matchat_gatunamn": details.get("road", ""), "matchat_husnummer": details.get("house_number", ""),
                "visningsnamn": best.get("display_name", "")
            })
            time.sleep(1.3)  # Globally serial requests, below public Nominatim absolute rate ceiling
    fields = list(rows[0]) if rows else []
    with (out/"nominatim_pilot.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    counts = {}
    for v in ("utan ortstillägg", "med Luleå, Sweden"):
        counts[v] = {status: sum(x["variant"] == v and x["status"] == status for x in rows)
                     for status in sorted(set(x["status"] for x in rows))}
    summary = {
        "sample_size": len(addresses),
        "selection": "12 distinct parseable addresses, sorted by SHA-256 of address text; not representative",
        "method": "Nominatim JSONv2 countrycodes=se; no municipal boundary verification",
        "crs": "EPSG:4326", "counts": counts,
        "warning": "Small diagnostic pilot only. Exact-text match does not establish an independent authoritative building position."
    }
    (out/"nominatim_pilot_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
