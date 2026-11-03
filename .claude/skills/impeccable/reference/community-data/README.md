# Community reference data (not part of impeccable's active reasoning)

Five CSVs imported 2026-09-26 from `creative-design/ui-ux-pro-max` on
aitmpl.com / github.com/davila7/claude-code-templates, merged here instead of
installed as a separate competing skill (impeccable already owns this
territory end to end).

- `colors.csv` — 96 rows, product-category → hex palette lookup.
- `typography.csv` — 57 rows, font-pairing name → Google Fonts family, import
  URL, and Tailwind config snippet.
- `styles.csv` — 58 rows, named visual styles (Glassmorphism, Brutalism,
  Neumorphism, …) with framework compatibility and accessibility notes.
- `ui-reasoning.csv` — 100 rows, product-category → recommended pattern +
  style + anti-patterns.
- `charts.csv` — 25 rows, data-shape → chart type + library recommendation.

## Read this before consulting any of the above

`colors.csv`, `styles.csv`, and `ui-reasoning.csv` are category → default
lookup tables. **This directly conflicts with impeccable's own calibration
principle** (see [new-work.md](../new-work.md): "if someone could guess your
aesthetic from the category alone... rework until neither answer is
obvious"). Do not use these three files to *choose* a palette or style for a
brief — that is precisely the shortcut impeccable exists to prevent. They may
still be useful as a fast sanity check on real, currently-shipping hex codes
and named styles when you already know the direction and just need
concrete values to start from.

`typography.csv` and `charts.csv` are lower-risk: they are mechanical
technical references (real Google Fonts names + working `@import`/Tailwind
syntax; which chart library suits which data shape) rather than aesthetic
defaults, so they're reasonable to consult directly — [typeset.md](../typeset.md)
links to `typography.csv` for concrete font-pairing syntax once a direction
is already chosen, never to pick the direction itself.

Source license: the upstream skill did not declare one explicitly; treat as
community-sourced reference data, not redistributable as a standalone
product.
