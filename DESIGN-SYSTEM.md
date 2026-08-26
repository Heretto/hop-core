# hop-core Design System — Complete Reference

> **Audience:** humans and AI coding agents building an app on hop-core.
> This file is intentionally **self-contained**: every token, component, API
> signature, and rule needed to build a correctly-styled hop-core app is
> inlined here. You should not need to scan the repository. When this document
> and the source disagree, trust the source under `ui/src/lib/theme/` and
> `ui/src/public-api.ts` — and update this file.

The design system is a **CSS-variable token layer + Angular Material (M3)
overrides**, not a bespoke component library. Angular Material remains the
component substrate; one SCSS mixin themes everything. Consistency comes from
the tokens; custom interactions never have to fight the system.

- **Stack:** Angular 19 · Angular Material 19 · Angular CDK 19
- **Library:** `@heretto/hop-ui` (source at `ui/`, entry `ui/src/public-api.ts`)
- **Brand:** navy `#011627` primary · teal `#79ECDD` accent · magenta `#AD4780` tertiary · gold `#F7D48E` warning

---

## 1. Integration (three steps)

### Step 1 — Install the library

```jsonc
// package.json — the packaged tarball attached to a hop-core release
"@heretto/hop-ui": "https://github.com/Heretto/hop-core/releases/download/v0.1.2/heretto-hop-ui-0.1.2.tgz"
```

Pin to a release tag so builds are reproducible. Asset names follow the tag:
`vX.Y.Z` produces `heretto-hop-ui-X.Y.Z.tgz`.

Two traps worth knowing:

- **npm cannot install from a subdirectory of a git repo**, so there is no
  `git+https://…` form for this package — it lives in `ui/`. Use the asset URL.
- **The `vX.Y.Z.tar.gz` that GitHub attaches to every release is not an npm
  package.** Its root is `hop-core-X.Y.Z/` rather than `package/` and it carries
  no build output; `npm install` fails with `ENOENT: Could not read package.json`.
  Use `heretto-hop-ui-*.tgz`.

<details>
<summary>Consuming from source (inside this repo only)</summary>

`demo/` resolves the library from source through a tsconfig alias, so demo builds
compile the library and give the fastest full check:

```jsonc
// tsconfig.json
{
  "compilerOptions": {
    "paths": { "@heretto/hop-ui": ["path/to/hop-core/ui/src/public-api"] }
  }
}
```

Do **not** use this in a consuming application. A path reaching outside the
project works only on one machine and can never resolve inside a Docker build.
It also bypasses the packaged artifact entirely, so packaging regressions go
undetected.

</details>

### Step 2 — Fonts in `src/index.html` `<head>`

```html
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#ffffff">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@400;500&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,300..500,0..1,0&display=block" rel="stylesheet">
```

Put `class="mat-typography"` on `<body>`.

**The package does not ship these fonts — loading them is the application's job**,
and Material Symbols is load-bearing rather than cosmetic. The theme points
`mat-icon` at it, so if it never loads, every icon renders its ligature *name*:
a button reads `play_arrow` instead of showing a play glyph.

Two consequences:

- **Allow both hosts in your CSP**: `fonts.googleapis.com` under `style-src`,
  `fonts.gstatic.com` under `font-src`.
- **Consider self-hosting for restricted deployments.** Google's variable icon
  font is ~3 MB, and browser font-blocking settings or egress rules can prevent
  it loading at all. A static instance pinned to the values the theme requests
  (`FILL` 0, `wght` 300, `opsz` 24) is ~478 KB, renders identically, and keeps all
  glyphs — so dynamically chosen icon names still resolve.

### Step 3 — One mixin in the global stylesheet

```scss
// src/styles.scss — this is the ENTIRE required global stylesheet
@use '@heretto/hop-ui/theme' as hop;

@include hop.hop-core-theme();
```

Requires `@heretto/hop-ui` >= 0.1.1, which is the first release to ship the theme
stylesheets inside the package. It resolves from `node_modules` with no
`angular.json` or `stylePreprocessorOptions.includePaths` changes. Inside this
repo, `demo/` uses the source path `'path/to/hop-core/ui/src/lib/theme/index'`
instead — that form is for in-repo use only, per Step 1.

The mixin emits: all semantic CSS custom properties (section 2), the Material
M3 theme + `--mat-sys-*` bridge, a CSS reset, typography, all Material
component overrides (section 5), and the utility classes (section 7). Nothing
renders until the mixin is included.

