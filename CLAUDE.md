# hop-core

Platform library for building multi-tenant AI-powered apps: a Python/FastAPI
backend package (`src/hop_core/`) + an Angular 19 UI library
(`ui/` → `@heretto/hop-ui`) + a runnable example app (`demo/`).

## Read this first when integrating a consuming app

**[`AGENTS.md`](AGENTS.md)** is the integration checklist for apps built on
hop-core: packaging, required settings, the icon font, the Angular/CSP
interaction that silently disables the stylesheet, migrations against the shared
`Base`, and how to verify a deployment rather than trust a green build. Every
item came from a real failure. Keep it updated when integration requirements
change — and note that `demo/` consumes the library from source, so it does not
exercise the published package.

## Read this first when doing UI work

**[`DESIGN-SYSTEM.md`](DESIGN-SYSTEM.md)** is the complete, self-contained
design-system reference: every token with its value, all Material overrides,
the full `@heretto/hop-ui` component/service/guard API, a copy-paste app
skeleton, and the do/don't rules. **Do not scan `ui/src/` to discover
components or tokens — the reference has them all.** Keep it updated when you
change the theme or public API.

Non-negotiables (details in the reference):
- Consume CSS variables (`var(--text-secondary)`) — never hard-code colors.
- Material components are pre-themed by the `hop-core-theme()` mixin — don't
  restyle them per-component; fix the token/theme layer instead.
- Icons are Material Symbols Rounded ligatures via plain `<mat-icon>`.
- No margins on `mat-form-field`, no borders/shadows on `mat-card` — global.

## Commands

```bash
# Backend tests
make test                    # pytest suite (from repo root)

# Demo app (backend :8000 + frontend :4200, auto-detects free ports)
cd demo && make setup && make start

# Frontend build check
cd demo/frontend && npm run build

# UI library package build (ng-packagr → ui/dist/hop-ui)
cd ui && npm run build
```

## Layout notes

- `ui/` resolves Angular via a local `node_modules` symlink →
  `../demo/frontend/node_modules` (gitignored; recreate after fresh clone:
  `ln -s ../demo/frontend/node_modules ui/node_modules`).
- `ui/package-lock.json` is committed so CI builds the library from pinned tool
  versions — releases are gated on a CI job, and an unpinned install lets an
  unrelated ng-packagr or TypeScript publish block a release. CI uses `npm ci`.
  Locally, prefer the symlink above: `npm ci` inside `ui/` deletes
  `node_modules`, which replaces that symlink with a full duplicate install.
- The demo consumes the library from source via a tsconfig paths alias
  (`@heretto/hop-ui` → `../../ui/src/public-api`), so demo builds compile the
  library — building the demo is the fastest full check.
- Backend integration point: `hop_core.app_factory.create_hop_app()`;
  settings subclass `HopCoreSettings`. See `demo/backend/main.py`.
