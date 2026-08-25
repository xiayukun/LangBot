# Spec: LangBot Notify

## Objective

Build a single-owner, self-hosted notification and Agent gateway on top of LangBot while keeping the fork easy to rebase or merge with `langbot-app/LangBot`.

The system manages multiple Feishu bot identities and their reachable people or groups, accepts proactive notification requests over HTTP or MCP, and invokes an Agent for inbound messages only when an explicit route matches. It also provides an Agent-facing guide that an operator can copy into Codex or another Agent so the Agent can discover and call the system safely.

The working product name is **LangBot Notify**. It is a development codename and is not part of any persistent API contract.

## Confirmed requirements

- The repository is a GitHub fork of `langbot-app/LangBot` with an `upstream` remote for future upgrades.
- The local checkout lives in the Windows user profile directory.
- One installation has one owner, while retaining LangBot's existing Workspace boundary internally.
- Multiple Feishu bot identities can be connected and managed through the existing LangBot bot administration flow.
- A proactive API can send one message to one or more managed person/group targets.
- Inbound private or group messages invoke an Agent only when an enabled route matches.
- A group route can require an explicit mention or accept every message.
- Without a matching route, the message is recorded but no pipeline or Agent runs.
- Agent connectors receive conversation history the Agent has not already seen.
- The administration UI exposes bots, targets, routes, Agent connectors, history, test-send, and an Agent guide.
- The Agent guide provides copy-ready instructions and MCP connection configuration.
- Agent-accessible HTTP operations have matching MCP tools and Agent guidance.

## Architecture and reuse boundaries

Reuse the existing LangBot layers instead of introducing a parallel application:

```text
Feishu adapter
  -> RuntimeBot
  -> strict route decision
       -> no match: monitoring/transcript only
       -> match: existing pipeline/Agent execution

HTTP API / Web UI
  -> existing Quart route group
  -> notification service
  -> existing BotService / runtime adapter

MCP /mcp
  -> curated notification tools
  -> the same notification service
```

- Platform-specific Feishu translation remains in `pkg/platform/sources/lark.py`.
- Routing and notification business rules live in platform/application services, not in the Feishu adapter.
- HTTP and MCP call the same service methods.
- Schema changes use Alembic migrations.
- Existing LangBot API response and authorization conventions remain authoritative.

## Tech stack

Detected from the fork at LangBot `4.10.8`:

- Python `>=3.11,<4.0`, Quart `>=0.20`, SQLAlchemy `>=2.0.40`, Alembic, Pydantic `>2.0`.
- MCP Python SDK `>=1.25,<2.0` using FastMCP and Streamable HTTP at `/mcp`.
- React `19.2.1`, React Router `7.15`, TypeScript `5.8`, Vite `8.0`, Tailwind CSS `4.1`, shadcn/ui.
- `uv` for Python dependencies and `pnpm 8.9.2` for the web application.

## Commands

Run from the repository root unless noted:

```powershell
uv sync --dev
uv run pytest tests/unit_tests -q
uv run pytest tests/integration -q
uv run ruff check src tests
uv run main.py

Set-Location web
pnpm install --frozen-lockfile
pnpm test:unit
pnpm lint
pnpm build
```

Focused MCP smoke test after the server is running:

```powershell
uv run --no-sync python tests/manual/mcp_smoke.py
```

## Project structure

```text
src/langbot/pkg/platform/            Existing bot runtime and route resolution
src/langbot/pkg/api/http/service/    Shared application services
src/langbot/pkg/api/http/controller/ HTTP endpoints and boundary validation
src/langbot/pkg/api/mcp/             Curated Agent-facing MCP tools
src/langbot/pkg/entity/persistence/  Persistent entities
src/langbot/pkg/persistence/alembic/ Schema migrations
web/src/app/home/                     Administration UI
web/src/i18n/locales/                 User-facing translations
skills/                               Agent/QA guidance maintained with MCP/API changes
tests/unit_tests/                     Pure and service-level behavior tests
tests/integration/                    HTTP and persistence integration tests
docs/specs/                           Product specifications
```

## API contracts

### Existing single-target operation

Keep the existing endpoint backward compatible:

```http
POST /api/v1/platform/bots/{botUuid}/send_message
X-API-Key: <key>
```

### Managed notification operation

Add an additive, versioned operation:

```http
POST /api/v1/notifications
X-API-Key: <key>
Idempotency-Key: <caller-generated-key>
Content-Type: application/json

{
  "targetIds": ["target-uuid-1", "target-uuid-2"],
  "messageChain": [
    {"type": "Plain", "text": "Service restored"}
  ]
}
```