> **If you serve the app with a Content-Security-Policy, check one more thing.**
> Angular's production build defaults to `optimization.styles.inlineCritical`,
> which loads your stylesheet inert (`media="print"`) and activates it with an
> inline `onload` handler. A CSP without `'unsafe-inline'` for scripts blocks
> that handler, so the stylesheet downloads with HTTP 200 and is never applied —
> the theme silently does not take effect, and icons render as their ligature
> names. Set `"inlineCritical": false` on the production configuration. See
> [`AGENTS.md`](AGENTS.md) §4.

---

## 2. Design tokens (CSS custom properties)

Consume tokens with `var(--token-name)`. **Never hard-code hex values in
components** — this is the golden rule. Values below are the light theme
(the active theme; a dark block ships inert, see section 10).

### Surfaces & backgrounds

| Token | Value | Use for |
|---|---|---|
| `--bg-primary` | `#ffffff` | Page background, header |
| `--bg-secondary` | `#f8f9fb` | App canvas below the header (sidebar + content) |
| `--bg-tertiary` | `#f1f3f6` | Subtle contrast panels |
| `--bg-elevated` | `#ffffff` | Menus, dialogs, popovers |
| `--bg-inverse` | `#15181e` | Tooltips, snackbars |
| `--bg-overlay` | `rgba(0,0,0,0.5)` | Modal scrim |
| `--surface-default` | `#ffffff` | Generic surface |
| `--surface-raised` | `#ffffff` | Raised surface |
| `--surface-sunken` | `#f1f3f6` | Inset wells, code-ish blocks |
| `--card-bg` | `#ffffff` | Card fill |
| `--sidebar-bg` | `#f8f9fb` | (Layout uses `--bg-secondary` in light mode) |
| `--header-bg` | `#ffffff` | Top bar fill |

### Text

| Token | Value | Use for |
|---|---|---|
| `--text-primary` | `#15181e` | Headings, body |
| `--text-secondary` | `#4d5560` | Supporting copy, labels |
| `--text-tertiary` | `#6c7280` | Hints, metadata, quiet table headers |
| `--text-disabled` | `#9ba1ac` | Disabled text |
| `--text-inverse` | `#ffffff` | Text on dark/inverse surfaces |
| `--text-link` | `#0f766e` | Links (teal-700 — AA on white) |
| `--text-link-hover` | `#115e59` | Link hover |

### Borders & focus

| Token | Value | Use for |
|---|---|---|
| `--border-default` | `#e4e7ec` | Hairline dividers, card borders |
| `--border-light` | `#f1f3f6` | Extra-quiet dividers (table rows) |
| `--border-strong` | `#d2d6dd` | Outlined buttons, unchecked controls |
| `--border-focus` | `#37d6c4` | Focused input outline |
| `--focus-ring` | `0 0 0 3px rgba(55,214,196,0.35)` | Box-shadow focus ring |

### Brand

| Token | Value | Use for |
|---|---|---|
| `--color-primary` | `#011627` (navy) | Filled buttons, primary emphasis, checked controls |
| `--color-primary-hover` | `#0d2947` | Hover on primary fills (lightens — base is near-black) |
| `--color-primary-bg` | `#eef2f6` | Soft navy tint (selected option bg) |
| `--color-primary-text` | `#0d2947` | Navy as text |
| `--color-accent` | `#16b9a8` (teal) | Highlights, active-tab underline, accent edges |
| `--color-accent-hover` | `#0d9488` | Accent hover |
| `--color-accent-bg` | `#effefb` | Soft teal tint (active nav highlight, selection) |
| `--color-accent-text` | `#0f766e` | Teal as text (AA on white — never use raw `#79ECDD` as text) |
| `--color-tertiary` | `#ad4780` (magenta) | Occasional accent |
| `--color-tertiary-bg` | `#fbf0f6` | Magenta tint |
| `--color-tertiary-text` | `#923a6b` | Magenta as text |

### Status

Every status has `--color-X` (icon/border grade), `--color-X-bg` (tint fill),
`--color-X-text` (AA text grade), and success/warning/error add `--color-X-border`.

| Family | color | bg | text | border |
|---|---|---|---|---|
| success | `#059669` | `#ecfdf5` | `#047857` | `#a7f3d0` |
| warning | `#c07f1c` | `#fefbf0` | `#714810` | `#fae5ad` |
| error | `#dc2626` | `#fef2f2` | `#b91c1c` | `#fecaca` |
| info | `#0d9488` | `#effefb` | `#0f766e` | — |

