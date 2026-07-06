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
| **Credentials** | Org-scoped encrypted credential storage (Fernet / PBKDF2), generic CRUD endpoints ready to extend with type-specific routes |
| **Account** | Self-service profile updates (email, password, account deletion) |
| **Password reset** | Token-based reset flow with SMTP email delivery |
| **Security** | CSRF double-submit cookie protection, rate limiting via slowapi, SSRF-safe URL validation, security response headers |
| **Admin** | Development-only admin endpoints for inspecting app state |
| **DITA** | `hop_core.dita` (install the `hop-core[dita]` extra) — DITA 1.3 validation with bundled OASIS grammars (`DitaValidator`: DTD validation via `xmllint`, structural fallback, deterministic auto-fixes) and AI-driven correction (`DitaCorrectionService`: validate→correct loop with any injected AI service). For full DTD validation install `xmllint` (`apt-get install libxml2-utils` / `brew install libxml2`); without it the validator falls back to structural checks. |

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

### 1. Install

```bash
pip install git+https://github.com/Heretto/hop-core.git
```

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
)
```

### 4. Wire up the Angular UI

Install the library source alongside your Angular app and add a `paths` alias:

```json
// tsconfig.json
{
  "compilerOptions": {
    "paths": {
      "@heretto/hop-ui": ["path/to/hop-core/ui/src/public-api"]
    }
  }
}
```

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
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { hopAuthInterceptor } from '@heretto/hop-ui';

export const appConfig: ApplicationConfig = {
  providers: [
    provideHttpClient(withInterceptors([hopAuthInterceptor])),
  ],
};
```

Apply the design system. It ships with `@heretto/hop-ui` (Angular 19 / Material
M3) — two steps give every hop-core app a consistent look and feel:

**a. Load the fonts** in your `src/index.html` `<head>` (Inter, Roboto Mono,
Material Symbols Rounded — the theme points `<mat-icon>` at the Symbols face,
so icons render in the light, unfilled line style):

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
@use 'path/to/hop-core/ui/src/lib/theme/index' as hop;

@include hop.hop-core-theme();
```

**[`DESIGN-SYSTEM.md`](DESIGN-SYSTEM.md) is the complete, self-contained
design-system reference** — every token with its value, the full component/API
inventory, a copy-paste app skeleton, and the do/don't rules. Written for both
humans and AI coding agents, so nothing requires scanning the source.
[`ui/README.md`](ui/README.md) is the shorter orientation doc.

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
| `DELETE` | `/credentials/{id}` | ✓ | Delete credential |

---

## Development

```bash
# Install with dev dependencies
make install

# Run the test suite (67 tests)
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
