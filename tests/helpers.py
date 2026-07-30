"""Shared test assertion helpers.

`assert_in_response`/`assert_not_in_response` check for a snippet in an HTTP
response body without dumping the full response on failure. A bare
`assert b'X' in response.data` triggers pytest's assertion-rewriting
introspection, which prints the *entire* response body (often a full
rendered HTML page) into the failure output. Computing the boolean first and
asserting on that plain value keeps failures short, and reports the status
code and body length, which is almost always the actually-useful context.

`expected_text` computes what `I18N._()` would render a given string as for
a given locale -- per the i18n policy in CLAUDE.md, tests must assert against
the translation system's actual output rather than hardcoding English, since
a hardcoded expectation breaks the moment the string is actually translated,
or whenever the suite runs under a non-English LANG. It intentionally
doesn't go through Flask's `g` (which is what I18N._ caches onto during a
real request) -- in this suite, `app.app_context()` is pushed once for the
whole session (see the `app` fixture), so `g` persists across every
`client.get()` call rather than resetting per-request. Looking up the
translation directly sidesteps relying on that shared, mutable `g` state.
"""

import gettext

from app.utils.translations import I18N
from app.utils.utils import Utils


def expected_text(text, locale=None):
    """The translated string I18N._(text) would produce for `locale`, or for
    the default resolved locale (whatever Utils.get_default_user_language()
    -- ultimately the real LANG env var -- currently resolves to) if
    `locale` isn't given."""
    if locale is None:
        locale = Utils.get_default_user_language()
    translation = gettext.translation('base', I18N.localedir, languages=[locale], fallback=True)
    return translation.gettext(text)


def _as_bytes(needle):
    return needle.encode() if isinstance(needle, str) else needle


def assert_in_response(needle, response, note=None):
    """Assert `needle` (str or bytes) appears in `response.data`."""
    haystack = response.data
    needle = _as_bytes(needle)
    found = needle in haystack
    detail = f" ({note})" if note else ""
    assert found, (
        f"Expected {needle!r} in response{detail} -- "
        f"status {response.status_code}, body length {len(haystack)} bytes"
    )


def assert_not_in_response(needle, response, note=None):
    """Assert `needle` (str or bytes) does NOT appear in `response.data`."""
    haystack = response.data
    needle = _as_bytes(needle)
    found = needle in haystack
    detail = f" ({note})" if note else ""
    assert not found, (
        f"Did not expect {needle!r} in response{detail} -- "
        f"status {response.status_code}, body length {len(haystack)} bytes"
    )
