# ERD/ERS Contrast Coloring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In contrast mode, color the cortex by the two compared classes' own colors with an `ERD | ERS` toggle (default ERD), shaded by the inter-class difference; leave the non-contrast heatmap unchanged.

**Architecture:** Extract the contrast color math into a pure, node-testable module (`lib/contrastColor.mjs`). `computeRegionAveragesAtTime` returns per-class `{a,b}` values per region in contrast mode (instead of the precomputed `v1−v2`). `computeHeatmapColors` gets a contrast branch that uses the pure module + the active phenomenon + the two class colors. A new `contrastPhenomenon` state flows page → DatasetPanel (toggle) + BrainViewer (color/legend/tooltip).

**Tech Stack:** Next.js 16 (App Router, Turbopack), React 19, Three.js 0.183, vanilla CSS. No JS test framework — pure logic is tested with a `node` assertion script; integration is verified in-browser via `playwright-cli` (same pattern used for the Mirror feature).

**Spec:** `docs/superpowers/specs/2026-06-13-erd-ers-contrast-coloring-design.md`

---

## File structure

- **Create** `frontend/app/lib/contrastColor.mjs` — pure color helpers (ESM, node-testable). Responsibility: phenomenon magnitude, winner+difference, hex→rgb, final RGB.
- **Create** `frontend/app/lib/contrastColor.test.mjs` — node assertions for the above.
- **Modify** `frontend/app/page.js` — `contrastPhenomenon` state; pass to DatasetPanel + BrainViewer.
- **Modify** `frontend/app/components/DatasetPanel.jsx` — `ERD | ERS` segmented toggle in the contrast block.
- **Modify** `frontend/app/components/BrainViewer.jsx` — per-class aggregation, contrast color branch, maxAbs, legend, tooltip, new props.
- **Modify** `frontend/app/globals.css` — toggle + contrast-legend styles.

---

### Task 1: Pure contrast-color module (+ tests)

**Files:**
- Create: `frontend/app/lib/contrastColor.mjs`
- Test: `frontend/app/lib/contrastColor.test.mjs`

- [ ] **Step 1: Write the failing test**

Create `frontend/app/lib/contrastColor.test.mjs`:

```js
// Run: node app/lib/contrastColor.test.mjs   (exit 0 = all pass)
import assert from 'node:assert/strict';
import {
    phenomenonMag, contrastWinner, hexToRgb01, contrastColorRGB, CONTRAST_NEUTRAL,
} from './contrastColor.mjs';

// phenomenonMag: ERD reads desync magnitude (from negative %), ERS reads sync (positive %)
assert.equal(phenomenonMag(-30, 'erd'), 30);
assert.equal(phenomenonMag(+10, 'erd'), 0);
assert.equal(phenomenonMag(+10, 'ers'), 10);
assert.equal(phenomenonMag(-30, 'ers'), 0);
assert.equal(phenomenonMag(null, 'erd'), 0);

// contrastWinner: which class shows the stronger phenomenon, and by how much
let w = contrastWinner({ a: -30, b: -10 }, 'erd');
assert.equal(w.winner, 'a'); assert.equal(w.magnitude, 20);
w = contrastWinner({ a: -5, b: -25 }, 'erd');
assert.equal(w.winner, 'b'); assert.equal(w.magnitude, 20);
assert.equal(contrastWinner({ a: -10, b: -10 }, 'erd').magnitude, 0);

// hexToRgb01
assert.deepEqual(hexToRgb01('#FF0000'), [1, 0, 0]);
assert.deepEqual(hexToRgb01('#000000'), [0, 0, 0]);

// contrastColorRGB
const A = [1, 0, 1], B = [0, 1, 0];
// winner A at full magnitude -> A's color
let rgb = contrastColorRGB({ ab: { a: -40, b: 0 }, phenomenon: 'erd', colorA: A, colorB: B, maxAbs: 40 });
assert.deepEqual(rgb.map((x) => Math.round(x * 100) / 100), [1, 0, 1]);
// equal desync -> grey (no contrast)
rgb = contrastColorRGB({ ab: { a: -20, b: -20 }, phenomenon: 'erd', colorA: A, colorB: B, maxAbs: 40 });
assert.deepEqual(rgb, CONTRAST_NEUTRAL);
// below threshold -> grey
rgb = contrastColorRGB({ ab: { a: -12, b: -10 }, phenomenon: 'erd', colorA: A, colorB: B, maxAbs: 40, threshold: 5 });
assert.deepEqual(rgb, CONTRAST_NEUTRAL);
// ERS mode picks the positive side
rgb = contrastColorRGB({ ab: { a: 0, b: +40 }, phenomenon: 'ers', colorA: A, colorB: B, maxAbs: 40 });
assert.deepEqual(rgb.map((x) => Math.round(x * 100) / 100), [0, 1, 0]);

console.log('contrastColor: all tests passed');
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && node app/lib/contrastColor.test.mjs`
Expected: FAIL — `Cannot find module '.../contrastColor.mjs'`.

