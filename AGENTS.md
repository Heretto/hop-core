# Building on hop-core

For agents (and people) starting a new application on hop-core, or auditing one
that already exists.

**Starting fresh: work through "Start here" below, in order.** It is the whole
wiring job — dependencies, settings, migrations, frontend — and following it
avoids every failure catalogued later in this document.

**Something already broken: skip to the numbered sections.** Each is a **check**
you can run, the **why**, and the **fix**, and each comes from a real failure in
a real hop-core app. Prefer running the check to assuming — most of these fail
silently, which is why they earned a section.

---

## Start here — wiring a new application

### Step 0 — Resolve the current release

Everything else derives from this, so do it first.

**Do not copy a version out of any document, including this one.** Look it up:

```bash
TAG=$(gh api repos/Heretto/hop-core/releases/latest --jq .tag_name)

# or, with no gh and no auth — hop-core is public:
TAG=$(curl -s https://api.github.com/repos/Heretto/hop-core/releases/latest \
      | grep -m1 '"tag_name"' | sed 's/.*: *"\(.*\)".*/\1/')

echo "$TAG"          # e.g. v0.1.2
VERSION="${TAG#v}"   # e.g. 0.1.2
```

Both dependencies come from that one value:

```bash
# Python
hop-core @ git+https://github.com/Heretto/hop-core.git@${TAG}

# npm — the asset name is the tag without its leading v
"@heretto/hop-ui": "https://github.com/Heretto/hop-core/releases/download/${TAG}/heretto-hop-ui-${VERSION}.tgz"
```

That second URL is safe to construct rather than look up. The release workflow
refuses to publish unless `ui/package.json`, `ui/package-lock.json`,
`pyproject.toml` and `hop_core.__version__` all equal the tag without its `v`,
so the asset name always follows the tag.

Pin the tag. Do not track `main`, and never point either dependency at a path on
disk — see §1 for why that keeps happening and what it breaks.

### Step 1 — Backend

```bash
pip install "hop-core[doctor] @ git+https://github.com/Heretto/hop-core.git@${TAG}"
```

Subclass the settings, create the app, and register your routers:

```python
# settings.py
from functools import lru_cache
from hop_core.config import HopCoreSettings

class AppSettings(HopCoreSettings):
    my_setting: str = "default"
    redis_url: str = ""        # override to optional if you do not use Redis

@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
```

```python
# main.py
from hop_core.app_factory import create_hop_app
from settings import get_settings

app = create_hop_app(settings_factory=get_settings, extra_routers=[...])
```

Generate the settings that have no defaults — the app will not start without
them (§3), and `ENCRYPTION_KEY` cannot be rotated later without orphaning every
encrypted row:

```bash
for k in APP_SECRET_KEY JWT_SECRET_KEY ENCRYPTION_KEY; do
  echo "$k=$(openssl rand -hex 32)"
done >> .env
echo "DATABASE_URL=sqlite:///./data/app.db" >> .env
```

If you use Alembic, write `migrations/env.py` in this shape from the start.
Every line of it exists because its absence produces an error that looks like
something else (§6):

```python
import sys
from pathlib import Path
from sqlalchemy import Table

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so `import models` works from the CLI

from hop_core import db as hop_db
from hop_core.db import Base
import hop_core.models   # register hop-core's tables, or your foreign keys cannot resolve
import models            # register yours

OUR_TABLES = {                      # derive it; a hand-written list goes stale
    m.class_.__tablename__
    for m in Base.registry.mappers
    if m.class_.__module__ == models.__name__
} | {o.name for o in vars(models).values() if isinstance(o, Table)}

def include_object(obj, name, type_, reflected, compare_to):
    return name in OUR_TABLES if type_ == "table" else True

def engine():                       # the CLI has no app startup to init it
    try:
        return hop_db.get_engine()
    except RuntimeError:
        from settings import get_settings
        hop_db.init_engine(get_settings().database_url)
        return hop_db.get_engine()
```

Configure with `include_object=include_object`, `compare_type=True`, and
`render_as_batch=True` for SQLite.

### Step 2 — Frontend

Add the dependency from Step 0, then the design system, which is **one mixin**:

```scss
// src/styles.scss — the entire required global stylesheet
@use '@heretto/hop-ui/theme' as hop;

@include hop.hop-core-theme();
```

