# User profiles and search backend (TSC-USER-001)

Backend slice for public profiles, self-editing, profile timeline contract, and
exact/prefix/fuzzy user search.

## API surface

- `GET /api/v1/users/{username}` — case-insensitive public profile lookup.
  Response excludes private fields (`email`, `password_hash`).
- `PATCH /api/v1/users/me` — authenticated self-edit only. Supports partial
  updates for `name`, `username`, `email`, `bio`; validates username regex and
  bio <= 160 chars.
- `GET /api/v1/users/{username}/tweets` — cursor-paginated profile timeline
  (`data` + `page.next_cursor` envelope).
- `GET /api/v1/users/search?q=&mode=exact|prefix|fuzzy` — cursor-paginated user
  search with opaque mode-specific cursors.

## Ordering and pagination

- Exact search: username/name exact match, deterministic ordering.
- Prefix search: username/name prefix match (`ILIKE 'q%'`), deterministic
  ordering.
- Fuzzy search: trigram similarity ranking over username/name.
- All list responses return opaque cursors and reject malformed cursors with
  the standard `400 validation_error` envelope.

## Verification commands

- `uv run pytest tests/test_users.py`
- `uv run pytest tests/repositories/test_user_search_plans.py tests/repositories/test_repositories.py`