Status callout pattern (verified, AA-safe):

```html
<div class="callout success">…</div>
```
```scss
.callout.success {
  background: var(--color-success-bg);
  color: var(--color-success-text);
  border: 1px solid var(--color-success-border);
  border-radius: 8px;
}
```

### Interactive states, shadows, misc

| Token | Value |
|---|---|
| `--hover-overlay` | `rgba(0,0,0,0.04)` |
| `--active-overlay` | `rgba(0,0,0,0.08)` |
| `--shadow-xs` … `--shadow-xl` | Soft elevation ramp (avoid — this system prefers hairlines) |
| `--input-bg` / `--input-border` / `--input-border-focus` | `#ffffff` / `#d2d6dd` / `#37d6c4` |
| `--button-secondary-bg` / `--button-secondary-hover` | `#f1f3f6` / `#e4e7ec` |
| `--code-bg` / `--code-text` | `#f1f3f6` / `#b91c1c` (light-surface inline/block code) |
| `--code-panel-bg` / `--code-panel-text` / `--code-panel-border` | `#1e1e1e` / `#d4d4d4` / `rgba(255,255,255,0.1)` — theme-invariant dark surface for `.hop-code-panel` |
| `--hop-shimmer-tint` | (unset — defaults to `--color-accent-bg`) tint of the `.hop-shimmer` sweep |
| `--font-sans` | Inter stack |
| `--font-mono` | Roboto Mono stack |

### Layout & legacy aliases (`--hop-*`)

| Token | Value | Notes |
|---|---|---|
| `--hop-sidebar-width` | `250px` | Consumed by `HopMainLayoutComponent` |
| `--hop-toolbar-height` | `64px` | Legacy; the top bar is 56px |
| `--hop-space-xs/sm/md/lg/xl` | `4/8/16/24/32px` | Spacing shorthand |
| `--hop-primary` → `var(--color-primary)` | | compat alias |
| `--hop-accent` → `var(--color-accent)` | | compat alias |
| `--hop-warn` → `var(--color-error)` | | compat alias |
| `--hop-gradient` | `linear-gradient(135deg, #011627 0%, #0f766e 100%)` | Auth-page backdrop (navy→teal) |
| `--hop-success-bg/-text`, `--hop-error-bg/-text` | → status tokens | used by `.hop-status-message` |

---

## 3. Typography

- **UI face:** Inter (variable), `font-feature-settings: 'cv05' 1, 'ss01' 1`, letter-spacing `-0.011em`
- **Mono:** Roboto Mono (code, IDs, hashes)
- **Root font-size: 15px** → rem-based body text lands ≈14px (tool-UI scale)
- Headings: weight 600, letter-spacing `-0.02em`, colored `--text-primary`
- `<p>` defaults to `--text-secondary`; links default to `--text-link`

| Element | Size |
|---|---|
| h1 | 2.25rem | h2 | 1.875rem |
| h3 | 1.5rem | h4 | 1.25rem |
| h5 | 1.125rem | h6 / body | 1rem |

All of this is applied globally by the mixin — write plain `<h1>`/`<p>`/`<a>`
and it's already correct.

---

## 4. Geometry: spacing, radii, breakpoints

These are **SCSS variables** (compile-time, in `ui/src/lib/theme/_variables.scss`);
in component styles prefer plain px values from these scales or the
`--hop-space-*` CSS vars.

- **Spacing scale (8px base):** 4, 8, 12, 16, 20, 24, 28, 32, 40, 48, 64, 80, 96
- **Radii:** 4 (sm) · **8 (md — buttons, inputs, callouts)** · 12 (lg — cards) · 16 (xl) · 9999 (full — chips only)
- **Breakpoints:** 640 / **768 (mobile cutoff)** / 1024 / 1280 / 1536
- **Z-index:** dropdown 100 · sticky 200 · fixed 300 · modal 500 · popover 600 · tooltip 700 · toast 800

Geometry language: **8px radius rectangles, not pills** (chips are the only
fully-rounded element). **Hairline borders instead of drop shadows** — depth
comes from a surface step + 1px `--border-default` line. **Structural panels
are square-edged** — dividers between parts of the UI are straight lines.

---

## 5. What is already styled (do not restyle)