Load the fonts in `src/index.html` and put `class="mat-typography"` on `<body>` —
[`DESIGN-SYSTEM.md`](DESIGN-SYSTEM.md) §1 has the exact tags. The package does
not ship the fonts, and a missing Material Symbols renders every icon as its
ligature name (§2).

**If you will serve behind a Content-Security-Policy, set this now**, in
`angular.json` on the production configuration:

```jsonc
"optimization": { "styles": { "inlineCritical": false } }
```

Otherwise your stylesheet downloads with HTTP 200 and is never applied. It is
the least obvious failure in this document (§4).

For components, services, guards and tokens, use
[`DESIGN-SYSTEM.md`](DESIGN-SYSTEM.md) rather than reading `ui/src`.

### Step 3 — Prove it works

```bash
hop-doctor                    # audits everything above; exits 1 on failures
```

Then check the running stack, not just the build (§8):

```bash
curl -s localhost:PORT/api/health                 # your app defines this; hop-core does not
curl -s -o /dev/null -w '%{http_code}\n' "localhost:PORT/api/v1/YOUR_COLLECTION/"
```

`401` there is success: every application route requires authentication, and the
trailing slash is required (§5). Read the browser console before concluding
anything about missing styles or icons.

---

## Run the checks automatically

Installing hop-core provides `hop-doctor`, which audits a project against
sections 1–4 and 6 of this document:

```bash
hop-doctor              # human-readable report; exits 1 on failures
hop-doctor --json       # structured findings, for agents and CI
hop-doctor --strict     # also exit 1 on warnings
```

It reports `FAIL` only when the repository proves something is broken, `WARN`
when configuration could legitimately come from elsewhere (host environment,
ingress, a secret manager), and `SKIP` when a thing is absent or undeterminable.
It never prints secret values. The compose check needs PyYAML and skips itself
without it — `pip install "hop-core[doctor]"` enables it.

`hop-doctor` catches the mechanical mistakes. The judgement calls in sections 5,
7 and 8 still need reading.

> Note for maintainers of this repo: `demo/` consumes the UI library **from
> source** via a tsconfig alias, so nothing here exercises the published
> package. Packaging regressions therefore survive releases — the theme
> stylesheets were missing from `@heretto/hop-ui` for its entire first release
> without any test noticing. When changing packaging, verify against the built
> tarball, not the demo.

---

## 1. Dependencies: never reference hop-core by filesystem path

**Check**

```bash
grep -rn "file://\|file:\.\.\|hop-core/ui/dist" requirements.txt package.json 2>/dev/null
grep -rn "hop-core/ui/src" --include="*.scss" --include="*.ts" . 2>/dev/null
```

Both must return nothing.

**Why.** A path like `hop-core @ file:///Users/someone/hop-core` or
`"@heretto/hop-ui": "file:../../hop-core/ui/dist/..."` works only on the machine
that wrote it. It breaks on every other checkout, and it can *never* work inside
a Docker build, because the path lies outside the build context. This is the
single most common way a hop-core app becomes unbuildable, and it is usually
invisible until someone else clones the repo.

