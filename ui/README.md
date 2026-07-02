# @heretto/hop-ui — design system

The shared Angular UI library for hop-core apps. Beyond the auth/layout/admin
components, it ships a **design system**: a CSS-variable token layer plus Angular
Material (M3) overrides that give every hop-core app a consistent look and feel.

It is a *token + theme* layer, not a bespoke component library. Angular Material
stays the component substrate — the design system themes it globally so
consistency comes for free and custom interactions never have to fight it.

Requires **Angular 19 / Angular Material 19** (the theme uses the M3 `mat.theme()`
API and the `--mat-sys-*` system-token bridge).

## Using it

Two steps (see the root README for copy-paste snippets):

1. **Fonts** — add Inter, Roboto Mono, and Material Symbols Rounded to
   `index.html`. The theme re-points `<mat-icon>` at the Symbols face, so all
   icons render in the light, unfilled line style (same ligature names).
2. **Theme** — `@include hop.hop-core-theme();` once in your global `styles.scss`.

That single mixin emits everything: the semantic tokens, the Material M3 theme +
bridge, base/reset styles, and component overrides. Nothing renders until you
include it.

## The golden rule: consume tokens, don't invent them

Component styles should reference the semantic CSS custom properties rather than
hardcoding colors. This is what keeps apps consistent and theme-ready.

```scss
// ✗ — hardcoded, drifts from the system, won't follow the theme
.card { background: #ffffff; color: #333; border: 1px solid #e0e0e0; }

// ✓ — semantic tokens
.card { background: var(--card-bg); color: var(--text-primary); border: 1px solid var(--border-default); }
```

## Card variants

`mat-card` renders as a quiet hairline-bordered surface. Add `hop-card-accent`
for an emphasis card with a colored left edge (the active/highlighted item in a
stack). The edge defaults to the teal accent; override per instance:

```html
<mat-card class="hop-card-accent">…</mat-card>
<mat-card class="hop-card-accent" style="--hop-card-accent-color: var(--color-warning)">…</mat-card>
```

## Token vocabulary

Defined in `src/lib/theme/`:

- **`_variables.scss`** — raw Sass palette + scales (spacing, type, radii,
  shadows, z-index, breakpoints). The Heretto brand ramps live here.
- **`_tokens.scss`** — semantic CSS custom properties consumed by components.

Common tokens:

| Group | Tokens |
|---|---|
| Surfaces | `--bg-primary`, `--bg-secondary`, `--bg-elevated`, `--surface-default`, `--surface-sunken`, `--card-bg` |
| Text | `--text-primary`, `--text-secondary`, `--text-tertiary`, `--text-link` |
| Borders | `--border-default`, `--border-light`, `--border-strong`, `--border-focus` |
| Brand | `--color-primary` (navy), `--color-accent` (teal), `--color-tertiary` (magenta) |
| Semantic | `--color-success`, `--color-warning`, `--color-error`, `--color-info` (+ `-bg` / `-text` variants) |
| State | `--hover-overlay`, `--active-overlay`, `--focus-ring` |

## Heretto brand

| Role | Color | Usage |
|---|---|---|
| Primary | `#011627` navy | Dominant brand color — filled buttons, primary emphasis. Dark, so white labels pass WCAG AA. |
| Accent | `#79ECDD` teal | Highlights, focus rings, hover tints, links. Bright — **not** used as text on white (use the teal-700 `--text-link` for on-light text). |
| Tertiary | `#AD4780` magenta | Occasional accent. |
| Warning | `#F7D48E` gold | Warning states (dark shades carry AA text). |
| Base | `#FFFFFF` | Page background. |

To rebrand, edit the ramps in `_variables.scss` — everything downstream follows.

## Adding a new semantic token

Add it to **both** theme blocks in `_tokens.scss` so it themes correctly:

```scss
// in :root, [data-theme="light"]
--status-review: #{$color-warning-600};
--status-review-bg: #{rgba($color-warning-500, 0.1)};

// in [data-theme="dark"]
--status-review: #{$color-warning-400};
--status-review-bg: #{rgba($color-warning-500, 0.2)};
```

Then consume it: `background: var(--status-review-bg); color: var(--status-review);`

## Light / dark

Light theme is active. The `[data-theme="dark"]` token block is present but
**inert** — nothing sets the attribute yet. Enabling dark mode later is a
follow-up (wire a `ThemeService` that toggles `document.documentElement.dataset.theme`),
not a rewrite: the tokens are already in place.

## Building the library

```bash
# from ui/ (requires ng-packagr + Angular 19 available)
npm run build   # → dist/hop-ui
```
