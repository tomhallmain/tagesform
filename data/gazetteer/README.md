# Gazetteer data

Source: [GeoNames](https://www.geonames.org/), `cities500` export (every
populated place with population > 500, plus a large number of places with
no recorded population figure that GeoNames still includes at this tier --
ca. 235k rows worldwide after filtering to populated places) plus
`admin1CodesASCII.txt` (English names for first-level administrative
divisions, e.g. US states).

Upgraded from the earlier `cities15000` export (population > 15,000 only,
ca. 25-34k places) specifically to cover smaller towns/municipalities --
see the coverage caveats below before assuming a given place will be
present.

- Retrieved: 2026-08-18, from `https://download.geonames.org/export/dump/`.
- License: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
  GeoNames provides this data "as is" without warranty of accuracy,
  timeliness, or completeness.

## Coverage caveats

`cities500` is GeoNames' finest pre-built city/town tier, but it is not
exhaustive, and the population threshold is not applied uniformly:

- **~13% of included rows have population recorded as 0** (30,654 of
  235,405 in the 2026-08-18 pull) -- GeoNames evidently includes many
  named places at this tier regardless of population data quality, not
  strictly "population > 500." Population figures that *are* present can
  also be stale (based on whatever census/estimate GeoNames last
  ingested), so the boundary between included/excluded doesn't track
  real-world population precisely.
- **Places genuinely below the threshold are still absent.** This
  disproportionately affects countries with many small administrative
  units -- e.g. France alone has roughly 35,000 communes, and only
  ~15,400 of them appear in this file; most of the rest are small rural
  communes under the population cutoff.
- **Only GeoNames feature class `P` (populated place) is included** (see
  Files below) -- a locally-known "town" tagged under a different feature
  code won't appear even if GeoNames has an entry for it.
- **Only the canonical `asciiname` is kept**, not GeoNames'
  `alternatenames` column (see Files below) -- a bilingual/regional-
  language name for a place that *is* in the dataset may still fail to
  fuzzy-match if it differs enough from the canonical name.
- **True neighborhood-level granularity is out of scope** for any
  `citiesNNN` tier -- resolving something like "SoHo" or "downtown
  Anchorage" would need GeoNames' full multi-million-row dataset or a
  manually curated add-on, not a bigger `citiesNNN` export.

If gaps remain after this upgrade, the next step up is per-country full
GeoNames dumps (e.g. `US.zip`, one per European country of interest) or
`allCountries.zip`, re-filtered locally with the same feature-class `P`
`awk` filter below, dropping the population floor entirely -- a bigger
lift, only worth it if `cities500` still isn't enough.

## Files

- `cities500.tsv` -- trimmed from GeoNames' own `cities500.txt`. Kept
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
curl -L -o cities500.zip https://download.geonames.org/export/dump/cities500.zip
unzip cities500.zip
awk -F'\t' 'BEGIN{OFS="\t"} $7=="P" {print $1,$3,$5,$6,$8,$9,$11,$15}' cities500.txt > cities500.tsv
curl -L -o admin1_codes.tsv https://download.geonames.org/export/dump/admin1CodesASCII.txt
```

Load into the app's `gazetteer_place` table with:

```bash
flask gazetteer-load
```

`gazetteer-load` upserts by `geonameid` (`GazetteerPlace.external_id`), so
re-running it after a fresh pull updates existing rows and adds new ones
without duplicating anything -- it does not remove rows for places that
disappeared from a newer export.