**Fix.** Consume both packages as versioned artifacts. Get the tag from
[Step 0](#step-0--resolve-the-current-release) rather than from the illustration
below — `v0.1.2` here shows the shape, and will be out of date the moment
another release lands.

```bash
# requirements.txt — pin to a release tag, not a branch
hop-core @ git+https://github.com/Heretto/hop-core.git@v0.1.2
```

```jsonc
// package.json — the packaged tarball attached to the release
"@heretto/hop-ui": "https://github.com/Heretto/hop-core/releases/download/v0.1.2/heretto-hop-ui-0.1.2.tgz"
```

Pin to a tag rather than `main` so builds are reproducible. The Python install
needs `git` and network access available in the build image.

**Two traps specific to the npm package:**

- **npm cannot install from a subdirectory of a git repo.** The neat
  `git+https://…@tag` form that works for pip does not work for `@heretto/hop-ui`,
  because the package lives in `ui/`. Use the release asset URL.
- **The auto-generated source archive is not installable.** Every GitHub release
  shows a `vX.Y.Z.tar.gz` that GitHub creates automatically. It is *not* an npm
  package: its root directory is `hop-core-X.Y.Z/` rather than `package/`, and it
  contains no build output. `npm install` against it fails with
  `ENOENT: Could not read package.json`. Use the `heretto-hop-ui-*.tgz` asset,
  which CI builds from the tagged source.

Asset names follow the tag: tag `vX.Y.Z` produces `heretto-hop-ui-X.Y.Z.tgz`.
The release workflow fails the build if `ui/package.json` and the tag disagree,
so the URL is always predictable.

---

## 2. The theme comes from the package; the icon font does not

**Check**

```bash
grep -n "@use" src/styles.scss        # expect '@heretto/hop-ui/theme'
grep -c "Material+Symbols" src/index.html   # expect 1, or a self-hosted @font-face
```

**Why.** The theme mixin is the entire design system — nothing renders without
it. Importing it through a relative path into this repo's `ui/src/` only resolves
when hop-core happens to sit at one exact location on disk.

Separately, the theme points `mat-icon` at `'Material Symbols Rounded'` but the
package **does not ship that font**. Every consuming app must load it, and must
allow its source in any Content-Security-Policy. If the font is missing, icons
silently render as their ligature *name* — a button shows the text
`play_arrow` instead of a play glyph.

**Fix.**

```scss
// src/styles.scss — requires @heretto/hop-ui >= 0.1.1
@use '@heretto/hop-ui/theme' as hop;

@include hop.hop-core-theme();
```

This resolves from `node_modules` with no `angular.json` or `includePaths`
changes. Load the font per §2 of [`DESIGN-SYSTEM.md`](DESIGN-SYSTEM.md), and if
your deployment is offline, air-gapped, or behind restrictive egress, self-host
it instead of relying on Google Fonts at runtime.

---

## 3. Required settings have no defaults

**Check**

```bash
python -c "from settings import get_settings; get_settings()"
```

A missing value raises a Pydantic validation error naming the field.

**Why.** `HopCoreSettings` declares these with **no default**, so the app cannot
start without them:

| Setting | Notes |
|---|---|
| `APP_SECRET_KEY` | |
| `JWT_SECRET_KEY` | distinct value from the above |
| `ENCRYPTION_KEY` | minimum 16 characters |
| `DATABASE_URL` | SQLAlchemy URL |
| `REDIS_URL` | required by `HopCoreSettings`; override it to optional in your subclass if you do not use Redis |

**`ENCRYPTION_KEY` is not rotatable.** It derives the Fernet key that encrypts
stored credentials. Change or lose it and every existing encrypted row becomes
unreadable. Back it up somewhere recoverable, keep it out of version control,
and never let a setup script regenerate one that already exists.

**Fix.** Generate secrets per environment (`openssl rand -hex 32`) and fail loudly
when they are absent rather than defaulting. In Docker Compose, guard them so the
failure happens at compose time with a readable message:

```yaml
environment:
  - APP_SECRET_KEY=${APP_SECRET_KEY:?not set — see .env.example}
```

Beware of having **two** `.env` files — one for local runs (read relative to the
backend's working directory) and one at the repo root for Compose. Document which
is which, or they drift.

---

## 4. Angular production builds vs. a strict CSP — the silent one

**Check** — after a production build, inspect the emitted HTML:

```bash
grep -o 'onload="[^"]*"' dist/*/index.html
grep -o 'media="print"' dist/*/index.html
```

If either matches **and** your CSP lacks `'unsafe-inline'` for scripts, your
stylesheet is not being applied.

**Why.** Angular's production default `optimization.styles.inlineCritical`
inlines above-the-fold CSS into a `<style>` block and loads the real stylesheet
inert:

```html
<link rel="stylesheet" href="styles-*.css" media="print" onload="this.media='all'">
```

`media="print"` means it does not apply until that inline `onload` handler flips
it. A CSP of `default-src 'self'` with no `script-src` blocks inline event
handlers, so the handler never runs and **the stylesheet never activates**. It
downloads with HTTP 200 and is silently ignored.

Only the inlined critical subset applies. That subset does not include the
`mat-icon` font-family rule, so the most visible symptom is icons rendering as
ligature text — which sends you hunting for a font problem that does not exist.
Material and `hop-*` component styles are also quietly wrong.

**Fix** — in `angular.json`, on the production configuration:

```jsonc
"optimization": {
  "scripts": true,
  "fonts": true,
  "styles": { "minify": true, "inlineCritical": false }
}
```

Do **not** instead add `'unsafe-inline'` to `script-src`. That trades a real XSS
protection for a rendering bug.

---

## 5. API surface conventions

**Check**

```bash
curl -s -o /dev/null -w "%{http_code}\n" "localhost:PORT/api/v1/YOUR_COLLECTION/"   # 401 when unauthenticated
curl -s localhost:PORT/openapi.json | python -c "import json,sys; print(*sorted(json.load(sys.stdin)['paths']),sep='\n')"
```

**Why.** Three things surprise people:

- Routes live under **`api_prefix`**, default `/api/v1` — not `/api`.
- **Collection routes require a trailing slash.** `/api/v1/things/` is correct;
  `/api/v1/things` returns 404. This looks exactly like a missing route.
- **Every application route requires authentication.** Unauthenticated requests
  get `401 {"detail":"Not authenticated"}`, which is correct behaviour, not a
  misconfiguration. Any unauthenticated health endpoint must be defined outside
  the prefix by your app; hop-core does not provide one.

**Fix.** Read the live surface from `/openapi.json`, or browse `/docs`. Generated
docs cannot go stale; a hand-maintained endpoint list in a README always does.

---

## 6. Migrations see hop-core's tables

**Check**

```bash
grep -n "include_object\|OUR_TABLES\|target_metadata" migrations/env.py
```

**Why.** Your models and hop-core's share one declarative `Base`, so
`target_metadata` covers `users`, `organizations`, `organization_members`,
`organization_invitations` and `credentials` as well as your own. Unfiltered,
`alembic revision --autogenerate` writes migrations against hop-core's schema —
measured on a real app, thirteen spurious `modify_type` operations, because
hop-core's UUID columns reflect out of SQLite as `NUMERIC`. Those migrations
rewrite tables your app does not own.

The usual fix is an `include_object` filter naming your own tables, which
introduces its own trap: **the filter has to be updated when you add a table.**
A table missing from the list is excluded from the comparison altogether. It is
not dropped — it becomes invisible, so changes to it never reach a migration and
the schema drifts unnoticed. That is quieter than a bad migration, and worse for
being quiet.

Three further things make alembic unusable from the command line until fixed,
all of which look like unrelated errors:

- Nothing puts your backend directory on `sys.path`. Uvicorn supplies it through
  the working directory; the CLI does not, so `import models` in `env.py` fails
  with `ModuleNotFoundError`.
- hop-core initialises its engine during application startup, which the CLI has
  none of, so `get_engine()` raises `Database engine not initialized`.
- If you do not `import hop_core.models` in `env.py`, hop-core's tables are absent
  from the metadata your foreign keys point at, and autogenerate dies on
  `NoReferencedTableError`.

**Fix.** Derive the filter from your models module rather than hand-listing it,
so a new table cannot be forgotten. Insert the backend directory on `sys.path`
from `env.py`'s own `__file__`, initialise hop-core's engine when nothing else
has, and import `hop_core.models` so foreign keys resolve. Use
`render_as_batch=True` for SQLite, which cannot `ALTER TABLE` in place. Note that
`alembic revision` also needs a `script.py.mako` template, so a project without
one writes revisions by hand regardless.

---

## 7. Runtime constraints

- **Python 3.11+.**
- **Single backend replica** if you schedule work with an in-process scheduler
  such as APScheduler. There is no distributed lock, so every replica fires every
  job. Scale vertically, or move to a shared job store first.
- **SQLite is stateful.** On Kubernetes that means a `StatefulSet` with a
  `PersistentVolumeClaim`, not a rolling `Deployment`.

---

## 8. Verify the deployment, not the build

A green build is not a working app. These checks catch the failures that look
like success:

```bash
# The container is running the code you just wrote — compose does NOT rebuild
# on source change, and a stale build context can report COPY as CACHED even
# when files changed.
docker compose exec SERVICE grep -n "a string you just added" /app/main.py
docker compose build --no-cache SERVICE     # when the above disagrees

# The stylesheet is actually applied (see §4)
curl -s localhost:PORT/ | grep -o 'media="print"'

# Health reports the truth. Probe the database with text("SELECT 1"), not a raw
# string — SQLAlchemy 2.0 rejects the latter, and a bare `except` turns that
# into a permanent, unexplained "degraded".
curl -s localhost:PORT/api/health
```

Read the browser console before concluding anything about missing styles, fonts,
or icons. A CSP violation there names the blocked resource directly and will save
you from diagnosing the wrong layer entirely.
