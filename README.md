# panelsd.cc

Static site for Panels DCC. Source pages live in `src/pages` as **EJS** templates; shared chrome is in `src/templates/partials`. Run the build to emit HTML under **`dist/`** (copy this folder to your host or point GitHub Pages at it).

## Build & Publish

```bash
npm install
npm run build
```

`npm run build` now does both:
- builds static output into `dist/`
- pushes your current working tree to the source branch (`origin/source`)
- publishes `dist/` to the `gh-pages` branch

For local-only rebuilds (no git push), use:

```bash
npm run build:local
```

Build output includes HTML plus `style.css`, `images/`, `videos/` (if present), `CNAME`, and `install.sh`.

## Edit

- **Content:** `src/pages/**/*.ejs`
- **Nav / head:** `src/templates/partials/*.ejs`
- **Styles:** `style.css` (repo root; copied into `dist/` on build)

## URLs

- Getting started: `/getting-started/installation.html` (steps 1–5: installation → Wi‑Fi → Connect → first train → account)
- Manual hub: `/manual/index.html`
- Configuration: `/configuration/index.html`
- Control (manual chapter): `/control/index.html`
- System admin: `/system-admin/index.html`
