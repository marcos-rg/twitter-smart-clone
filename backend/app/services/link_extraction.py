"""Safe link-entity extraction for tweet content (TSC-TWEET-001's "safely
renderable link data" acceptance criterion; spec §10.2: "sanitize/validate
links").

The backend never returns HTML for tweet content — it returns the tweet's
plain text plus a list of `(url, start, end)` spans describing where a link
begins/ends inside that text. The frontend renders the plain text (React's
default escaping already makes that safe) and overlays real `<a>` elements
only at these server-validated spans. Nothing about this contract lets a
client-supplied string become executable markup: there's no HTML
round-trip, so there's nothing to sanitize on the way out.

Only `http://`/`https://` URLs are ever recognized. `javascript:`, `data:`,
bare `//scheme-relative`, and every other scheme are invisible to
`_URL_PATTERN` (it requires a literal `http`/`https` scheme) and are
additionally rejected by the explicit scheme check below, so a link entity
can never carry anything a client could use to `href`-inject script
execution.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

#: A run of non-whitespace, non-angle-bracket, non-quote characters starting
#: with an explicit http(s) scheme. Deliberately conservative (a real "URL"
#: grammar is far more permissive) — false negatives just leave text
#: unlinkified, which is safe; false positives are the failure mode this
#: contract must avoid, so `_TRAILING_PUNCTUATION` and the scheme check below
#: further narrow what actually gets treated as a link.
_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

#: Punctuation commonly typed right after a URL as part of the surrounding
#: sentence (not part of the link itself), trimmed from the match's tail.
_TRAILING_PUNCTUATION = ".,!?;:'\")]}»”’"

#: A tweet is at most 280 characters, so this is already generous — mainly a
#: defensive cap against pathological input rather than a realistic limit.
MAX_LINK_ENTITIES = 10


@dataclass(frozen=True)
class LinkEntity:
    """One safely-recognized link inside a tweet's `content`.

    `start`/`end` are Python-style character offsets into `content` (i.e.
    `content[start:end] == url`), in Unicode code points — the same unit
    `len(content)` and the 280-character limit are measured in.
    """

    url: str
    start: int
    end: int


def extract_link_entities(content: str) -> list[LinkEntity]:
    """Find every safely-linkifiable URL in `content`, in left-to-right
    order. Never raises — content that looks like a URL but fails the
    scheme/host check is simply not included, not an error.
    """
    entities: list[LinkEntity] = []
    for match in _URL_PATTERN.finditer(content):
        start, end = match.start(), match.end()
        candidate = match.group(0)

        while end > start and candidate[-1] in _TRAILING_PUNCTUATION:
            candidate = candidate[:-1]
            end -= 1
        if not candidate:
            continue

        parsed = urlsplit(candidate)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
            continue

        entities.append(LinkEntity(url=candidate, start=start, end=end))
        if len(entities) >= MAX_LINK_ENTITIES:
            break
    return entities
