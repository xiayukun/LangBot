---
name: langbot-mcp-ops
description: Operate a LangBot instance through its built-in MCP (Model Context Protocol) server. Use when an AI agent needs to send a person or group message or manage LangBot — bots, pipelines, models, knowledge bases, MCP servers, and skills — over MCP instead of raw HTTP. Covers the /mcp endpoint, API-key auth (web-UI lbk_ keys and the config.yaml global key), safe target discovery, the tool surface, and client configuration. Triggers on "langbot mcp", "manage langbot via mcp", "send through langbot", "langbot /mcp", "langbot mcp server".
---

# LangBot MCP Operations

LangBot exposes an **MCP server** so AI agents can manage an instance
programmatically. It mirrors a curated subset of the HTTP service API.

## Endpoint

```
http://<langbot-host>:5300/mcp
```

Transport: **streamable HTTP** (stateless, JSON responses). Same host/port as
the web UI and HTTP API.

## Authentication

Reuses the same API keys as the HTTP API. Send either header:

```
X-API-Key: <api-key>
# or
Authorization: Bearer <api-key>
```

Two kinds of key are accepted:

1. **Web-UI key** — created in the web UI (sidebar → API Keys), prefixed `lbk_`.
   The secret is shown once; only its SHA-256 hash is stored. Each key is bound
   to one Workspace and has explicit scopes, status, optional expiry, and
   last-used metadata. The key determines the Workspace; callers cannot switch
   it with `X-Workspace-Id`.
2. **Global API key** — set in `data/config.yaml` under `api.global_api_key`.
   Requires no login session and no DB record; does not need the `lbk_` prefix.
   It is accepted only by a community instance with exactly one local
   Workspace and is disabled for SaaS multi-Workspace operation. Leave empty to
   disable. See the `langbot-deploy` skill for config details.

Invalid, revoked, or expired keys get `401 Unauthorized`. A valid key whose
scopes do not authorize a tool gets `403 Forbidden`.

## Client configuration

Codex (`config.toml`), keeping the API key in an environment variable:

```toml
[mcp_servers.langbot_notify]
url = "http://<langbot-host>:5300/mcp"
env_http_headers = { "X-API-Key" = "LANGBOT_API_KEY" }
required = false
default_tools_approval_mode = "writes"
```

Generic MCP client:

```json
{
  "mcpServers": {
    "langbot": {
      "url": "http://<langbot-host>:5300/mcp",
      "headers": { "X-API-Key": "<api-key>" }
    }
  }
}
```

## Tool surface

The tools wrap the LangBot service layer. Current tools (v1):

| Tool | Purpose |
| --- | --- |
| `get_system_info` | Version, edition, instance id |
| `list_bots` / `get_bot` / `create_bot` / `update_bot` / `delete_bot` | Manage messaging-platform bots (secrets redacted on read) |
| `list_notification_targets` | List operator-managed people and groups that are safe to select by UUID |
| `send_notification` / `get_notification_job` | Send to one or more managed targets idempotently and inspect every outcome |
| `send_message` | Send directly through a selected bot to one unmanaged person or group |
| `list_pipelines` / `get_pipeline` / `create_pipeline` / `update_pipeline` / `delete_pipeline` | Manage pipelines |
| `list_llm_models` / `get_llm_model` / `list_embedding_models` / `list_model_providers` | Inspect models & providers |
| `list_knowledge_bases` / `get_knowledge_base` / `retrieve_knowledge_base` | RAG knowledge bases (incl. semantic search) |
| `list_mcp_servers` | External MCP servers LangBot connects to (as a client) |
| `list_skills` / `get_skill` | Installed skills |

Mutating tools (`create_*`, `update_*`) take a JSON object matching the same
shape as the corresponding HTTP API request body. Discover resources with the
`list_*` / `get_*` tools before mutating; identifiers are UUIDs. Reads require
`resource.view`; mutations require `resource.manage`. All service calls inherit
the immutable Workspace context authenticated at the MCP transport boundary.

Prefer managed notifications for recurring automation. First call
`list_notification_targets`, then call `send_notification` with:

- `target_ids`: one or more discovered target UUIDs (maximum 100, no duplicates);
- `message_chain`: a non-empty LangBot message-chain JSON array, for example
  `[{"type":"Plain","text":"Service restored"}]`;
- `idempotency_key`: a stable caller-generated key for this intended event.
  Reuse it when retrying the same request. Reusing it with different targets or
  content is rejected.

`send_notification` is a write and requires `runtime.operate`; target discovery
and `get_notification_job` require `resource.view`. A result has an overall
status plus one `sent` or `failed` outcome per target. The direct `send_message`
tool remains available for one-off unmanaged destinations. Its arguments are:

- `bot_uuid`: an existing bot UUID discovered with `list_bots`;
- `target_type`: exactly `person` or `group`;
- `target_id`: the platform-specific person or group identifier;
- `message_chain`: the existing LangBot message-chain JSON array.

Never guess a bot UUID or target ID. If no configured target is available, ask
the operator for one. Do not request, echo, or place platform credentials or API
keys in tool arguments.

Bot inbound routing is explicit:

- New bots default to `routing_mode: "routes_only"`. An inbound message that
  matches no enabled rule is audited as `unrouted` and does not enter an Agent
  pipeline.
- Bots migrated from an older LangBot database use
  `routing_mode: "fallback_default"` so their existing default-pipeline behavior
  remains intact.
- Set `fallback_default` on a new bot only when the operator explicitly asks for
  compatibility behavior and has selected `use_pipeline_uuid`. Unknown routing
  modes are rejected by the service and fail closed at runtime.
- Each routing rule may set `group_trigger` to `mention` (only when the bot is
  explicitly mentioned) or `all` (every group message matching that rule).
  Existing rules without the field keep `all`; new UI-created rules default to
  `mention`.

## How to use

1. Get an API key (web UI key, or set `api.global_api_key` in config.yaml).
2. Point your MCP client at `http://<host>:5300/mcp` with the key header.
3. Call `get_system_info` to confirm connectivity.
4. Use `list_*` tools to discover, then `get_*` / `create_*` / `update_*` /
   `delete_*` as needed.
5. To send a notification, call `list_notification_targets`, select only
   operator-managed target UUIDs, then call `send_notification` with a stable
   idempotency key. Use `get_notification_job` to inspect delivery outcomes.
6. Use `list_bots` plus `send_message` only when the operator explicitly needs
   a one-off destination that is not yet managed.

## Implementation & maintenance (for LangBot developers)

- Server: `src/langbot/pkg/api/mcp/server.py` (FastMCP). Tools call the service
  layer directly, so the MCP surface stays aligned with the API.
- Mount: `src/langbot/pkg/api/mcp/mount.py` — an ASGI dispatcher fronting Quart,
  authenticating `/mcp` requests, running the streamable-HTTP session manager.
- Smoke test: `tests/manual/mcp_smoke.py`.

> When you add, remove, or change an HTTP API endpoint that should be
> agent-accessible, update the corresponding MCP tool **and** this skill. The
> MCP tool surface and the API must stay aligned (see `AGENTS.md`).

## Pitfalls

- `/mcp` is the **server** LangBot exposes. The `/api/v1/mcp` routes are the
  **client** side (managing external MCP servers LangBot connects to). Don't
  confuse them.
- A `401` means the key is wrong, missing, revoked, expired, or (for the global
  key) `api.global_api_key` is empty or the instance is not an OSS singleton.
- A `403` means the key is valid but lacks the permission required by the tool.
- The global key is plaintext in config.yaml — only enable it on trusted/internal
  deployments and serve over HTTPS.
