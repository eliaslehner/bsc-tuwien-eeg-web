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
