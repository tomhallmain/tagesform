"""Fuzzy-matches freeform location strings (User.location, Entity.location)
against the local GazetteerPlace table -- see docs/entity-geolocation.md.

Not a live geocoding API call: resolution is a local computation against a
bundled dataset (data/gazetteer/, loaded via `flask gazetteer-load`).
Callers geocode once on save and cache the result on the owning row --
never call this from a per-request/per-refresh hot path.
"""
from dataclasses import dataclass

from ..models import GazetteerPlace, db
from ..utils.logging_setup import get_logger
from ..utils.utils import Utils

logger = get_logger('geocoding_service')

# First N characters of the normalized name used to narrow SQL candidates
# before scoring the rest with Utils.string_distance -- comparing a typo'd
# input against every gazetteer row in Python doesn't scale. Trade-off,
# confirmed by testing against the real bundled dataset: a typo landing in
# the first two characters (e.g. "nnchorage") won't be found, since the
# true place drops out of the candidate pool before scoring even starts.
FUZZY_PREFIX_LENGTH = 2

# Below this length, only an exact match is attempted -- fuzzy-matching
# very short strings (e.g. a 2-letter admin-region code like "AK" showing
# up as a name candidate) is unreliable no matter the distance threshold,
# confirmed directly: an earlier version of this matcher, without this
# guard, resolved "Anchorage, AK" to a place called "Aku" because "AK"
# itself fuzzy-matched before "Anchorage" was ever tried.
MIN_FUZZY_LENGTH = 4


def _max_accepted_distance(length):
    """How many edits (Utils.string_distance) to tolerate for a candidate
    of this length. Deliberately NOT Utils.is_similar_strings' own
    threshold -- that formula is tuned for the short strings it was built
    for (entity-name dedup, LLM JSON key typos) and, tested directly
    against this dataset, rejects exactly the kind of realistic typo this
    feature needs to tolerate: "Anchorage" (9 chars) vs "Anchoarge" (a
    transposition, edit distance 2) fails Utils.is_similar_strings'
    threshold for that length outright. This formula was tuned instead by
    testing against the bundled gazetteer directly (see
    docs/entity-geolocation.md) -- allows more slack as names get longer,
    capped so it doesn't get so loose that unrelated places start
    colliding. Measured against 500 real city names (6-10 chars) with one
    random single-character edit each: ~68% resolved correctly, ~27%
    landed below the prefix filter's reach (see FUZZY_PREFIX_LENGTH) and
    matched nothing, ~4% resolved to a meaningfully different place. That
    residual false-positive rate is a real, open trade-off, not
    eliminated -- see docs/entity-geolocation.md's open questions.
    """
    return min(3, max(1, length // 4))


@dataclass
class GeocodeResult:
    latitude: float
    longitude: float
    matched_place_id: int


def geocode(location_string):
    """Resolve a freeform location string to a GeocodeResult, or None if
    nothing in the gazetteer matches confidently enough (an unmatched
    location is left ungeocoded by callers, never guessed at)."""
    if not location_string or not location_string.strip():
        return None

    segments = [s.strip() for s in location_string.split(',') if s.strip()]
    if not segments:
        return None

    if len(segments) == 1:
        place = _match_segment(segments[0], region_hint=None)
        return _to_result(place) if place else None

    # The last comma-separated segment is conventionally the broader
    # region/country ("Anchorage, AK" / "123 Main St, Anchorage, Alaska"),
    # not itself a candidate place name -- trying it as one is exactly what
    # let "AK" get matched as a name in testing (see MIN_FUZZY_LENGTH).
    # It's used only as a region_hint for narrowing/tie-breaking below.
    region_hint = segments[-1]
    for name_candidate in reversed(segments[:-1]):
        place = _match_segment(name_candidate, region_hint)
        if place is not None:
            return _to_result(place)
    return None


def _to_result(place):
    return GeocodeResult(latitude=place.latitude, longitude=place.longitude, matched_place_id=place.id)


def apply_geocode(target, location):
    """Best-effort: resolve `location` and set it on `target` (a User or
    Entity)'s latitude/longitude/location_matched_place_id. Never raises
    and never blocks the save it's part of -- an unmatched or failed
    geocode just leaves coordinates null, same as every other best-effort
    signal in this app. Shared by entities.py's add/edit-place routes and
    settings.py's update-location route rather than duplicated in each."""
    result = None
    if location:
        try:
            result = geocode(location)
        except Exception as e:
            logger.error(f"Error geocoding location {location!r}: {e}")

    if result is None:
        target.latitude = None
        target.longitude = None
        target.location_matched_place_id = None
    else:
        target.latitude = result.latitude
        target.longitude = result.longitude
        target.location_matched_place_id = result.matched_place_id


def _match_segment(name_candidate, region_hint):
    normalized = name_candidate.strip().lower()

    exact = GazetteerPlace.query.filter_by(normalized_name=normalized).all()
    if exact:
        return _resolve_candidates(exact, region_hint)

    if len(normalized) < MIN_FUZZY_LENGTH:
        return None

    pool = _fuzzy_candidate_pool(normalized, region_hint)
    max_distance = _max_accepted_distance(len(normalized))
    scored = [(place, Utils.string_distance(normalized, place.normalized_name)) for place in pool]
    accepted = [(place, distance) for place, distance in scored if distance <= max_distance]
    if not accepted:
        return None

    min_distance = min(distance for _, distance in accepted)
    closest = [place for place, distance in accepted if distance == min_distance]
    return _resolve_candidates(closest, region_hint)


def _fuzzy_candidate_pool(normalized, region_hint):
    prefix = normalized[:FUZZY_PREFIX_LENGTH]
    base_query = GazetteerPlace.query.filter(GazetteerPlace.normalized_name.like(f"{prefix}%"))

    if region_hint:
        region_filtered = base_query.filter(
            db.func.lower(GazetteerPlace.admin_region) == region_hint.strip().lower()
        ).all()
        if region_filtered:
            return region_filtered
        # region_hint may be spelled differently than the gazetteer's admin1
        # code (e.g. "Alaska" vs "AK"), or just wrong -- retry unfiltered
        # rather than treating a region mismatch as "no match at all."
    return base_query.all()


def _resolve_candidates(candidates, region_hint):
    """Tie-break among multiple equally-good candidates (same normalized
    name, or tied fuzzy distance): prefer one matching the supplied region
    hint, else the most populous -- a reasonable prior for "which
    same-named place did they probably mean" absent other information."""
    if len(candidates) == 1:
        return candidates[0]
    if region_hint:
        region_matches = [
            c for c in candidates if c.admin_region and c.admin_region.lower() == region_hint.strip().lower()
        ]
        if region_matches:
            candidates = region_matches
    return max(candidates, key=lambda c: c.population or 0)