The mixin overrides all Material components. Defaults you get for free:

| Component | Styled as |
|---|---|
| Buttons | 8px radius, 36px tall, Inter medium. `mat-raised-button color="primary"` / `mat-flat-button color="primary"` = **navy fill, white label**. Outlined = hairline `--border-strong`, fills `--hover-overlay` on hover |
| Cards (`mat-card`) | `--card-bg` fill, 1px `--card-border`, 12px radius, **no shadow** |
| Form fields | Outlined only, 44px tall, 8px radius; 12px top margin (floating-label room), 10px between consecutive fields — **do not add your own field margins** |
| Tabs | **Left-aligned at natural width** (no stretch), teal underline on active, quiet inactive labels |
| Tables (`mat-table`) | Transparent bg, uppercase quiet headers (`--text-tertiary`), hairline row dividers, row hover overlay |
| Menus / selects / dialogs | `--bg-elevated` + hairline border; dialog 14px radius |
| Checkbox / slide-toggle / radio | Navy checked state, `--border-strong` unchecked |
| Chips | `--button-secondary-bg` fill, fully rounded |
| Icons | See section 6 |
| Sidenav / toolbar | Square corners (no M3 rounded drawer edges) |
| Scrollbars | 8px, tokenized thumb/track |
| Focus | 3px teal glow on `:focus-visible` — except Material text inputs/selects, whose outline + floating label are the focus affordance |
| Mobile ≤768px | Dialogs/menus capped to viewport, 44px touch targets, overflow guards |

If a Material widget looks wrong, fix the token or the theme override in
`ui/src/lib/theme/` — not with per-component CSS.

## 6. Icons

**Material Symbols Rounded, weight 300, FILL 0** (light, unfilled line style).
The theme re-points `<mat-icon>`'s default font at the Symbols face — use
ordinary ligature names and get line-style icons automatically:

```html
<mat-icon>settings</mat-icon>   <!-- renders outlined, weight 300 -->
```

Do not import the old Material Icons stylesheet. Do not set FILL 1. Icon boxes
are 24px (18px in dense contexts) — the theme handles metrics and clipping.

## 7. Utility classes & variants (emitted by the mixin)

| Class | Effect |
|---|---|
| `.text-primary/.text-secondary/.text-tertiary` | Text color tokens |
| `.text-success/.text-warning/.text-error` | Status text (AA grades) |
| `.bg-primary/.bg-secondary/.bg-surface` | Background tokens |
| `.hop-status-message` (+ `.success`/`.error`) | Inline status banner |
| `.hop-form-section` | Section spacing + heading treatment for forms |
| `.hop-form-actions` | Right-aligned action row (flex, gap) |
| `.loading-overlay` | Fixed full-viewport scrim with centered content |
| `.skip-link` | Accessibility skip-to-content link |
| `.hop-status-chip` (+ `-pending/-running/-completed/-failed`) | Lifecycle-state chips (see below) |
| `.hop-icon-badge` (+ color family) | Colored icon circle (see below) |
| `.hop-stat-card` / `.hop-stat-value` / `.hop-stat-label` | Dashboard metric card (see below) |
| `.hop-code-panel` | Dark VS Code-style code viewer, theme-invariant (see below) |
| `.hop-query-block` / `.hop-query-block-label` | Labeled monospace query display (see below) |
| `.hop-shimmer` | Animated running-state sweep (see below) |

### Card variants

```html
<!-- Normal card: hairline border all around -->
<mat-card>…</mat-card>

<!-- Accent card: 4px colored left edge (active/highlighted item in a stack) -->
<mat-card class="hop-card-accent">…</mat-card>

<!-- Accent with a different edge color -->
<mat-card class="hop-card-accent" style="--hop-card-accent-color: var(--color-warning)">…</mat-card>
```

### Status chips (job/entity lifecycle states)

Never override `mat-chip` colors per-component — use these. On a `mat-chip`
the state class alone is enough; on a plain `span` pair it with the base class
for the pill shape:

```html
<mat-chip class="hop-status-chip-pending">Pending</mat-chip>      <!-- amber -->
<mat-chip class="hop-status-chip-running">Running</mat-chip>      <!-- teal -->
<mat-chip class="hop-status-chip-completed">Completed</mat-chip>  <!-- green -->
<mat-chip class="hop-status-chip-failed">Failed</mat-chip>        <!-- red -->

<span class="hop-status-chip hop-status-chip-running">Running</span>
<span class="hop-status-chip">Neutral / unknown</span>  <!-- base alone = gray -->
```

