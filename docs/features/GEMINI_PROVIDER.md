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

The provider core lives in `tools/gemini_provider/` and currently keeps
credentials only in memory. Native secure persistence is a later UI/integration
step.

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

## Native integration plan

1. Add a Gemini provider adapter to the existing AI Assistant transport.
2. Add a Gemini section at the top of the right AI Agent panel.
3. Add credential slots with masked display, label, optional project id, test
   status, enable/disable state, and remove controls.
4. Add `Test Selected` / `Test All` without exposing secret values.
5. Populate the model dropdown from live model discovery.
6. Route Gemini tool/function calls into the existing native tool registry.
7. Keep Film Context escalation text-first and frame-limited.
8. Run source reconstruction, targeted tests, Windows compile, packaging, and
   packaged-app smoke verification before calling the integration complete.