- [ ] **Step 3: Write the module**

Create `frontend/app/lib/contrastColor.mjs`:

```js
// Pure helpers for contrast-mode cortex colouring (class-coloured, per-phenomenon).
// .mjs so the logic is node-testable without a test runner; imported by BrainViewer.jsx.

// Grey shown where there is no inter-class contrast (matches the heatmap's
// below-threshold neutral).
export const CONTRAST_NEUTRAL = [0.2, 0.2, 0.2];

// Magnitude of the chosen phenomenon for one class's ERD/ERS value (%).
// ERD (desynchronisation) lives in the negative values; ERS in the positive.
export function phenomenonMag(v, phenomenon) {
    if (v == null) return 0;
    return phenomenon === 'ers' ? Math.max(0, v) : Math.max(0, -v);
}

// For a region's two class values {a, b}, which class shows the stronger
// phenomenon and by how much (the inter-class difference).
export function contrastWinner(ab, phenomenon) {
    const eA = phenomenonMag(ab?.a, phenomenon);
    const eB = phenomenonMag(ab?.b, phenomenon);
    return { magnitude: Math.abs(eA - eB), winner: eA >= eB ? 'a' : 'b', eA, eB };
}

// '#RRGGBB' -> [r, g, b] in 0..1.
export function hexToRgb01(hex) {
    const h = hex.replace('#', '');
    return [
        parseInt(h.slice(0, 2), 16) / 255,
        parseInt(h.slice(2, 4), 16) / 255,
        parseInt(h.slice(4, 6), 16) / 255,
    ];
}

// Final RGB (0..1) for a region in contrast mode.
//   ab            : {a, b} per-class ERD/ERS values
//   phenomenon    : 'erd' | 'ers'
//   colorA/colorB : [r,g,b] 0..1 class colours (a = contrastOrder[0])
//   maxAbs        : normaliser (max |eA-eB| over the epoch)
//   threshold     : ERD-threshold noise filter (%)
export function contrastColorRGB({ ab, phenomenon, colorA, colorB, maxAbs, threshold = 0 }) {
    const { magnitude, winner } = contrastWinner(ab, phenomenon);
    if (magnitude === 0 || magnitude < (threshold || 0)) return CONTRAST_NEUTRAL;
    const t = Math.max(0, Math.min(1, magnitude / (maxAbs || 1)));
    const c = winner === 'a' ? colorA : colorB;
    const [gr, gg, gb] = CONTRAST_NEUTRAL;
    return [gr + (c[0] - gr) * t, gg + (c[1] - gg) * t, gb + (c[2] - gb) * t];
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && node app/lib/contrastColor.test.mjs`
Expected: PASS — prints `contrastColor: all tests passed`, exit 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/lib/contrastColor.mjs frontend/app/lib/contrastColor.test.mjs
git commit -m "feat(contrast): pure class-color contrast helpers + tests"
```

---

### Task 2: ERD/ERS toggle state + control

**Files:**
- Modify: `frontend/app/page.js`
- Modify: `frontend/app/components/DatasetPanel.jsx`
- Modify: `frontend/app/globals.css`

- [ ] **Step 1: Add state in `page.js`**

After the `const [contrastOrder, setContrastOrder] = useState([null, null]);` line, add:

```js
    const [contrastPhenomenon, setContrastPhenomenon] = useState('erd'); // 'erd' | 'ers'
