# Design reference

These images are the visual target. Phone screens are 390 × 844 CSS px, rendered at 2×. Implement the same look; you don't need pixel-perfect copies.

`private/` holds a screenshot of the real George app for personal reference only. It is gitignored: never commit it, never copy its logo or assets.

## What each image shows and where it is used

| Image | Shows | Build it as |
|---|---|---|
| 01-entdecken-start.png | Blue header band, card overlapping it, input with round send button, example prompts | `/chat` empty state |
| 02-entdecken-ergebnisse.png | "Das habe ich verstanden" filter chips with KI label, result list | `product_cards` block + filter chips |
| 03-produkt-kurzinfo.png | KID summary, risk scale 1–7, "Quelle: S. 1" badges, cost calculator | `/produkt/:id`, `risk_meter`, `cost_breakdown` |
| 04-depot-bewegung.png | Value chart with tappable event markers, AI explanation, source chips, attribution bars | `/depot`, `attribution` block |
| 05-depot-roentgen.png | Overlap Venn, amber AI warning, tabs for regions/sectors/top holdings | `exposure_bars`, `overlap_matrix` |
| 06-simulator.png | Percentile fan chart, levers as segmented buttons, three stat cards | `/simulator`, `fan_chart` |
| 07-profil-dialog.png | Chat-style profiling, contradiction warning, live profile card | persona profile view (optional) |
| 08-invest-coach.png | Lesson card, explanation modes, quiz | optional "learn" intent answer |
| 09-innehalten.png | Bottom sheet with three facts and three equal-weight options | `handoff` block style |
| 10-architektur.png | System architecture board | README diagram and the "So funktioniert's" section |
| 11-trace-panel.png | Desktop layout: phone left, "Unter der Haube" right, numbered pipeline steps with timings, JSON view | trace panel |
| 12-eval-tabelle.png | Evaluation table with runs and colour-coded scores | `/evals` |

## Tokens

```css
:root {
  --blue: #2463EB;        /* brand, header band, primary buttons */
  --blue-ink: #1A4FC4;    /* links, active tab text */
  --blue-soft: #E6EEFE;   /* active tab and quiet button background */
  --navy: #0F1E3D;        /* main text, dark buttons, code background */
  --ink-2: #33415E;       /* secondary text */
  --muted: #5A6784;       /* captions */
  --ground: #EDF0F5;      /* app background */
  --card: #FFFFFF;
  --line: #D9DFEA;
  --ai: #5A3FD6;          /* everything AI: KI labels, chips, AI bubbles */
  --ai-soft: #EEEAFE;
  --green: #0A7A3B;  --green-soft: #E3F5EA;   /* gains, passed checks */
  --red: #B42D23;    --red-soft: #FBE7E5;     /* losses, failed checks */
  --amber-ink: #8A5200; --amber-soft: #FFF3DC; /* warnings */
}
```

- **Type:** Onest 400/500/600/700/800 via `@fontsource/onest`. Scale 28 / 22 / 17 / 15 / 13 px. `font-variant-numeric: tabular-nums` for all figures. German number format (1.234,56 €).
- **Shape:** cards 20 px radius, buttons 14 px, chips fully rounded, segmented controls 12 px. Soft shadow `0 1px 2px rgba(15,30,61,.06), 0 8px 24px rgba(15,30,61,.06)`.
- **Layout:** blue header band ~120 px tall; the first card overlaps it by 40 px. 16 px page padding, 12 px gaps.
- **AI pattern:** anything AI-generated gets a purple "KI" label, purple-tinted surfaces and source chips ("BIB P07 · S. 2"). Deterministic results use neutral cards.
- **Motion:** chips pop in staggered by 60 ms; nothing else animates on load. Respect `prefers-reduced-motion`.
- **Accessibility:** 44 px minimum touch targets, visible focus ring (3 px blue), real `<button>` elements, contrast ≥ 4.5:1.
- **Footer on every AI surface:** "KI-generiert · Beispieldaten · keine Anlageberatung".
