# Gemini Provider

`Edit-Aja-Gemini` uses Gemini as the primary cloud AI provider while preserving
the existing native Edit Aja / Kdenlive tool registry and deterministic local
editing paths.

## Goals

- Keep the AI Agent as the primary right-hand sidebar.
- Support up to 100 configured Gemini credentials.
- Never write real API keys into the repository, logs, crash messages, or tests.
- Discover available Gemini models dynamically instead of hard-coding model names.
- Keep Gemini transport separate from timeline execution so all edits still go
  through the native `kdenlive_*` tool registry and remain editable/undoable.
- Preserve Local Edit and Film Context as local-first helpers so the Gemini API
  receives only the context it actually needs.

## Credential behavior

The provider core lives in `tools/gemini_provider/`. The native Qt Gemini
integration is also intentionally memory-only today: API keys can be managed in
the AI Agent sidebar, but they are not persisted to disk. OS-backed secure
Windows persistence remains a separate follow-up.

`GeminiKeyPool` deduplicates keys, enforces a maximum of 100 unique keys, masks
keys for UI/log output, and tracks credential health.

Gemini quotas are project-scoped rather than API-key-scoped. For that reason,
a `429` response cools down every configured key with the same `project_id`.
If project identity is unknown, unknown-project keys share one conservative
quota scope instead of pretending that extra keys automatically create extra
quota.

Authentication failures (`401`/`403`) invalidate only the failing credential.
Transient server failures use a short per-key cooldown. Request-shape errors
such as `400` do not rotate keys because changing credentials would not fix the
request.

## Model discovery

`GeminiRestClient.list_models()` calls the official `models.list` endpoint using
the `x-goog-api-key` header and filters to models that support
`generateContent`. Pagination is handled automatically and no model name is
hard-coded into the provider core.

For current API behavior, see:

- https://ai.google.dev/api/models
- https://ai.google.dev/api
- https://ai.google.dev/gemini-api/docs/api-key
- https://ai.google.dev/gemini-api/docs/rate-limits

## Security

Google's September 2026 API-key transition means the application should expect
current Gemini authorization keys rather than relying on old unrestricted
standard keys. Keys must never be committed to GitHub.

The native Windows integration should use OS-backed credential storage before
persistent multi-key management is exposed in the packaged app.

## Native integration status

The built-in right-side AI Agent now has a native Qt Gemini transport, a masked
multi-key credential manager with optional project IDs, live model discovery,
and direct Gemini function calling into the existing `kdenlive_*` registry.
Film Context remains text-first and frame-limited.

The native transport has passed source reconstruction, Windows compilation,
packaging, installer startup smoke, and functional packaged-editor smoke tests.

Hardening rules:

- Cancel invalidates the current request epoch before aborting the network reply,
  so stale callbacks cannot rotate credentials or surface a false API error.
- Native requests leave Gemini sampling at the model default instead of forcing
  `temperature`, which is important for current Gemini 3.x models and future
  models that reject deprecated sampling parameters.
- Tool function responses and selected visual frames are returned in one user
  turn rather than two consecutive user turns.
- API keys remain memory-only until OS-backed Windows credential storage is
  implemented.
