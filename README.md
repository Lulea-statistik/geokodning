# Adressmatchning mot OpenStreetMap – Luleå

Målet är att kontrollera i vilken utsträckning unika adresser i Luleå finns som adressobjekt i OpenStreetMap (OSM).

## Kom igång
1. Hämta den tidigare framtagna filen `lulea_adresser_kvalitetsgranskning.xlsx`.
2. Ladda upp den till `data/lulea_adresser_kvalitetsgranskning.xlsx` i detta repository, **inte originalfilen som innehåller Lgh-identifierare**.
3. Öppna Actions > **Kontrollera Luleåadresser i OSM** > Run workflow.
4. Hämta CSV-filerna som workflow-artifact efter körningen.

Indata hämtas från bladet **Unika adresser**, kolumnen **Adress för OSM-matchning**. Lägenhetsnummer ingår inte. **Observera att även en rensad bostadsadresslista blir offentligt tillgänglig i ett publikt repository.** Publicera inte filen om det finns sekretess-/personuppgiftsproblem; byt i så fall till privat repository.

## Referensmaterial och dataskydd
Adresslistan uppges av beställaren ha hämtats från Lantmäteriets folkbokföringsregister. Detta är en uppgift om materialets proveniens, inte en oberoende verifiering av registerbenämning eller fullständig adresskvalitet. Behandla referensadresserna som givna söknycklar: en utebliven OSM-träff innebär **inte** att registeradressen är fel.

**Viktigt:** Detta repository är offentligt och den uppladdade Excel-filen kan innehålla ursprungliga lägenhetstillägg och information med koppling till folkbokföring. Innan fortsatt publicering måste materialets licens, eventuella personuppgifter och lämpligheten av öppen spridning bedömas. Om underlaget inte är avsett för publicering: ändra repository till privat och sanera Git-historiken; att bara ta bort filen i senaste commit tar inte bort tidigare versioner. Workflow-artifacts är också åtkomliga för personer med tillräcklig repositorybehörighet.

## Metod
GitHub Actions laddar ned Geofabriks senaste Sverigeutdrag och letar efter `addr:street` + `addr:housenumber` på OSM-noder/vägar inom en bred geografisk avgränsning runt Luleå. Alla koordinater exporteras i WGS84 / EPSG:4326. Avgränsningen är en **sökruta, inte kommungräns**, och matchningen är en registerkontroll – inte ett test av Nominatims faktiska sökresultat. Matchningar utan säkert Luleå-sammanhang eller med flera kandidater flaggas för granskning.

Filer: `resultat/osm_matchning.csv`, `resultat/sammanfattning.json` och `resultat/osm_kandidater.csv` (artifact i Actions; inte automatiskt commit:ade). Resultaten får inte tolkas som verifierad fastighets- eller byggnadsposition utan ytterligare kvalitetskontroll.

Källa: https://download.geofabrik.de/europe/sweden.html

## Geografisk granskningskö
Efter OSM-matchning verifieras kandidaternas koordinater mot en OSM-kommunpolygon (admin_level=7) för Luleå, utan att förväxla kommungräns med adressprecision. Körningen skapar även `osm_kandidater_geografi.csv` med en rad för varje OSM-kandidat och `granskningsko.csv` med samtliga kandidater för flertydiga adresser eller punkter utanför kommungränsen. Därmed tappas inte flertydiga kandidater bort när ursprunglig sammanställning saknar en vald koordinat.

**Ingen träff**, **adresskandidat inom kommungräns**, **entydig adressmatchning** och **lyckad Nominatim-geokodning** är olika mått. Ingen av de geografiska kontrollerna verifierar ännu Nominatims faktiska utfall.