The response returns one job plus an outcome for every target. Repeating a request with the same owner/workspace and idempotency key returns the original job rather than sending twice.

All errors follow LangBot's existing structured API envelope. Authentication uses an API key and sending requires `runtime.operate`.

### MCP tools

The MCP notification surface includes:

- `send_message`: send through one bot to one person or group, matching the existing HTTP operation.
- `list_notification_targets`: discover reusable destinations configured by the operator.
- `send_notification`: idempotently fan out one message to one or more managed targets.
- `get_notification_job`: inspect the durable per-target outcomes.
- Route inspection tools remain deferred until the durable Agent connector slice.

MCP tools never accept or return Feishu application secrets.

## Routing contract

Each bot has an explicit routing mode:

- `ROUTES_ONLY`: rules are evaluated in order; when none matches, record the inbound message with status `unrouted` and stop.
- `FALLBACK_DEFAULT`: preserve upstream LangBot behavior and use `use_pipeline_uuid` when no rule matches.

New bots created through LangBot Notify default to `ROUTES_ONLY`. Existing upstream data migrates to `FALLBACK_DEFAULT` so an upgrade does not silently disable a working bot.

A route contains a destination pipeline/Agent connector and a trigger:

- private message;
- group message requiring an `At` element for this bot;
- every group message.

Rules remain first-match-wins. The backend is the security and behavior boundary; UI hiding or prompt instructions are not enforcement.

## Agent context contract

The transcript is the source of truth. For each conversation and Agent connector, persist a cursor identifying the last inbound/outbound record already supplied to that Agent.

An Agent invocation receives:

- route and conversation identity;
- a bounded recent transcript;
- all messages after the Agent cursor;
- an optional rolling summary when the transcript exceeds the context window;
- allowed skills/tools and their human-readable instructions.

Advance the cursor only after the connector accepts the invocation. Never put API keys, Feishu secrets, or unrelated conversations in Agent context.

## Agent guide

The administration UI provides a dedicated **Agent Guide** surface with:

- the current instance MCP endpoint;
- a copy-ready MCP client configuration containing an API-key placeholder, never a stored secret;
- a copy-ready system instruction explaining discovery, notification, route, and safety behavior;
- the currently available tool names, generated from the supported product contract rather than hard-coded secrets;
- clear guidance to list/discover resources before sending and never guess IDs.

The first increment extends the existing API Integration panel. A standalone sidebar page may be added later if the content outgrows the panel.

## Code style

Follow the existing repository conventions. Python uses single quotes, four spaces, type annotations on public service methods, and a 120-character line limit. User-visible text is translated at least in `en_US` and `zh_Hans`.

Example service boundary:

```python
async def send_message(
    self,
    context: TenantContext,
    bot_uuid: str,
    target_type: str,
    target_id: str,
    message_chain_data: dict,
) -> None:
    if target_type not in {'person', 'group'}:
        raise ValueError('Unsupported target type')
    await self._send_validated_message(context, bot_uuid, target_type, target_id, message_chain_data)
```

## Testing strategy

- Unit tests cover route resolution, routes-only stopping behavior, request validation, idempotency, and Agent cursor selection.
- Service tests use real service logic with fake runtime adapters rather than asserting internal call order.
- Integration tests cover HTTP authentication/authorization and persistence migrations.
- MCP tests assert tool discovery, authorization, validation, and delegation to the shared service.
- Frontend unit tests cover prompt/config generation as pure functions; browser verification covers copy actions and translated rendering.
- Every behavior change follows red-green-refactor; no failing test is removed or skipped to make the suite pass.

## Security model

Trust boundaries are HTTP/MCP requests, Feishu events, Agent connector responses, and remote webhook destinations.

- Validate external input at controllers/MCP tool boundaries and validate third-party responses.
- Enforce Workspace permissions in code. Prompt text is not an authorization boundary.
- Redact bot credentials from list/get operations and never include them in Agent prompts.
- Treat inbound chat text and Agent output as untrusted data; never execute either as shell, SQL, HTML, or a file path.
- Require HTTPS and an explicit destination policy for remote Agent connectors to mitigate SSRF.
- Bound request size, target fan-out, Agent context size, tool loops, and connector timeouts.
- Record notification and Agent execution audit events without logging secrets.

## Boundaries

### Always