```

- [ ] **Step 2: Pass to DatasetPanel**

In the `<DatasetPanel ... />` props (where `contrastOrder`/`setContrastOrder` are passed), add:

```js
                    contrastPhenomenon={contrastPhenomenon}
                    setContrastPhenomenon={setContrastPhenomenon}
```

- [ ] **Step 3: Pass to BrainViewer**

In the `<BrainViewer ... />` props (after `contrastOrder={contrastOrder}`), add:

```js
                    contrastPhenomenon={contrastPhenomenon}
```

- [ ] **Step 4: Accept props + render the toggle in `DatasetPanel.jsx`**

Add `contrastPhenomenon, setContrastPhenomenon` to the destructured props (next to `contrastOrder, setContrastOrder`).

Then, immediately AFTER the closing `)}` of the `{contrastMode && contrastOrder[0] && contrastOrder[1] && ( ... )}` block (the contrast-order div), insert:

```jsx
                {contrastMode && (
                    <div className="erd-ers-toggle" role="group" aria-label="Contrast phenomenon">
                        <button
                            className={contrastPhenomenon === 'erd' ? 'active' : ''}
                            onClick={() => setContrastPhenomenon('erd')}
                        >ERD</button>
                        <button
                            className={contrastPhenomenon === 'ers' ? 'active' : ''}
                            onClick={() => setContrastPhenomenon('ers')}
                        >ERS</button>
                    </div>
                )}
