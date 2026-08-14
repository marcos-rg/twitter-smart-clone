import { describe, expect, it } from 'vitest'
import { linkifyContent } from '../../../src/components/tweet/linkify'

/**
 * Unit tests for the safe-link splitting helper (TSC-TWEET-002). The
 * backend (`app/services/link_extraction.py`) only ever emits `http`/`https`
 * spans — this helper must never turn any other substring (including a
 * `<script>`-shaped or `javascript:`-shaped one) into a link, since it only
 * slices the given spans and never interprets the string itself.
 */
describe('linkifyContent', () => {
  it('returns a single text segment when there are no links', () => {
    expect(linkifyContent('hello world', [])).toEqual([{ type: 'text', text: 'hello world' }])
  })

  it('returns an empty array for empty content', () => {
    expect(linkifyContent('', [])).toEqual([])
  })

  it('splits text/link segments at the given offsets, preserving link text verbatim', () => {
    const content = 'check https://example.com out'
    const segments = linkifyContent(content, [{ url: 'https://example.com', start: 6, end: 25 }])
    expect(segments).toEqual([
      { type: 'text', text: 'check ' },
      { type: 'link', text: 'https://example.com', url: 'https://example.com' },
      { type: 'text', text: ' out' },
    ])
  })

  it('handles a link at the very start and one at the very end', () => {
    const content = 'https://a.com middle https://b.com'
    const segments = linkifyContent(content, [
      { url: 'https://a.com', start: 0, end: 13 },
      { url: 'https://b.com', start: 21, end: 34 },
    ])
    expect(segments[0]).toEqual({ type: 'link', text: 'https://a.com', url: 'https://a.com' })
    expect(segments.at(-1)).toEqual({ type: 'link', text: 'https://b.com', url: 'https://b.com' })
  })

  it('handles multiple adjacent links with no text between them', () => {
    const content = 'https://a.comhttps://b.com'
    const segments = linkifyContent(content, [
      { url: 'https://a.com', start: 0, end: 13 },
      { url: 'https://b.com', start: 13, end: 26 },
    ])
    expect(segments).toEqual([
      { type: 'link', text: 'https://a.com', url: 'https://a.com' },
      { type: 'link', text: 'https://b.com', url: 'https://b.com' },
    ])
  })

  it('never treats a script-shaped or javascript:-shaped substring as a link when no span covers it', () => {
    const content = '<script>alert(1)</script> and javascript:alert(1) are just plain text'
    const segments = linkifyContent(content, [])
    expect(segments).toEqual([{ type: 'text', text: content }])
    expect(segments.some((segment) => segment.type === 'link')).toBe(false)
  })

  it('is defensive against out-of-order or overlapping spans, never producing overlapping/negative-length segments', () => {
    const content = 'aaaa https://example.com bbbb'
    // Spans given out of order and overlapping — must not crash or corrupt output.
    const segments = linkifyContent(content, [
      { url: 'https://example.com', start: 20, end: 5 }, // malformed: end < start
      { url: 'https://example.com', start: 5, end: 25 },
    ])
    const reconstructed = segments.map((segment) => segment.text).join('')
    expect(reconstructed.length).toBeLessThanOrEqual(content.length)
    for (const segment of segments) {
      expect(segment.text.length).toBeGreaterThanOrEqual(0)
    }
  })

  it('clamps spans that run past the end of the content', () => {
    const content = 'short https://example.com'
    const segments = linkifyContent(content, [{ url: 'https://example.com', start: 6, end: 999 }])
    expect(segments.at(-1)).toEqual({
      type: 'link',
      text: 'https://example.com',
      url: 'https://example.com',
    })
  })
})