- Keep `origin` pointed at the fork and `upstream` pointed at `langbot-app/LangBot`.
- Add functionality through existing services, MCP, and UI conventions.
- Add tests before behavior code and run focused tests before committing.
- Keep changes additive and localized to reduce future upstream merge conflicts.
- Update HTTP, MCP, tests, and Agent guidance together for Agent-accessible operations.

### Ask first

- Changing authentication flows, API-key semantics, Workspace roles, or CORS.
- Adding a new runtime dependency or external paid service.
- Storing a new category of personal or sensitive data.
- Renaming the GitHub repository or changing the public product name.
- Deploying the service or adding real Feishu credentials.

### Never

- Commit API keys, Feishu credentials, webhook secrets, tokens, or local `.env` files.
- Force-push or rewrite upstream/fork history.
- Make unmatched messages invoke a default Agent in `ROUTES_ONLY` mode.
- Expose all internal APIs automatically through MCP.
- Execute Agent output directly.

## Increment plan

### Slice 0: Fork foundation and living specification

- [x] Fork `langbot-app/LangBot` under the authenticated GitHub account.
- [x] Clone into the Windows user profile and configure `origin` plus `upstream`.
- [x] Record requirements, contracts, commands, boundaries, and verification strategy.
- Verification: remotes point to the expected repositories and the feature branch starts at `upstream/master`.

### Slice 1: Existing send operation through MCP and copy-ready Agent guide

- [x] Add a failing MCP test for `send_message`, permission enforcement, and argument validation.
- [x] Add the smallest MCP tool that calls the existing `BotService.send_message`.
- [x] Extend the existing API Integration UI with a copy-ready Agent instruction and MCP configuration.
- [x] Add `en_US` and `zh_Hans` strings and frontend unit tests for generated content.
- Verification: focused backend tests, authenticated Streamable HTTP smoke test, frontend unit tests,
  targeted lint, and production build. The repository-wide frontend lint currently reports the
  checkout-wide Windows CRLF baseline, so changed frontend files are linted explicitly.

### Slice 2: Strict route-only behavior

- [x] Add a backward-compatible `routing_mode` schema and Alembic migration.
- [x] Add failing tests proving unmatched messages are persisted and never queued in `ROUTES_ONLY` mode.
- [x] Implement route-only stopping and an explicit UI selector; keep `FALLBACK_DEFAULT` for migrated bots.
- [x] Add group trigger choices for mention-only and every message.
- Verification: route resolver/unit tests, person/group callback audit tests, SQLite upgrade/backfill tests,
  bot HTTP tests, MCP smoke test, frontend unit tests, targeted lint, and production build.

### Slice 3: Managed targets and multi-target notifications

- [x] Add target and notification job/attempt entities with idempotency constraints.
- [x] Add target CRUD and paginated listing.
- [x] Add asynchronous fan-out using the existing runtime adapters with bounded concurrency.
- [x] Add HTTP and matching MCP operations plus test-send UI.
- Verification: notification service, HTTP, MCP, and SQLite migration tests;
  frontend unit tests, targeted ESLint, and production build. Browser-surface
  verification remains pending because this Codex environment exposes no
  registered Browser or Chrome runtime tool.

### Slice 4: Agent connectors and durable context

- [ ] Add connector, conversation transcript, and connector cursor entities.
- [ ] Implement HTTP webhook connector first; integrate Codex through the same connector boundary.
- [ ] Inject bounded recent/unseen history and allowed skill instructions.
- [ ] Add connector and route administration UI plus audit/history views.
- Verification: cursor/idempotency tests, prompt-injection boundaries, connector timeout/retry tests, end-to-end route test.

## Success criteria

- `origin` is the user's fork and `upstream/master` can be fetched and merged without history rewriting.
- An operator can connect multiple Feishu bots using existing LangBot flows.
- An API or MCP client can discover resources and send a message without seeing Feishu secrets.
- One request can reliably send to multiple managed targets with per-target results and no duplicate delivery on retry.
- An inbound message without a matching route is visible in history and provably does not invoke any Agent.
- A matching group route follows its configured mention/all-message trigger.
- Agent invocations include unseen conversation history and advance a durable cursor only after acceptance.
- The Agent Guide can be copied into Codex or another Agent and accurately describes the live MCP/API contract.
- Focused tests, lint, type checking, and production builds pass for every completed slice.

## Open questions (not blocking Slice 1)

- Final product and GitHub repository name; `LangBot Notify` is temporary.
- Whether multi-target delivery retries should be automatic in the MVP or operator-triggered first.
- Which Codex integration becomes the default after the HTTP connector: Codex app-server, ACP, or the upstream Agent Runner once its stable release lands.
