"""Unit tests for `app.services.link_extraction` (TSC-TWEET-001's "safely
renderable link data" contract). No database/Redis needed — pure function.
"""

from __future__ import annotations

from app.services.link_extraction import extract_link_entities


def test_extracts_a_single_https_url_with_correct_offsets() -> None:
    content = "check this out https://example.com/path?q=1 cool right"
    [entity] = extract_link_entities(content)
    assert entity.url == "https://example.com/path?q=1"
    assert content[entity.start : entity.end] == entity.url


def test_extracts_multiple_urls_in_order() -> None:
    content = "http://a.example.com and https://b.example.com are both here"
    entities = extract_link_entities(content)
    assert [e.url for e in entities] == ["http://a.example.com", "https://b.example.com"]
    assert entities[0].start < entities[1].start


def test_trims_trailing_sentence_punctuation() -> None:
    content = "see (https://example.com/thing), it's great!"
    [entity] = extract_link_entities(content)
    assert entity.url == "https://example.com/thing"


def test_javascript_scheme_is_never_linkified() -> None:
    content = "click javascript:alert(1) for fun"
    assert extract_link_entities(content) == []


def test_data_scheme_is_never_linkified() -> None:
    content = "data:text/html,<script>alert(1)</script>"
    assert extract_link_entities(content) == []


def test_scheme_relative_url_is_never_linkified() -> None:
    content = "go to //evil.example.com/path now"
    assert extract_link_entities(content) == []


def test_url_without_host_is_rejected() -> None:
    content = "broken http:// nothing after it"
    assert extract_link_entities(content) == []


def test_no_urls_returns_empty_list() -> None:
    assert extract_link_entities("just a plain tweet, no links here") == []


def test_caps_at_max_link_entities() -> None:
    content = " ".join(f"https://example.com/{i}" for i in range(50))
    entities = extract_link_entities(content)
    assert len(entities) == 10