```

- [ ] **Step 5: Add CSS**

Append to `frontend/app/globals.css`:

```css
/* === ERD/ERS contrast toggle === */
.erd-ers-toggle {
    display: flex;
    gap: 0;
    margin-top: 0.5rem;
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    overflow: hidden;
    width: fit-content;
}
.erd-ers-toggle button {
    background: transparent;
    border: none;
    color: #888;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    padding: 0.3rem 0.8rem;
    cursor: pointer;
    transition: all 0.15s;
}
.erd-ers-toggle button + button { border-left: 1px solid #2a2a2a; }
.erd-ers-toggle button.active { background: rgba(110, 231, 183, 0.12); color: #6ee7b7; }
```

- [ ] **Step 6: Verify it renders (no behaviour yet)**

Run: `cd frontend && PORT=3137 npm run dev` (background). Open the app, select exactly 2 classes, turn Contrast Mode ON. Confirm an `ERD | ERS` toggle appears under the contrast-order row with ERD highlighted; clicking ERS highlights it. No console errors. Stop the dev server.

- [ ] **Step 7: Commit**

```bash
git add frontend/app/page.js frontend/app/components/DatasetPanel.jsx frontend/app/globals.css
git commit -m "feat(contrast): ERD/ERS toggle control (state + UI)"
```

---

### Task 3: Per-class aggregation + contrast color rendering

**Files:**
- Modify: `frontend/app/components/BrainViewer.jsx`

- [ ] **Step 1: Import the pure module**

Change the eeg import line (top of file) to add the contrast import below it:

```js
import { activeChannelsFor } from '../lib/eeg';
import { contrastWinner, contrastColorRGB, hexToRgb01 } from '../lib/contrastColor.mjs';
```

- [ ] **Step 2: Replace `computeRegionAveragesAtTime` with the per-class-aware version**

Replace the whole function body with:

```js
function computeRegionAveragesAtTime(
    eegData, selectedClasses, selectedBand, timeIndex, contrastMode, contrastOrder, channelMode,
    mirror = null,
) {
    const bandData = eegData?.erd_ers?.[selectedBand];
    if (!bandData) return null;

    const channels = eegData.dataset.channels;
    const channelRegions = eegData.channel_regions;
    const activeClasses = [...selectedClasses].filter((c) => bandData[c]);
    if (activeClasses.length === 0) return null;

    const activeChannelSet = new Set(activeChannelsFor(channelMode || 'all', channels));
    const isContrast = contrastMode && activeClasses.length === 2;

    // Bucket a per-channel value map into a per-region mean, mirroring midline
    // electrodes into both hemispheres when the Mirror toggle is on.
    const bucketize = (chValues) => {
        const buckets = {};
        const push = (rid, value) => {
            if (rid == null) return;
            (buckets[rid] ||= []).push(value);
        };
        for (const [ch, value] of Object.entries(chValues)) {
            const region = channelRegions?.[ch];
            if (!region) continue;
            const rid = region.region_id;
            push(rid, value);
            if (mirror?.enabled && mirror.midline?.has(ch)) {
                const mid = mirror.map?.[rid];
                if (mid != null && mid !== rid) push(mid, value);
            }
        }
        const avg = {};
        for (const [rid, vals] of Object.entries(buckets)) {
            avg[rid] = vals.reduce((a, b) => a + b, 0) / vals.length;
        }
        return avg;
    };

    if (isContrast) {
        const c1 = contrastOrder?.[0] || activeClasses[0];
        const c2 = contrastOrder?.[1] || activeClasses[1];
        const chA = {};
        const chB = {};
        for (let i = 0; i < channels.length; i++) {
            if (!activeChannelSet.has(channels[i])) continue;
            chA[channels[i]] = bandData[c1]?.[i]?.[timeIndex] ?? 0;
            chB[channels[i]] = bandData[c2]?.[i]?.[timeIndex] ?? 0;
        }
        const avgA = bucketize(chA);
        const avgB = bucketize(chB);
        const out = {};
        for (const rid of new Set([...Object.keys(avgA), ...Object.keys(avgB)])) {
            out[rid] = { a: avgA[rid] ?? 0, b: avgB[rid] ?? 0 };
        }
        return out; // { rid: {a, b} }
    }

    // Non-contrast: average over the selected classes.
    const chValues = {};
    for (let i = 0; i < channels.length; i++) {
        if (!activeChannelSet.has(channels[i])) continue;
        let sum = 0;
        let count = 0;
        for (const cls of activeClasses) {
            const cd = bandData[cls];
            if (cd?.[i]) {
                sum += cd[i][timeIndex] ?? 0;
                count++;
            }
        }
        if (count > 0) chValues[channels[i]] = sum / count;
    }
    return bucketize(chValues); // { rid: number }
}
```

- [ ] **Step 3: Make `computeHeatmapMaxAbs` contrast-aware**

Replace its signature and the inner `maxAbs` update. New version:

```js
function computeHeatmapMaxAbs(
    eegData, selectedClasses, selectedBand, contrastMode, contrastOrder, channelMode,
    mirror, contrastPhenomenon,
) {
    const bandData = eegData?.erd_ers?.[selectedBand];
    const times = bandData?.times || [];
    if (!bandData || times.length === 0) return 1;

    const activeClasses = [...selectedClasses].filter((c) => bandData[c]);
    const isContrast = contrastMode && activeClasses.length === 2;

    let maxAbs = 1;
    for (let timeIndex = 0; timeIndex < times.length; timeIndex++) {
        const regionAvg = computeRegionAveragesAtTime(
            eegData, selectedClasses, selectedBand, timeIndex,
            contrastMode, contrastOrder, channelMode, mirror,
        );
        if (!regionAvg) continue;
        for (const value of Object.values(regionAvg)) {
            maxAbs = isContrast
                ? Math.max(maxAbs, contrastWinner(value, contrastPhenomenon).magnitude)
                : Math.max(maxAbs, Math.abs(value));
        }
    }
    return maxAbs;
}
```

- [ ] **Step 4: Add the contrast branch to `computeHeatmapColors`**

Replace its signature to add `contrastPhenomenon, classColors` at the end, and replace the per-vertex loop body. New version:

```js
function computeHeatmapColors(
    vertexRegionIds, eegData, selectedClasses, selectedBand, timeIndex,
    contrastMode, contrastOrder, erdThreshold, channelMode, maxAbs, mirror,
    contrastPhenomenon, classColors,
) {
    if (!vertexRegionIds?.length) return null;

    const regionAvg = computeRegionAveragesAtTime(
        eegData, selectedClasses, selectedBand, timeIndex,
        contrastMode, contrastOrder, channelMode, mirror,
    );

    const allVals = Object.values(regionAvg || {});
    if (allVals.length === 0) return null;

    const isContrast = !!classColors && typeof allVals[0] === 'object';
    const n = vertexRegionIds.length;
    const colors = new Float32Array(n * 3);

    for (let i = 0; i < n; i++) {
        const rid = vertexRegionIds[i];
        const val = regionAvg[rid];

        if (val === undefined) {
            colors[i * 3] = 0.12;
            colors[i * 3 + 1] = 0.12;
            colors[i * 3 + 2] = 0.12;
            continue;
        }

        if (isContrast) {
            const [r, g, b] = contrastColorRGB({
                ab: val, phenomenon: contrastPhenomenon,
                colorA: classColors.a, colorB: classColors.b,
                maxAbs, threshold: erdThreshold,
            });
            colors[i * 3] = r;
            colors[i * 3 + 1] = g;
            colors[i * 3 + 2] = b;
            continue;
        }

        // Non-contrast: diverging blue (ERD) - grey - red (ERS).
        if (Math.abs(val) < (erdThreshold || 0)) {
            colors[i * 3] = 0.2;
            colors[i * 3 + 1] = 0.2;
            colors[i * 3 + 2] = 0.2;
        } else {
            const norm = Math.max(-1, Math.min(1, val / maxAbs));
            if (norm < 0) {
                const t = -norm;
                colors[i * 3] = 0.15 * (1 - t) + 0.10 * t;
                colors[i * 3 + 1] = 0.15 * (1 - t) + 0.40 * t;
                colors[i * 3 + 2] = 0.15 * (1 - t) + 0.90 * t;
            } else {
                const t = norm;
                colors[i * 3] = 0.15 * (1 - t) + 0.90 * t;
                colors[i * 3 + 1] = 0.15 * (1 - t) + 0.20 * t;
                colors[i * 3 + 2] = 0.15 * (1 - t) + 0.10 * t;
            }
        }
    }

    return { colors, regionAvg };
}
```

- [ ] **Step 5: Accept the prop and derive `classColors` + thread phenomenon through the memo/effect**

In the `BrainViewer({ ... })` destructure, add `contrastPhenomenon,` after `channelMode,`.

After the `mirror` `useMemo`, add a `classColors` memo (rgb01 for the two contrasted classes):

```js
    const classColors = useMemo(() => {
        if (!contrastMode) return null;
        const classes = eegData?.dataset?.classes || [];
        const find = (id) => classes.find((c) => c.id === id)?.color;
        const a = find(contrastOrder?.[0]);
        const b = find(contrastOrder?.[1]);
        if (!a || !b) return null;
        return { a: hexToRgb01(a), b: hexToRgb01(b) };
    }, [contrastMode, contrastOrder, eegData]);
```

Update the `heatmapMaxAbs` memo call to pass `contrastPhenomenon` and add it to deps:

```js
    const heatmapMaxAbs = useMemo(
        () => computeHeatmapMaxAbs(
            eegData, selectedClasses, selectedBand, contrastMode, contrastOrder,
            channelMode, mirror, contrastPhenomenon,
        ),
        [eegData, selectedClasses, selectedBand, contrastMode, contrastOrder, channelMode, mirror, contrastPhenomenon],
    );
```

In the heatmap `useEffect`, update the `computeHeatmapColors(...)` call to pass `contrastPhenomenon, classColors` as the last two args, and add `contrastPhenomenon, classColors` to that effect's dependency array.

- [ ] **Step 6: Verify rendering in-browser**

Run dev server (`PORT=3137 npm run dev`). Select exactly **Left Hand + Right Hand**, Contrast ON, ERD selected, advance the timeline to mid-trial. The cortex should be colored magenta (Left Hand) / yellow (Right Hand) instead of blue/red; switching the toggle to ERS recolors; turning Contrast OFF restores blue/red. Hover the lit lateral motor strip — labels still resolve. No console errors. Stop dev server.

- [ ] **Step 7: Commit**

```bash
git add frontend/app/components/BrainViewer.jsx
git commit -m "feat(contrast): class-color cortex by ERD/ERS phenomenon"
```

---

### Task 4: Contrast legend + tooltip

**Files:**
- Modify: `frontend/app/components/BrainViewer.jsx`
- Modify: `frontend/app/globals.css`

- [ ] **Step 1: Stash contrast context for the tooltip**

In the heatmap `useEffect`, right after `const result = computeHeatmapColors(...)`, set a ref the hover handler can read:

```js
        configRef.current.contrast = (contrastMode && classColors)
            ? {
                phenomenon: contrastPhenomenon,
                labelA: eegData?.dataset?.classes?.find((c) => c.id === contrastOrder?.[0])?.label,
                labelB: eegData?.dataset?.classes?.find((c) => c.id === contrastOrder?.[1])?.label,
            }
            : null;
```

(`configRef` already exists.)

- [ ] **Step 2: Make the tooltip contrast-aware**

In the hover handler, replace the tooltip-text block:

```js
                const erdValue = heatmapValuesRef.current[regionId];
                let tooltipText = regionName;
                if (erdValue !== undefined) {
                    const sign = erdValue > 0 ? '+' : '';
                    tooltipText += ` (${sign}${erdValue.toFixed(1)}%)`;
                }
```

with:

```js
                const hv = heatmapValuesRef.current[regionId];
                let tooltipText = regionName;
                const cx = configRef.current.contrast;
                if (cx && hv && typeof hv === 'object') {
                    const { magnitude, winner } = contrastWinner(hv, cx.phenomenon);
                    if (magnitude > 0) {
                        const lbl = winner === 'a' ? cx.labelA : cx.labelB;
                        tooltipText += ` — ${lbl} (${cx.phenomenon.toUpperCase()}) ${magnitude.toFixed(1)}%`;
                    }
                } else if (typeof hv === 'number') {
                    const sign = hv > 0 ? '+' : '';
                    tooltipText += ` (${sign}${hv.toFixed(1)}%)`;
                }
```

- [ ] **Step 3: Swap the legend in contrast mode**

Replace the legend JSX block (`{heatmapEnabled && !loading && ( <div className="brain-legend"> ... </div> )}`) with a contrast-aware version:

```jsx
                {heatmapEnabled && !loading && contrastMode && classColorsLegend && (
                    <div className="brain-legend brain-legend-contrast">
                        <div className="brain-legend-contrast-title">
                            {contrastPhenomenon === 'ers' ? 'ERS' : 'ERD'} contrast
                        </div>
                        <span className="brain-legend-item">
                            <span className="brain-legend-dot" style={{ background: classColorsLegend.a }} />
                            {classColorsLegend.labelA}
                        </span>
                        <span className="brain-legend-item">
                            <span className="brain-legend-dot" style={{ background: classColorsLegend.b }} />
                            {classColorsLegend.labelB}
                        </span>
                    </div>
                )}
                {heatmapEnabled && !loading && !contrastMode && (
                    <div className="brain-legend">
                        <div className="brain-legend-bar">
                            <div className="brain-legend-gradient" />
                            <div className="brain-legend-labels">
                                <span>ERS +</span>
                                <span>0</span>
                                <span>ERD −</span>
                            </div>
                        </div>
                        <div className="brain-legend-desc">
                            <span className="brain-legend-item"><span className="brain-legend-dot brain-legend-dot-red" />Synchronization (power increase)</span>
                            <span className="brain-legend-item"><span className="brain-legend-dot brain-legend-dot-blue" />Desynchronization (power decrease)</span>
                        </div>
                    </div>
                )}
```

Add a `classColorsLegend` memo near the other memos (gives the legend the raw hex + labels):

```js
    const classColorsLegend = useMemo(() => {
        if (!contrastMode) return null;
        const classes = eegData?.dataset?.classes || [];
        const A = classes.find((c) => c.id === contrastOrder?.[0]);
        const B = classes.find((c) => c.id === contrastOrder?.[1]);
        if (!A || !B) return null;
        return { a: A.color, b: B.color, labelA: A.label, labelB: B.label };
    }, [contrastMode, contrastOrder, eegData]);
```

- [ ] **Step 4: Legend CSS**

Append to `frontend/app/globals.css`:

```css
/* === Contrast legend === */
.brain-legend-contrast {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
}
.brain-legend-contrast-title {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    color: #aaa;
}
```

- [ ] **Step 5: Verify in-browser**

Run dev server. Contrast ON, Left vs Right hand: the blue/red legend is replaced by a two-swatch legend ("ERD contrast", Left Hand magenta, Right Hand yellow). Hover a colored region → tooltip reads e.g. `L G_precentral — Left Hand (ERD) 18.0%`. Switch to ERS → legend title flips to "ERS contrast". Contrast OFF → blue/red legend returns and tooltip shows `(+X.X%)`. No console errors. Stop dev server.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/components/BrainViewer.jsx frontend/app/globals.css
git commit -m "feat(contrast): class-swatch legend + contrast-aware tooltip"
```

---

### Task 5: End-to-end verification + branch wrap-up

**Files:** none (verification only)

- [ ] **Step 1: Full in-browser pass with `playwright-cli`**

Start `PORT=3137 npm run dev`. With Left Hand + Right Hand selected, Contrast ON:
- ERD mode, mid-trial time: confirm right hemisphere ≈ Left-Hand color, left hemisphere ≈ Right-Hand color (lateralization); hover both motor strips and read the tooltip class/phenomenon.
- Toggle ERS: colors + legend title update live.
- Toggle Contrast OFF: blue/red heatmap + original legend restored; tooltip shows `(+X.X%)`.
- Mirror toggle still works in contrast mode (midline regions update symmetrically).
- Check `playwright-cli console error` → 0 errors.
Capture one before/after screenshot for the PR. Stop the dev server; remove screenshots and `.playwright-cli/`.

- [ ] **Step 2: Re-run the unit test**

Run: `cd frontend && node app/lib/contrastColor.test.mjs` → PASS.

- [ ] **Step 3: Push branch + open PR**

```bash
git push -u origin feat/erd-ers-contrast-coloring
gh pr create --base main --head feat/erd-ers-contrast-coloring \
  --title "Contrast mode: class-colored ERD/ERS coloring with phenomenon toggle" \
  --body "Implements docs/superpowers/specs/2026-06-13-erd-ers-contrast-coloring-design.md"
```

---

## Self-review notes (author)

- **Spec coverage:** scope (Task 3/4 gate on `contrastMode`), class-color scheme (Task 1+3), ERD|ERS toggle default ERD (Task 2), winner-by-difference + threshold + grey (Task 1), legend swap (Task 4), tooltip (Task 4), Mirror still applies (Task 3 `bucketize`), maxAbs normalization (Task 3). All covered.
- **Naming consistency:** `contrastPhenomenon` ('erd'|'ers'), `classColors` ({a,b} rgb01) vs `classColorsLegend` ({a,b} hex + labels) used consistently across tasks. `contrastWinner`/`contrastColorRGB`/`hexToRgb01` imported in BrainViewer match the module exports in Task 1.
- **No placeholders:** every code step has complete code.
