# hop-core

A batteries-included platform library for building AI-powered content creation applications on top of [Heretto](https://heretto.com). Drop it into any FastAPI project to get production-ready authentication, multi-tenant organization management, encrypted credential storage, and a matching Angular UI — all wired up and ready to go.

---

## What's included

### Backend (`hop-core` Python package)

| Area | What you get |
|---|---|
| **Auth** | Email/password registration and login, JWT access + refresh tokens, HttpOnly cookies, bcrypt password hashing with automatic rehash |
| **SSO** | Google (client-side ID token) and Microsoft (server-side OIDC) OAuth flows |
| **Organizations** | Multi-tenant model — every user belongs to one or more orgs, role-based access (admin / member), org switching with re-issued tokens |
| **Invitations** | Token-based email invitations for new and existing users, admin-managed pending invites |
| **Credentials** | Org-scoped encrypted credential storage (Fernet / PBKDF2), generic CRUD, and a registry of credential *types* with field specs and connection testers — an app picks which types it offers and gets a working management UI, including a Test button, for them |
| **Agents** | Org-scoped agent configurations — name, a selected AI configuration, markdown context files, permitted reference URLs, and a separate feedback memory. CRUD at `/agents`, a chat endpoint for testing one, and `hop_core.agents` (`AgentDefinition`, `AgentRunner`) for running one from a job or workflow |
| **Account** | Self-service profile updates (email, password, account deletion) |
| **Password reset** | Token-based reset flow with SMTP email delivery |
| **Security** | CSRF double-submit cookie protection, rate limiting via slowapi, SSRF-safe URL validation, security response headers |
| **Admin** | Development-only admin endpoints for inspecting app state |
| **DITA** | `hop_core.dita` (install the `hop-core[dita]` extra) — DITA 1.3 validation with bundled OASIS grammars (`DitaValidator`: DTD validation via `xmllint`, structural fallback, deterministic auto-fixes) and AI-driven correction (`DitaCorrectionService`: validate→correct loop with any injected AI service). For full DTD validation install `xmllint` (`apt-get install libxml2-utils` / `brew install libxml2`); without it the validator falls back to structural checks. Also DITA → HTML rendering modeled on DITA-OT's HTML5 transform (`DitaRenderer`: every topic type, conref/keyref/filtering hooks, output safe to insert into a page), with an opt-in `POST /dita/render` route (`create_hop_app(include_dita_router=True)`). |

### Frontend (`@heretto/hop-ui` Angular library)

| Component / Service | What you get |
|---|---|
| `HopLoginComponent` | Login form with SSO button support |
| `HopForgotPasswordComponent` | Forgot-password request form |
| `HopResetPasswordComponent` | Token-based password reset form |
| `HopAcceptInvitationComponent` | Invitation acceptance flow (new and existing users) |
| `HopSsoCallbackComponent` | Handles OAuth redirect callbacks |
| `HopAccountComponent` | Profile editor (email, password change) |
| `HopAdminComponent` | Organization member management with invite dialog |
| `HopCredentialsComponent` | Credential management — a tab per registered type, forms built from each type's declared fields, one-click connection testing |
| `HopAgentsComponent` + `HopAgentEditorComponent` | Agent management — a list page plus a full create/edit page with tabs for the AI configuration, context files, reference URLs, memory, and a chat panel for testing the agent |
| `HopDitaContentComponent` + `HopDitaService` | `<hop-dita-content>` shows rendered DITA — `[html]` from your backend's `DitaRenderer`, or `[dita]` rendered via `POST /dita/render` — styled by the theme, with in-topic links scrolling in place and other links reported through `(linkClick)` |
| `HopMainLayoutComponent` | App shell with sidebar navigation, header, and router outlet |
| `HopAuthService` | Reactive auth state, token refresh, login/logout |
| `hopAuthGuard` | Route guard — redirects unauthenticated users to login |
| `hopAdminGuard` | Route guard — restricts routes to org admins |
| `HopAuthInterceptor` | Attaches Bearer token and handles 401 refresh automatically |

---

## Quick start — run the demo

The `demo/` directory is a working full-stack app you can launch with a single command.

**Prerequisites:** Python 3.11+, Node 18+, `uvicorn` (`pip install uvicorn[standard]`)

```bash
git clone https://github.com/Heretto/hop-core.git
cd hop-core
make demo
```

The script installs dependencies, generates secrets, picks free ports, starts both servers, and opens the app in your browser.

Alternatively with Docker Compose:

```bash
cd demo
docker compose up --build
# Backend → http://localhost:8000
# Frontend → http://localhost:80
```

---

## Using hop-core in your own app

> **Read [`AGENTS.md`](AGENTS.md) first.** It is a short integration checklist
> covering the failure modes that bite every new hop-core app — filesystem-path
> dependencies, the required settings that have no defaults, the icon font the
> theme does not ship, and the Angular/CSP interaction that silently disables
> your entire stylesheet. Each item is a command you can run.

### 1. Install

```bash
pip install "hop-core @ git+https://github.com/Heretto/hop-core.git@v0.1.4"
```

Pin to a release tag rather than tracking `main`, so builds are reproducible.
In `requirements.txt`:

```
hop-core @ git+https://github.com/Heretto/hop-core.git@v0.1.4
```

Never install from a local path (`file:///…`) in a committed dependency file —
it works only on the machine that wrote it and can never resolve inside a
Docker build.

### 2. Define your settings

Subclass `HopCoreSettings` to add app-specific config and point it at your `.env`:

```python
from functools import lru_cache
from hop_core.config import HopCoreSettings

class AppSettings(HopCoreSettings):
    my_custom_setting: str = "default"

@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
```

**Required environment variables:**

| Variable | Description |
|---|---|
| `APP_SECRET_KEY` | Secret for session signing (32+ chars) |
| `JWT_SECRET_KEY` | Secret for JWT signing (32+ chars) |
| `ENCRYPTION_KEY` | Key for credential encryption (16+ chars) |
| `DATABASE_URL` | SQLAlchemy URL, e.g. `sqlite:///./app.db` or `postgresql://...` |
| `REDIS_URL` | Redis URL (reserved for future rate limiting backend) |

**Optional variables (with defaults):**

```env
CORS_ORIGINS=http://localhost:4200
COOKIE_SECURE=false
SSO_ONLY=false
SINGLE_ORG_MODE=false
SMTP_HOST=
SMTP_FROM_EMAIL=
GOOGLE_OAUTH_CLIENT_ID=
MICROSOFT_OAUTH_CLIENT_ID=
MICROSOFT_OAUTH_CLIENT_SECRET=
```

### 3. Create the app

```python
from hop_core.app_factory import create_hop_app

app = create_hop_app(
    settings_factory=get_settings,
    title="My App",
    version="1.0.0",
)
```

`create_hop_app` registers all platform routes under `/api/v1`, wires up CORS, CSRF, sessions, rate limiting, and runs `CREATE TABLE IF NOT EXISTS` on startup.

**Options:**

```python
app = create_hop_app(
    settings_factory=get_settings,
    extra_routers=[my_domain_router],   # additional APIRouters
    include_admin=True,                 # dev-only admin routes (default: True)
    include_superadmin=True,            # superadmin routes (default: True)
    include_credentials_router=True,    # generic credentials CRUD (default: True)
                                        # set False if you add type-specific routes
    include_agents_router=True,         # agent configuration CRUD (default: True)
)
```

### 4. Wire up the Angular UI

Install the packaged library from a hop-core release:

```jsonc
// package.json
"@heretto/hop-ui": "https://github.com/Heretto/hop-core/releases/download/v0.1.4/heretto-hop-ui-0.1.4.tgz"
```

npm cannot install this package from a git URL (it lives in `ui/`), and the
`vX.Y.Z.tar.gz` GitHub attaches to every release is not an npm package — see
[`DESIGN-SYSTEM.md`](DESIGN-SYSTEM.md) §1. Resolving the library from source
through a `tsconfig` `paths` alias is for work **inside this repo only**: a path
reaching outside the project resolves on one machine and never in a Docker build.

Configure routes and the auth interceptor:

```typescript
// app.routes.ts
import { hopAuthGuard, hopAdminGuard } from '@heretto/hop-ui';
import { HopLoginComponent, HopMainLayoutComponent } from '@heretto/hop-ui';

export const routes: Routes = [
  { path: 'login', loadComponent: () => HopLoginComponent },
  {
    path: '',
    canActivate: [hopAuthGuard],
    loadComponent: () => ShellComponent,
    children: [
      { path: 'account', loadComponent: () => HopAccountComponent },
      { path: 'admin', canActivate: [hopAdminGuard], loadComponent: () => HopAdminComponent },
    ],
  },
];

// app.config.ts
import { provideZoneChangeDetection } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { hopAuthInterceptor } from '@heretto/hop-ui';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection(),   // hop-ui needs Zone.js; see AGENTS.md §7
    provideHttpClient(withInterceptors([hopAuthInterceptor])),
  ],
};
```

Apply the design system. It ships with `@heretto/hop-ui` (Angular 22 / Material
M3) — two steps give every hop-core app a consistent look and feel:

**a. Load the fonts** in your `src/index.html` `<head>` (Inter, Roboto Mono,
Material Symbols Rounded — the theme points `<mat-icon>` at the Symbols face,
so icons render in the light, unfilled line style):

The package does **not** ship these fonts — loading them is the application's
job, and Material Symbols is load-bearing: if it fails to load, every icon
renders its ligature name instead of a glyph. Allow `fonts.googleapis.com`
(`style-src`) and `fonts.gstatic.com` (`font-src`) in any CSP.

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;500&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,300..500,0..1,0&display=block" rel="stylesheet">
```

**b. Include the theme** in your global stylesheet — one mixin themes the whole
app (design tokens, the Material M3 theme + `--mat-sys-*` bridge, base styles,
and component overrides):

```scss
// styles.scss
@use '@heretto/hop-ui/theme' as hop;

@include hop.hop-core-theme();
```

**[`DESIGN-SYSTEM.md`](DESIGN-SYSTEM.md) is the complete, self-contained
design-system reference** — every token with its value, the full component/API
inventory, a copy-paste app skeleton, and the do/don't rules. Written for both
humans and AI coding agents, so nothing requires scanning the source.
[`ui/README.md`](ui/README.md) is the shorter orientation doc.

---

## Credentials

A credential is an encrypted payload plus a **type**. hop-core does not know
what a Jira token is — an application registers the types it offers, each with
a *field spec*, and that one registration drives everything: the management
UI's form, the API's validation, and which fields are safe to return.

```python
from hop_core.credentials import AI_PROVIDER_TYPES, register_builtin_types

register_builtin_types("jira", "heretto", *AI_PROVIDER_TYPES)
```

hop-core ships the three kinds the Release Notes Agent uses. Register the
subset that makes sense for your app — anything you leave out never appears in
the UI.

| Built-in type | Tab | Fields | Connection test |
|---|---|---|---|
| `jira` | Jira | Server URL, Email, API Token *(secret)* | `GET /rest/api/3/myself` |
| `heretto` | Heretto | Server URL, Username, API Token *(secret)* | authenticated `GET /api/v1/user` |
| `anthropic`, `openai`, `gemini` | AI Providers | API Key *(secret)*, Model | a 16-token completion |

The three AI provider types share a `group`, so they render as **one** "AI
Providers" tab with a provider picker rather than three tabs. They are also
marked `is_ai_configuration`, which is what makes them selectable as an
[agent's](#agents) model configuration — one registration, both behaviours.

Declare your own types the same way, with an optional tester:

```python
from hop_core.credentials import CredentialTesterRegistry, CredentialTestResult

CredentialTypeRegistry.register("zendesk", label="Zendesk", icon="support_agent", fields=[
    {"name": "subdomain", "label": "Subdomain", "summary": True},
    {"name": "api_token", "label": "API Token", "type": "password", "secret": True},
])

async def test_zendesk(payload) -> CredentialTestResult:
    ...  # returns CredentialTestResult(success=..., message=...)

CredentialTesterRegistry.register("zendesk", test_zendesk)
```

### Testing a connection

Every built-in type ships a tester, registered alongside the type — importing
the type is all it takes to get a working **Test** button. A type with no
tester simply does not show one (`testable: false` on its spec).

`POST /credentials/{id}/test` decrypts the credential, calls the service, and
returns `{success, message, details, exchange, tested_at}`. A credential that
cannot connect is a **200 with `success: false`**, not an HTTP error: the
request worked, the connection did not, and the UI wants to show why.

`exchange` is what makes a failure actionable — the method and URL called, the
HTTP status, how long it took, and the service's own response body:

```jsonc
{
  "success": false,
  "message": "Anthropic rejected the API key.",
  "exchange": {
    "method": "POST",
    "url": "https://api.anthropic.com/v1/messages",
    "status_code": 401,
    "response_body": "{\"type\":\"error\",\"error\":{\"type\":\"authentication_error\",\"message\":\"API key is invalid.\"}}",
    "body_truncated": false,
    "duration_ms": 135
  }
}
```

The Test button opens a dialog that renders this — status, timing, the request
line, and the response body pretty-printed in a code panel with a Copy button.
The row's status chip reopens the last result. `exchange` is `null` when no
request was made (a URL refused by validation, a missing field), and the dialog
says so rather than showing an empty panel.

Four things the testers do deliberately:

- **User-supplied hosts go through `validate_server_url`** — the Jira and
  Heretto URLs come from a form, so they are checked against loopback, link-local
  and RFC-1918 ranges before any request. A test against `https://169.254.169.254`
  fails with "URL must not point to a private or internal address" and makes no
  request at all.
- **Redirects are never followed.** A redirect is the simplest way for a host
  that passed that check to hand the request to one that would not have; a 3xx
  is reported as a failure instead.
- **Nothing secret reaches the result.** Messages say what happened, never what
  was sent, and an unexpected exception is logged server-side and reported
  generically rather than echoed. The response body is passed through verbatim
  but scrubbed of the credential's own secret values first — some APIs echo the
  request back, key and all — and truncated to 4000 characters.
- **The endpoint is rate-limited to 10/minute.** Every call leaves the building
  and an AI provider test costs real tokens.

Field flags that matter:

- **`secret: True`** — write-only. Never returned by any endpoint; a response
  says only *which* secret fields are set (`secrets_set`), never a value, not
  even masked. Submitting one blank on update keeps the stored value, which is
  how the edit form works without ever holding the secret.
- **`summary: True`** — shown as a column in the credential list.
- **`required`** — enforced on create and update. A type with no registered
  spec is not validated at all, so existing free-form credentials keep working.

### Managing credentials in the UI

`HopCredentialsComponent` is the whole page — a tab per type or group, a table
with each type's summary columns, and an add/edit dialog whose form is built
from the field spec. It needs no configuration; it renders whatever the backend
registered.

```typescript
{ path: 'credentials', loadComponent: () => import('@heretto/hop-ui').then(m => m.HopCredentialsComponent) },
```

---

## Agents

An **agent** is a reusable, organization-scoped configuration:

| Part | What it is |
|---|---|
| **Name** and description | How jobs and workflows refer to the agent |
| **AI configuration** | The model the agent runs on, selected from configurations established separately — one `ai_configuration_id`, one select box |
| **Context files** | Markdown documents the agent is given as reference on every run — style guides, templates, domain background |
| **Permitted URLs** | URL prefixes the agent may read for additional reference. An entry covers the pages beneath it, and a leading `*.` on the host covers subdomains |
| **Feedback memory** | What the agent has learned from feedback on past work, kept deliberately separate from context files: context is what the agent was given, memory is what it has picked up |

### The model configuration is established separately

An **AI configuration** is an ordinary [credential](#credentials) whose type
was registered as an AI type — `anthropic`, `openai` and `gemini` are, out of
the box. Its *type* is the provider, and its payload carries the API key and
the model. Create one in the credentials UI, or through the API:

```jsonc
// POST /credentials — the same generic endpoint as any other credential
{"type": "anthropic", "name": "Anthropic - Opus 5",
 "credentials": {"api_key": "sk-ant-...", "model": "claude-opus-5"}}
```

An agent then points at one. `GET /agents/ai-configurations` lists what is
available — id, name, provider, provider label, and model, **never the API
key** — which is exactly what the editor's single select box renders. Several
agents can share one configuration, so rotating a key or moving to a new model
is one edit in one place.

Deleting a configuration does not delete the agents using it: the reference is
set to null and they show as unconfigured.

**Agents do nothing on their own.** A job or workflow gives one input and
instructions and receives its output back:

```python
from hop_core.agents import AgentDefinition, AgentRequest, AgentRunner
from hop_core.models.agent import Agent

agent = db.query(Agent).filter(Agent.id == agent_id).one()
definition = AgentDefinition.from_model(agent)

result = await AgentRunner(ai_service).run(
    definition,
    AgentRequest(instructions="Write the release notes", input=merged_prs),
)
result.output  # what the workflow does something with
```

`AgentDefinition` composes the system prompt from the agent's description,
context files, permitted URLs, and feedback memory, and resolves the selected
AI configuration into `definition.ai_configuration` (`credential_id`,
`provider`, `model` — no API key). `AgentRequest` supplies the per-run
instructions and input, plus `temperature` / `max_tokens`: the configuration
owns *which* model, the job owns *how hard it thinks*. Running an agent with no
configuration raises `AgentNotConfigured` rather than quietly falling back to a
service default.

`ai_service` is any object with an `async generate(request) -> result` method
exposing `.content` (`hop_core.ai.SupportsGenerate`) — hop-core does not pick a
model vendor and fetches no keys; the host app's service decrypts the
credential named by `credential_id` itself.

Before fetching a URL on the agent's behalf, check it against the agent's list:

```python
if definition.is_url_permitted(url):
    ...
```

### Testing an agent

`POST /agents/{id}/chat` runs the agent against a conversation so you can see
how it actually behaves — same composed system prompt, same AI configuration,
same context and memory a job would get. The whole conversation goes up each
time and **nothing is stored**: a test session lives in the browser and leaves
no trace on the agent.

```jsonc
// → POST /agents/{id}/chat
{"messages": [{"role": "user", "content": "Summarise PR #12"}]}

// ← 200
{"message": {"role": "assistant", "content": "…"},
 "provider": "anthropic", "model": "claude-opus-5",
 "ai_configuration_name": "Anthropic — Opus 5",
 "system_prompt": "You are Release Notes Writer.\n\n…"}
```

The reply carries the composed `system_prompt` back, because when an agent
misbehaves the first question is always *what was it actually told*.

A vendor failure comes back as **502 with the vendor's own words** —
`Anthropic returned HTTP 401: API key is invalid.` — rather than a generic
error. The endpoint is rate-limited to 30/minute; every message is a paid call.

**This is the one place hop-core talks to a model vendor.** Registering an AI
credential type also registers a generator for it, and the chat endpoint builds
a `CredentialAiService` from the agent's stored configuration:

```python
from hop_core.agents import AiProviderRegistry, CredentialAiService

# Bring your own vendor:
AiProviderRegistry.register("bedrock", generate_with_bedrock)
```

Everything else stays injectable — `AgentRunner` still takes any
`SupportsGenerate`, so a job pipeline can keep using the app's own client.

### Managing agents in the UI

Agent management is two pages: `HopAgentsComponent` lists them, and
`HopAgentEditorComponent` creates and edits one on its own full page — tabs for
the AI configuration, context files, reference URLs, and memory. Editing is a
page rather than a dialog because an agent is a substantial thing to author,
and the page has room to grow.

In the list, **clicking an agent opens it** — there is no Edit button, and the
overflow menu holds duplicate, activate and delete.

The editor's five tabs are Configuration, Context, Reference URLs, Memory and
**Test**. Test is the chat panel: send a message, see the reply, and expand the
system prompt that produced it. It tells you plainly when it cannot
run — the agent is unsaved, has no AI configuration, or has unsaved edits that
the conversation will not reflect.

Mount both with the exported routes:

```typescript
import { HOP_AGENT_ROUTES } from '@heretto/hop-ui';

{ path: 'agents', children: HOP_AGENT_ROUTES },   // '', 'new', ':agentId'
```

`HOP_AGENT_ROUTES` is componentless, so its pages render in whatever outlet
already holds the list — no nested `<router-outlet>` needed. The editor
navigates back relatively, so mounting the set under any path works.

---

## API reference

All routes are prefixed with `/api/v1` by default (configurable via `API_PREFIX`).

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/register` | — | Create account (+ org) |
| `POST` | `/auth/login` | — | Login, returns tokens |
| `POST` | `/auth/logout` | — | Clear auth cookies |
| `POST` | `/auth/refresh` | — | Refresh access token |
| `POST` | `/auth/forgot-password` | — | Send reset email |
| `POST` | `/auth/reset-password` | — | Reset with token |
| `GET` | `/sso/google` | — | Google SSO |
| `GET` | `/sso/microsoft` | — | Microsoft SSO |
| `GET` | `/account/me` | ✓ | Get profile |
| `PUT` | `/account/me` | ✓ | Update profile |
| `DELETE` | `/account/me` | ✓ | Delete account |
| `GET` | `/organizations` | ✓ | List user's orgs |
| `POST` | `/organizations` | ✓ | Create org |
| `GET` | `/organizations/current` | ✓ | Get active org |
| `PATCH` | `/organizations/current` | admin | Rename org |
| `POST` | `/organizations/switch/{id}` | ✓ | Switch active org |
| `GET` | `/organizations/current/members` | ✓ | List members |
| `PATCH` | `/organizations/members/{id}` | admin | Update member role |
| `DELETE` | `/organizations/members/{id}` | admin | Remove member |
| `POST` | `/organizations/invitations` | admin | Create invitation |
| `GET` | `/organizations/invitations` | admin | List pending invites |
| `DELETE` | `/organizations/invitations/{id}` | admin | Cancel invite |
| `POST` | `/organizations/invitations/accept/{token}` | ✓ | Accept invite (existing user) |
| `GET` | `/invitations/info/{token}` | — | Get invite details |
| `POST` | `/invitations/accept/{token}` | — | Accept invite (new user) |
| `GET` | `/credentials` | ✓ | List credentials |
| `POST` | `/credentials` | ✓ | Create credential |
| `GET` | `/credentials/{id}` | ✓ | Get credential |
| `PUT` | `/credentials/{id}` | ✓ | Update credential |
| `GET` | `/credentials/types` | ✓ | Registered credential types and their fields |
| `POST` | `/credentials/{id}/test` | ✓ | Test that a credential reaches its service |
| `DELETE` | `/credentials/{id}` | ✓ | Delete credential |
| `GET` | `/agents` | ✓ | List agents (summaries) |
| `POST` | `/agents` | ✓ | Create agent |
| `GET` | `/agents/ai-configurations` | ✓ | AI configurations an agent can select |
| `GET` | `/agents/{id}` | ✓ | Get agent with context files and memory |
| `PUT` | `/agents/{id}` | ✓ | Update agent (partial) |
| `DELETE` | `/agents/{id}` | ✓ | Delete agent |
| `PUT` | `/agents/{id}/memory` | ✓ | Replace feedback memory |
| `POST` | `/agents/{id}/memory` | ✓ | Append one piece of feedback |
| `POST` | `/agents/{id}/chat` | ✓ | Talk to an agent to test its behaviour |

---

## Development

```bash
# Install with dev dependencies
make install

# Run the test suite
make test

# Verbose test output
make test-v

# Run the demo app locally
make demo
```

Tests use an in-memory SQLite database and a session-scoped TestClient. No external services required.

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
