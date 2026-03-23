'use client';

import { useEffect, useRef, useCallback, useMemo } from 'react';

const CHANNEL_ORDER = [
    'Fz', 'FC3', 'FC1', 'FCz', 'FC2', 'FC4',
    'C5', 'C3', 'C1', 'Cz', 'C2', 'C4', 'C6',
    'CP3', 'CP1', 'CPz', 'CP2', 'CP4',
    'P1', 'Pz', 'P2', 'POz',
];
const GROUP_BREAKS = [6, 13, 18];

function erdToColor(value, maxAbs) {
    const norm = Math.max(-1, Math.min(1, value / (maxAbs || 1)));
    let r, g, b;
    if (norm < 0) {
        const t = -norm;
        r = Math.round(30 * (1 - t) + 30 * t);
        g = Math.round(30 * (1 - t) + 100 * t);
        b = Math.round(30 * (1 - t) + 220 * t);
    } else {
        const t = norm;
        r = Math.round(30 * (1 - t) + 220 * t);
        g = Math.round(30 * (1 - t) + 50 * t);
        b = Math.round(30 * (1 - t) + 30 * t);
    }
    return `rgb(${r},${g},${b})`;
}

function niceStep(range, maxTicks) {
    if (range <= 0) return 1;
    const rough = range / maxTicks;
    const pow = Math.pow(10, Math.floor(Math.log10(rough)));
    const norm = rough / pow;
    if (norm <= 1.5) return pow;
    if (norm <= 3) return 2 * pow;
    if (norm <= 7) return 5 * pow;
    return 10 * pow;
}

