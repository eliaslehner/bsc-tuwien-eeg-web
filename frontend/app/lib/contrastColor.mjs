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
