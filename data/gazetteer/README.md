# Gazetteer data

Source: [GeoNames](https://www.geonames.org/), `cities15000` export (every
populated place with population > 15,000, or a national/administrative
capital regardless of population -- ca. 25-34k places worldwide) plus
`admin1CodesASCII.txt` (English names for first-level administrative
divisions, e.g. US states).

- Retrieved: 2026-08-04, from `https://download.geonames.org/export/dump/`.
- License: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
  GeoNames provides this data "as is" without warranty of accuracy,
  timeliness, or completeness.

## Files

- `cities15000.tsv` -- trimmed from GeoNames' own `cities15000.txt`. Kept
  columns (tab-separated, no header row): `geonameid, asciiname, latitude,
  longitude, feature_code, country_code, admin1_code, population`. Rows
  restricted to GeoNames feature class `P` (populated place). The
  `alternatenames` column (dozens of transliterations per place) was
  dropped -- it's most of the original file's size and isn't used by
  `geocoding_service.py`'s matching, which relies on edit-distance fuzzy
  matching against `asciiname` rather than an exact-alternate-name lookup.
- `admin1_codes.tsv` -- GeoNames' `admin1CodesASCII.txt` unmodified.
  `<country_code>.<admin1_code>` -> English name, e.g. `US.AK` -> `Alaska`.
  Not currently consumed by the loader (see `app/cli.py`'s
  `gazetteer-load` command) -- `GazetteerPlace.admin_region` stores the raw
  admin1 code (e.g. `AK`) as-is, since that's what matches how people
  commonly write US locations ("Anchorage, AK"). Kept alongside the cities
  file so admin1-name-aware matching (accepting "Alaska" as well as "AK")
  can be added later without a second download.

## Regenerating

```bash
curl -L -o cities15000.zip https://download.geonames.org/export/dump/cities15000.zip
unzip cities15000.zip
awk -F'\t' 'BEGIN{OFS="\t"} $7=="P" {print $1,$3,$5,$6,$8,$9,$11,$15}' cities15000.txt > cities15000.tsv
curl -L -o admin1_codes.tsv https://download.geonames.org/export/dump/admin1CodesASCII.txt
```

Load into the app's `gazetteer_place` table with:

```bash
flask gazetteer-load
```