### Stat / metric cards & icon badges

Dashboard summary metrics — icon in a colored circle, big value, quiet label.
`hop-icon-badge` families: default (navy), `accent`, `success`, `warning`,
`error`, `info`. `hop-stat-card` works on `mat-card` or a plain `div`.

```html
<mat-card class="hop-stat-card">
  <span class="hop-icon-badge success"><mat-icon>check_circle</mat-icon></span>
  <div>
    <span class="hop-stat-value">128</span>
    <span class="hop-stat-label">Completed</span>
  </div>
</mat-card>
```

`hop-icon-badge` also works standalone (list markers, dialog headers).

### Dark code panel

VS Code-style viewer for logs/diffs/test output. Stays dark in **both** themes
(driven by the theme-invariant `--code-panel-*` tokens). Inner `pre`/`code`
are reset automatically:

```html
<div class="hop-code-panel">
  <pre>FAILED tests/test_grouping.py — AssertionError …</pre>
</div>
```

Do not hard-code `#1e1e1e`-style panels per-component — use this class.

### Query block

Labeled monospace query display (JQL, SQL, search DSL) on the light sunken
surface:

```html
<div class="hop-query-block">
  <span class="hop-query-block-label">JQL</span>
  <code>project = REL AND fixVersion = "1.2.0" ORDER BY priority DESC</code>
</div>
```

### Shimmer (running-state rows)

Animated brand-teal sweep over an element's own background — for in-progress
job rows and loading placeholders. Respects `prefers-reduced-motion`. Tint is
adjustable via `--hop-shimmer-tint` (defaults to `--color-accent-bg`):

```html
<div class="job-row hop-shimmer">Publishing release notes…</div>
```

---

## 8. `@heretto/hop-ui` public API (complete)

Everything importable from `@heretto/hop-ui`:

### Components

| Class | Selector | Purpose | Inputs |
|---|---|---|---|
| `HopLoginComponent` | `hop-login` | Login + registration, SSO (Google/Microsoft), org selection | — |
| `HopForgotPasswordComponent` | `hop-forgot-password` | Request password-reset email | — |
| `HopResetPasswordComponent` | `hop-reset-password` | Token-based password reset | — |
| `HopSSOCallbackComponent` | `hop-sso-callback` | OAuth redirect completion | — |
| `HopAcceptInvitationComponent` | `hop-accept-invitation` | Accept org invitation (`/invite/:token`) | — |
| `HopMainLayoutComponent` | `hop-main-layout` | App shell: white top bar (brand left; profile + settings icon buttons right), sidebar below, router outlet | `appTitle: string`, `logoSrc?: string` (brand image, 36px tall, far left; with `appTitle` set the app name renders beside it after a thin divider — set `appTitle=""` for logo-only; without `logoSrc` the brand falls back to icon + name), `navItems: NavItem[]` |
| `HopAccountComponent` | `hop-account` | Profile editor (email, password, delete) | — |
| `HopAdminComponent` | `hop-admin` | Org admin: members + invitations tabs | — |
| `HopInviteDialogComponent` | `hop-invite-dialog` | Invite-member dialog (opened by HopAdmin) | via `MatDialog` |
| `HopConfirmDialogComponent` | `hop-confirm-dialog` | Reusable confirm dialog | `MatDialog` data: `HopConfirmDialogData` |
| `HopInviteSuccessDialogComponent` | — | Post-invite success dialog | `MatDialog` data: `HopInviteSuccessDialogData` |

All components are **standalone** (import directly, no NgModule).

### Types

```typescript
interface NavItem { label: string; icon: string; route: string; adminOnly?: boolean; superuserOnly?: boolean; }
interface HopConfirmDialogData { title: string; message: string; confirmText?: string; cancelText?: string; }
interface Organization { id: string; name: string; slug: string; settings?: any; created_at: string; updated_at?: string; member_count?: number; }
interface OrganizationMember { id: string; user_id: string; user_email: string; role: 'admin' | 'member'; joined_at: string; invited_by?: string; }
interface OrganizationInvitation { id: string; organization_id: string; organization_name: string; email: string; role: 'admin' | 'member'; token: string; invited_by_email: string; expires_at: string; created_at: string; }
interface AccountInfo { id: string; email: string; is_active: boolean; is_superuser: boolean; created_at: string; organization_role?: string; organization_id?: string; organization_name?: string; }
interface AccountUpdate { email?: string; current_password?: string; new_password?: string; }
interface UserOrganizationInfo { id: string; name: string; slug: string; role: string; }
interface LoginResponse { access_token: string; refresh_token: string; token_type: string; expires_at?: number; organizations?: UserOrganizationInfo[]; }
interface SSOProviders { google: boolean; microsoft: boolean; sso_only: boolean; single_org_mode: boolean; google_client_id?: string; }
```

