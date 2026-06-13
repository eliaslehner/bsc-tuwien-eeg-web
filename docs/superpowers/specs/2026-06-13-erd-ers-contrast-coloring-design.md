# ERD/ERS contrast coloring — design

- Date: 2026-06-13
- Status: approved (brainstorm) — pending spec review
- Area: frontend (`frontend/app`)

## Problem

In contrast mode the heatmap value is `ERD/ERS(A) − ERD/ERS(B)`, but it is rendered
with the **same** blue→grey→red ERD/ERS scale and the **same** legend as the
single-class heatmap. Two issues:

1. **Misleading legend.** A red region in contrast does not mean "synchronization
   (power increase)"; it means "class A is more ERS / less ERD than class B here".
   The static "ERS +" / "ERD −" legend invites misreading in figures.
2. **Conflated phenomena.** The diverging difference mixes two opposite effects: a
   region can take class A's side because A *desynchronizes* (activation) **or**
   because B *synchronizes* (idling). The colour alone cannot tell which.

## Goal

In contrast mode, colour the cortex by the two compared classes' **own colours**
and show exactly one phenomenon at a time (ERD **or** ERS), so a coloured region
unambiguously means "this class shows the stronger <phenomenon> here".

## Scope

- **Only contrast mode changes.** When contrast is OFF, the heatmap is unchanged:
  the blue→grey→red ERD–ERS diverging scale and its current legend stay exactly as
  today.
- Contrast requires exactly two selected classes (already enforced); `contrastOrder`
  gives `A = contrastOrder[0]`, `B = contrastOrder[1]`. Both classes always have a
  colour (from `eeg_data.json` → `dataset.classes[].color`).

## Behaviour (contrast mode ON, heatmap ON)

### ERD/ERS toggle
- A segmented control **`ERD | ERS`**, default **`ERD`**.
- Visible only while contrast mode is active; placed in `DatasetPanel` next to the
  contrast-order swap control.
- New state `contrastPhenomenon: 'erd' | 'ers'` in `page.js`, passed to both
  `DatasetPanel` (toggle UI) and `BrainViewer` (colouring + legend).

### Per-region colouring
For region R with the two contrasted classes A and B, using each class's
per-region averaged value at the current time (`vA`, `vB`):

- **ERD mode:** `eA = max(0, −vA)`, `eB = max(0, −vB)` (desync magnitude; 0 if that
  class is ERS/flat there).
- **ERS mode:** `eA = max(0, vA)`, `eB = max(0, vB)` (sync magnitude).
- `winner = A if eA ≥ eB else B`.
- `magnitude = |eA − eB|` — the **inter-class difference** (this is the contrast;
  decided over "winner's own magnitude").
- `colour = lerp(neutralGrey, winnerClassColour, clamp(magnitude / maxAbs, 0, 1))`,
  where `winnerClassColour` is the winner's colour from `dataset.classes`, and
  `maxAbs` is the maximum `|eA − eB|` over the epoch for the active phenomenon
  (stable normalisation, mirrors the existing `computeHeatmapMaxAbs`).
  `neutralGrey` is the heatmap's existing neutral grey.
- `if eA == eB == 0` (region is entirely the opposite phenomenon / flat) → grey.
- **ERD-threshold filter still applies:** if `magnitude < erdThreshold`, the region
  is grey (same noise-suppression behaviour as the current heatmap, now applied to
  the inter-class difference).
- Regions with no electrode mapping → grey (unchanged from today).

Consequence: a region where both classes desync equally stays grey (no contrast),
while regions that distinguish the classes light up in the dominant class's colour.
Left-vs-Right hand in ERD → right hemisphere in Left-Hand's colour, left hemisphere
in Right-Hand's colour (clean lateralisation, no ERD/ERS ambiguity).

### Legend
- The blue/red legend is **hidden** while contrast mode is active.
- A new **contrast legend** is shown instead: the active phenomenon label
  (`ERD`/`ERS`) plus the two class swatches with their names, e.g.
  `ERD — ▢ Left Hand · ▢ Right Hand`. A coloured region is then self-explanatory in
  a static figure.

### Tooltip
- In contrast mode the tooltip reads `region — WinningClass (PHENOMENON) NN%`, e.g.
  `L G_precentral — Left Hand (ERD) 18%` (magnitude, no sign).

## Components / files

- `app/page.js`: add `contrastPhenomenon` state (default `'erd'`); pass to
  `DatasetPanel` and `BrainViewer`. Reset/ignore when not in contrast mode.
- `app/components/DatasetPanel.jsx`: render the `ERD | ERS` segmented toggle inside
  the contrast-controls block, shown only when `contrastMode`.
- `app/components/BrainViewer.jsx`:
  - `computeRegionAveragesAtTime`: in contrast mode, bucket **each class's** value
    per region separately (return `{ regionId: { a, b } }`) instead of the
    precomputed `v1 − v2`. The midline **Mirror** logic still applies per class.
  - colour path: add a contrast-aware branch that implements the winner-by-difference
    colouring using class colours + `contrastPhenomenon`.
  - `computeHeatmapMaxAbs`: in contrast mode normalise over `|eA − eB|` for the
    active phenomenon.
  - legend JSX: render the contrast legend when `contrastMode`; hide the blue/red one.
  - tooltip + `heatmapValuesRef`: contrast-aware text (winning class + phenomenon).
  - needs `eegData.dataset.classes` (id → colour/label) and the existing
    `channel_regions` mapping.
- `app/globals.css`: styles for the `ERD | ERS` segmented toggle and the contrast
  legend swatches.

## Edge cases / notes

- **Mirror toggle** (midline electrodes) still applies: per-class bucketing mirrors
  midline electrodes into both L/R regions exactly as the current single-value path.
- **Colour-blindness:** only two colours are shown at once, but some class pairs
  (feet green vs right-hand yellow) are less distinct than blue/red. Accepted; out
  of scope to remap class colours here.
- **Non-contrast modes** are untouched by this work.

## Verification (in-browser)

- Contrast Left vs Right hand, **ERD**: right hemisphere ≈ Left-Hand colour, left
  hemisphere ≈ Right-Hand colour; both-active midline regions stay grey.
- Switch to **ERS**: colouring updates to the synchronisation contrast.
- Toggle the ERD/ERS control: brain + legend update live.
- Contrast legend shows the two class colours; blue/red legend hidden.
- Turn contrast OFF: blue/red ERD–ERS heatmap + original legend restored.
- No console errors.
