# Adressmatchning mot OpenStreetMap – Luleå

Målet är att kontrollera i vilken utsträckning unika adresser i Luleå finns som adressobjekt i OpenStreetMap (OSM).

## Kom igång
1. Hämta den tidigare framtagna filen `lulea_adresser_kvalitetsgranskning.xlsx`.
2. Ladda upp den till `data/lulea_adresser_kvalitetsgranskning.xlsx` i detta repository, **inte originalfilen som innehåller Lgh-identifierare**.
3. Öppna Actions > **Kontrollera Luleåadresser i OSM** > Run workflow.
4. Hämta CSV-filerna som workflow-artifact efter körningen.

Indata hämtas från bladet **Unika adresser**, kolumnen **Adress för OSM-matchning**. Lägenhetsnummer ingår inte. **Observera att även en rensad bostadsadresslista blir offentligt tillgänglig i ett publikt repository.** Publicera inte filen om det finns sekretess-/personuppgiftsproblem; byt i så fall till privat repository.

## Metod
GitHub Actions laddar ned Geofabriks senaste Sverigeutdrag och letar efter `addr:street` + `addr:housenumber` på OSM-noder/vägar inom en bred geografisk avgränsning runt Luleå. Alla koordinater exporteras i WGS84 / EPSG:4326. Avgränsningen är en **sökruta, inte kommungräns**, och matchningen är en registerkontroll – inte ett test av Nominatims faktiska sökresultat. Matchningar utan säkert Luleå-sammanhang eller med flera kandidater flaggas för granskning.

Filer: `resultat/osm_matchning.csv`, `resultat/sammanfattning.json` och `resultat/osm_kandidater.csv` (artifact i Actions; inte automatiskt commit:ade). Resultaten får inte tolkas som verifierad fastighets- eller byggnadsposition utan ytterligare kvalitetskontroll.

Källa: https://download.geofabrik.de/europe/sweden.html