### Services (root-provided, `inject()` them)

```typescript
HopAuthService {
  currentUser$: Observable<...>;
  login(email, password): Observable<LoginResponse>;
  register(email, password, organizationName?): Observable<any>;
  logout(): void;
  refreshToken(): Observable<LoginResponse>;
  isAuthenticated(): boolean;
  forgotPassword(email): Observable<{message}>;
  resetPassword(token, newPassword): Observable<{message}>;
  getSSOProviders(): Observable<SSOProviders>;
  updateTokens(response): void;
  navigateToDashboard(returnUrl?): void;
}

HopOrganizationService {
  currentOrganization$: Observable<Organization>;
  getCurrentOrganization(): Observable<Organization>;
  listUserOrganizations(): Observable<Organization[]>;
  createOrganization({name}): Observable<Organization>;
  updateOrganization({name?, settings?}): Observable<Organization>;
  switchOrganization(orgId): Observable<{access_token, refresh_token, token_type}>;
  listMembers(): Observable<OrganizationMember[]>;
  updateMemberRole(memberId, role): Observable<OrganizationMember>;
  removeMember(memberId): Observable<any>;
  createInvitation({email, role}): Observable<OrganizationInvitation>;
  listInvitations(): Observable<OrganizationInvitation[]>;
}

HopAccountService {
  accountInfo$: Observable<AccountInfo>;
  isAdmin$: Observable<boolean>;
  isSuperuser$: Observable<boolean>;
  getAccountInfo(): Observable<AccountInfo>;
  updateAccount(data: AccountUpdate): Observable<UpdateResponse>;
  deleteAccount(confirm?): Observable<{message}>;
  clearAccountInfo(): void;
  isAdmin(): boolean;
  getCurrentEmail(): string | null;
}
```

### Guards, interceptor, token, routes

| Export | Kind | Behavior |
|---|---|---|
| `hopAuthGuard` | `CanActivateFn` | Redirects unauthenticated users to `/login` |
| `hopAdminGuard` | `CanActivateFn` | Requires org-admin role |
| `hopSuperuserGuard` | `CanActivateFn` | Requires system superuser |
| `hopAuthInterceptor` | `HttpInterceptorFn` | Attaches Bearer token, auto-refreshes on 401 |
| `HOP_API_URL` | `InjectionToken<string>` | API base URL, defaults `/api/v1` — provide to override |
| `HOP_ROUTES` | `Routes` | Prebuilt: `login`, `forgot-password`, `reset-password`, `auth/sso/complete`, `invite/:token`, `account` (auth-guarded), `admin` (auth+admin-guarded) |

---

## 9. Canonical app skeleton (copy-paste starting point)

```typescript
// app.config.ts
import { ApplicationConfig } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideAnimations } from '@angular/platform-browser/animations';
import { hopAuthInterceptor } from '@heretto/hop-ui';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideRouter(routes),
    provideHttpClient(withInterceptors([hopAuthInterceptor])),
    provideAnimations(),
  ],
};
```

```typescript
// app.routes.ts
import { Routes } from '@angular/router';
import { hopAuthGuard, hopAdminGuard } from '@heretto/hop-ui';

export const routes: Routes = [
  { path: 'login', loadComponent: () => import('@heretto/hop-ui').then(m => m.HopLoginComponent) },
  { path: 'forgot-password', loadComponent: () => import('@heretto/hop-ui').then(m => m.HopForgotPasswordComponent) },
  { path: 'reset-password', loadComponent: () => import('@heretto/hop-ui').then(m => m.HopResetPasswordComponent) },
  { path: 'auth/sso/complete', loadComponent: () => import('@heretto/hop-ui').then(m => m.HopSSOCallbackComponent) },
  { path: 'invite/:token', loadComponent: () => import('@heretto/hop-ui').then(m => m.HopAcceptInvitationComponent) },
  {
    path: '',
    canActivate: [hopAuthGuard],
    loadComponent: () => import('./shell/shell.component').then(m => m.ShellComponent),
    children: [
      { path: 'dashboard', loadComponent: () => import('./dashboard/dashboard.component').then(m => m.DashboardComponent) },
      { path: 'account', loadComponent: () => import('@heretto/hop-ui').then(m => m.HopAccountComponent) },
      { path: 'admin', canActivate: [hopAdminGuard], loadComponent: () => import('@heretto/hop-ui').then(m => m.HopAdminComponent) },
      { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
    ],
  },
  { path: '**', redirectTo: '' },
];
```

