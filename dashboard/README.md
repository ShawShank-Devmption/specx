# SpecX evidence dashboard

```bash
# From the repository root (after generating experiment artefacts):
make report
# Missing inputs still publish an explicitly incomplete report and exit 2.

cd dashboard
npm ci
npm run build
npm test
npm run dev
```

Open `http://127.0.0.1:5173`. The app fetches `public/numbers.json`, copied by the reporter from `results/final/numbers.json`. No API key or sandbox connection is used by the dashboard. There is no hard-coded fallback dataset: absent/invalid JSON produces an error, and incomplete or test-double evidence produces a visible warning.

The four panels show readiness with 95% CI whiskers and paired comparisons, quarantine reasons, accepted/rejected revisions, and S6/S1/S2 metrics. Safety values retain their published field names because S1's detailed JSON nesting is not specified by its developer plan. Details include generation, verification and F2 convergence. The dark bronze Outfit theme supports narrow viewports, keyboard focus styles and reduced-motion preferences.

The visual direction matches the supplied SpecX reference: a full-height hero with a centered oversized Outfit headline, warm ivory text, gold pill-shaped links, amber and midnight-blue ambient gradients, and sparse decorative stars. The background is built with CSS and requires no external images. Hero links navigate to the existing evidence panels. The dark evidence panels continue the gold palette below the hero. Outfit is served locally from `public/fonts` under the included SIL Open Font License; no external font requests are needed. Unknown results remain explicitly marked as missing.

The report command also supports `--apps`, `--trials`, `--seed`, and `--dashboard-public` for isolated tests or alternative cohorts. Paths are repository-relative unless absolute. Partial/missing cohorts exit 2; malformed shared-schema artefacts exit 1 before new output is published. Only canonical condition JSONL files and held-out task IDs enter readiness; gate/training episodes are excluded.

Dependencies are locked in `package-lock.json`. Node 20.19+ or 22.12+ is required by Vite; use a supported active Node release. These instructions concern local development, not deployment.