export default function TimelineHeatmap({
    eegData, selectedClasses, selectedBand, currentTimeIndex, onTimeChange,
}) {
    const canvasRef = useRef(null);
    const containerRef = useRef(null);

    const bandData = eegData?.erd_ers?.[selectedBand];
    const times = bandData?.times || [];
    const channels = eegData?.dataset?.channels || [];
    const classes = eegData?.dataset?.classes || [];
    const activeClasses = useMemo(
        () => classes.filter((c) => selectedClasses.has(c.id)),
        [classes, selectedClasses],
    );

    const orderedChannels = useMemo(
        () => CHANNEL_ORDER.filter((ch) => channels.includes(ch)),
        [channels],
    );

    const { matrix, maxAbs } = useMemo(() => {
        if (!bandData || !times.length || !activeClasses.length)
            return { matrix: [], maxAbs: 1 };
        const mat = [];
        let mAbs = 0;
        for (const ch of orderedChannels) {
            const ci = channels.indexOf(ch);
            const row = new Array(times.length).fill(0);
            let count = 0;
            for (const cls of activeClasses) {
                const cd = bandData[cls.id];
                if (cd?.[ci]) {
                    for (let t = 0; t < times.length; t++) row[t] += cd[ci][t];
                    count++;
                }
            }
            if (count > 0)
                for (let t = 0; t < times.length; t++) row[t] /= count;
            for (const v of row) {
                const a = Math.abs(v);
                if (a > mAbs) mAbs = a;
            }
            mat.push(row);
        }
        return { matrix: mat, maxAbs: mAbs || 1 };
    }, [bandData, times, orderedChannels, channels, activeClasses]);

    const draw = useCallback(() => {
        const canvas = canvasRef.current;
        if (!canvas || !matrix.length || !times.length) return;
        const dpr = window.devicePixelRatio || 1;
        const rect = canvas.getBoundingClientRect();
        if (!rect.width || !rect.height) return;
        canvas.width = Math.round(rect.width * dpr);
        canvas.height = Math.round(rect.height * dpr);
        const ctx = canvas.getContext('2d');
        ctx.scale(dpr, dpr);
        const w = rect.width, h = rect.height;

        ctx.fillStyle = '#0d0d0d';
        ctx.fillRect(0, 0, w, h);

        const pad = { top: 4, right: 52, bottom: 22, left: 44 };
        const plotW = w - pad.left - pad.right;
        const plotH = h - pad.top - pad.bottom;
        const nCh = matrix.length;
        const nT = times.length;
        const cellW = plotW / nT;
        const cellH = plotH / nCh;
        const tmin = times[0], tmax = times[nT - 1];
        const tRange = tmax - tmin || 1;
        const xFor = (t) => pad.left + ((t - tmin) / tRange) * plotW;

        // Cells
        for (let ci = 0; ci < nCh; ci++) {
            for (let ti = 0; ti < nT; ti++) {
                ctx.fillStyle = erdToColor(matrix[ci][ti], maxAbs);
                ctx.fillRect(
                    pad.left + ti * cellW,
                    pad.top + ci * cellH,
                    cellW + 0.5,
                    cellH + 0.5,
                );
            }
        }

        // Group dividers
        ctx.strokeStyle = '#666';
        ctx.lineWidth = 1;
        for (const brk of GROUP_BREAKS) {
            if (brk < nCh) {
                const y = pad.top + brk * cellH;
                ctx.beginPath();
                ctx.moveTo(pad.left, y);
                ctx.lineTo(pad.left + plotW, y);
                ctx.stroke();
            }
        }

        // Channel labels
        ctx.fillStyle = '#888';
        ctx.font = `${Math.min(10, Math.max(7, cellH - 1))}px system-ui`;
        ctx.textAlign = 'right';
        for (let ci = 0; ci < nCh; ci++) {
            ctx.fillText(
                orderedChannels[ci],
                pad.left - 4,
                pad.top + ci * cellH + cellH / 2 + 3,
            );
        }

        // Cue line
        ctx.strokeStyle = 'rgba(255,255,255,0.5)';
        ctx.lineWidth = 1;
        ctx.setLineDash([2, 2]);
        ctx.beginPath();
        ctx.moveTo(xFor(0), pad.top);
        ctx.lineTo(xFor(0), pad.top + plotH);
        ctx.stroke();
        ctx.setLineDash([]);

        // Playhead
        if (currentTimeIndex >= 0 && currentTimeIndex < nT) {
            ctx.strokeStyle = '#6ee7b7';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(xFor(times[currentTimeIndex]), pad.top);
            ctx.lineTo(xFor(times[currentTimeIndex]), pad.top + plotH);
            ctx.stroke();
        }

        // Time labels
        ctx.fillStyle = '#444';
        ctx.textAlign = 'center';
        ctx.font = '9px system-ui';
        const tStep = niceStep(tRange, 8);
        for (let t = Math.ceil(tmin / tStep) * tStep; t <= tmax; t += tStep) {
            if (Math.abs(t) < 0.01) continue;
            ctx.fillText(`${t.toFixed(1)}s`, xFor(t), h - 4);
        }
        ctx.fillStyle = '#555';
        ctx.fillText('cue', xFor(0), h - 4);

        // Color scale legend
        const lx = w - pad.right + 10;
        const lw = 10;
        const nSteps = 40;
        const stepH = plotH / nSteps;
        for (let i = 0; i < nSteps; i++) {
            const v = maxAbs * (1 - (2 * i) / (nSteps - 1));
            ctx.fillStyle = erdToColor(v, maxAbs);
            ctx.fillRect(lx, pad.top + i * stepH, lw, stepH + 0.5);
        }
        ctx.fillStyle = '#888';
        ctx.font = '8px system-ui';
        ctx.textAlign = 'left';
        ctx.fillText(`+${maxAbs.toFixed(0)}%`, lx + lw + 3, pad.top + 7);
        ctx.fillText('0%', lx + lw + 3, pad.top + plotH / 2 + 3);
        ctx.fillText(`-${maxAbs.toFixed(0)}%`, lx + lw + 3, pad.top + plotH - 1);
    }, [matrix, maxAbs, times, orderedChannels, currentTimeIndex]);

    useEffect(() => {
        const el = containerRef.current;
        if (!el) return;
        const obs = new ResizeObserver(() => draw());
        obs.observe(el);
        return () => obs.disconnect();
    }, [draw]);

    useEffect(() => {
        draw();
    }, [draw]);

    const handleClick = useCallback(
        (e) => {
            const canvas = canvasRef.current;
            if (!canvas || !times.length) return;
            const rect = canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const tmin = times[0], tmax = times[times.length - 1];
            const t = tmin + ((x - 44) / (rect.width - 44 - 52)) * (tmax - tmin);
            let best = 0,
                bestD = Infinity;
            for (let i = 0; i < times.length; i++) {
                const d = Math.abs(times[i] - t);
                if (d < bestD) {
                    bestD = d;
                    best = i;
                }
            }
            onTimeChange(best);
        },
        [times, onTimeChange],
    );

    return (
        <div ref={containerRef} className="tl-canvas-wrap">
            <canvas
                ref={canvasRef}
                className="tl-canvas"
                onClick={handleClick}
            />
        </div>
    );
}