```typescript
// shell/shell.component.ts — wraps the hop-ui layout with your nav
import { Component } from '@angular/core';
import { HopMainLayoutComponent, NavItem } from '@heretto/hop-ui';

@Component({
  selector: 'app-shell',
  imports: [HopMainLayoutComponent],
  // logoSrc is optional — omit it to show a hub icon + appTitle text instead.
  template: `<hop-main-layout appTitle="My App" logoSrc="assets/my-logo.png" [navItems]="navItems"></hop-main-layout>`,
})
export class ShellComponent {
  navItems: NavItem[] = [
    { label: 'Dashboard', route: '/dashboard', icon: 'dashboard' },
    // { label: 'Admin only', route: '/x', icon: 'shield', adminOnly: true },
  ];
}
```

The layout automatically appends Account / Administration / System Admin nav
items (role-gated) and renders the top-bar profile + settings menus — do not
re-add them to `navItems`.

Working example of all of the above: `demo/frontend/`. Live component
showcase: the demo's **Widget Library** page
(`demo/frontend/src/app/widgets/widgets.component.ts`).

---

## 10. Rules

**Do**
- Consume tokens: `color: var(--text-secondary)`, `background: var(--surface-sunken)`.
- Use plain Material components — they are already themed.
- Use `<mat-icon>ligature_name</mat-icon>` for icons.
- Use 8px-scale spacing and 8px radii for custom elements; hairline
  (`1px solid var(--border-default)`) for separation.
- Use `.hop-card-accent` for emphasized/selected cards.
- Put page content on `--bg-secondary`; put grouped content in cards.

**Don't**
- Hard-code hex colors, rgba grays, or `white`/`black` in component styles.
- Add `border`/`box-shadow` to `mat-card` (base border is themed; shorthand
  `border` in a component style will silently kill the accent-edge variant).
- Add top/bottom margins to `mat-form-field` — spacing is global.
- Use raw `#79ECDD` as text on light surfaces (fails WCAG AA — use
  `--color-accent-text`).
- Import the Material Icons font or use filled icons.
- Introduce pills (fully-rounded rectangles) for anything but chips.
- Restyle Material internals per-component; fix it in the token/theme layer.

### Extending tokens (new semantic color)

Add to **both** theme blocks in `ui/src/lib/theme/_tokens.scss`, then consume:

```scss
// :root, [data-theme="light"]
--status-review: #{$color-warning-600};
--status-review-bg: #{rgba($color-warning-500, 0.1)};

// [data-theme="dark"]
--status-review: #{$color-warning-400};
--status-review-bg: #{rgba($color-warning-500, 0.2)};
```

### Dark mode (future)

A complete `[data-theme="dark"]` token block ships **inert** — nothing sets
the attribute. Enabling dark mode later = a ThemeService that toggles
`document.documentElement.dataset.theme` + persists to localStorage. Write
token-consuming styles now and they will theme automatically then.

---

## 11. File map (for maintainers)

| File | Contents |
|---|---|
| `ui/src/lib/theme/_variables.scss` | Raw Sass ramps + scales (brand color ramps live here) |
| `ui/src/lib/theme/_tokens.scss` | Semantic CSS custom properties (light + inert dark) + `--hop-*` aliases |
| `ui/src/lib/theme/_base.scss` | Reset, typography, scrollbars, focus, utility classes |
| `ui/src/lib/theme/_material.scss` | `mat.theme()` M3 setup, `--mat-sys-*` bridge, Material overrides, icon font swap, mobile guardrails |
| `ui/src/lib/theme/_theme.scss` | `hop-core-theme()` entry mixin + hop utility classes + card variants |
| `ui/src/lib/theme/index.scss` | Public forward (`@use ... as hop`) |
| `ui/src/public-api.ts` | Library export barrel (section 8 mirrors it) |
