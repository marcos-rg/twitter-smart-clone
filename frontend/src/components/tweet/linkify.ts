import type { LinkEntity } from '../../api/types'

export interface TextSegment {
  type: 'text'
  text: string
}

export interface LinkSegment {
  type: 'link'
  text: string
  url: string
}

export type ContentSegment = TextSegment | LinkSegment

/**
 * Splits `content` into plain-text and link segments using the server's
 * `(url, start, end)` spans (`app.services.link_extraction` on the backend
 * — see `docs/tweet-backend.md`'s "Safe link contract"). The backend never
 * returns HTML: `content` is always plain text, and only `http`/`https`
 * spans it explicitly identified become real links. This function only ever
 * *slices* `content` — it never interprets any substring as markup — so a
 * caller that renders `TextSegment.text`/`LinkSegment.text` as React text
 * nodes (never `dangerouslySetInnerHTML`) can't be tricked into rendering
 * executable content, no matter what a malicious author typed (e.g. a
 * `<script>` or `javascript:` string typed as plain text stays plain text,
 * since the backend's link extractor never emits a span for it).
 *
 * Defensive against a malformed span list (out-of-order, overlapping, or
 * out-of-bounds `start`/`end`): entries are sorted by `start` and each span
 * is clamped to never precede the previous segment's end, so segments never
 * overlap or go out of order even if the input does.
 */
export function linkifyContent(content: string, links: LinkEntity[]): ContentSegment[] {
  if (!content) return []
  if (links.length === 0) return [{ type: 'text', text: content }]

  const sorted = [...links].sort((a, b) => a.start - b.start)
  const segments: ContentSegment[] = []
  let cursor = 0

  for (const link of sorted) {
    const start = Math.min(Math.max(link.start, cursor), content.length)
    const end = Math.min(Math.max(link.end, start), content.length)
    if (start > cursor) {
      segments.push({ type: 'text', text: content.slice(cursor, start) })
    }
    if (end > start) {
      segments.push({ type: 'link', text: content.slice(start, end), url: link.url })
    }
    cursor = end
  }

  if (cursor < content.length) {
    segments.push({ type: 'text', text: content.slice(cursor) })
  }

  return segments
}
