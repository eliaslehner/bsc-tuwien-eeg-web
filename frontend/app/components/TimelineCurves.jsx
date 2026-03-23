'use client';

import { useEffect, useRef, useCallback, useMemo } from 'react';

const MOTOR_CHANNELS = ['C3', 'Cz', 'C4'];

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

export default function TimelineCurves({
    eegData, selectedClasses, selectedBand, currentTimeIndex, onTimeChange,
    channelMode, stacked,
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

    const channelIndices = useMemo(() => {
        if (channelMode === 'all') return channels.map((_, i) => i);
        if (channelMode === 'motor') {
            const m = channels.reduce((a, ch, i) => {
                if (MOTOR_CHANNELS.includes(ch)) a.push(i);
                return a;
            }, []);
            return m.length > 0 ? m : channels.map((_, i) => i);
        }
        const idx = channels.indexOf(channelMode);
        return idx >= 0 ? [idx] : [0];
    }, [channels, channelMode]);

    const curves = useMemo(() => {
        if (!bandData || !times.length) return {};
        const result = {};
        for (const cls of activeClasses) {
            const cd = bandData[cls.id];
            if (!cd) continue;
            const avg = new Array(times.length).fill(0);
            let n = 0;
            for (const ci of channelIndices) {
                if (cd[ci]) {
                    for (let t = 0; t < times.length; t++) avg[t] += cd[ci][t];
                    n++;
                }
            }
            if (n > 0) for (let t = 0; t < times.length; t++) avg[t] /= n;
            result[cls.id] = avg;
        }
        return result;
    }, [bandData, times, activeClasses, channelIndices]);

    const yRange = useMemo(() => {
        let min = 0, max = 0;
        for (const c of Object.values(curves)) {
            for (const v of c) {
                if (v < min) min = v;
                if (v > max) max = v;
            }
        }
        const p = Math.max((max - min) * 0.15, 5);
        return { min: min - p, max: max + p };
    }, [curves]);

    const draw = useCallback(() => {
        const canvas = canvasRef.current;
        if (!canvas || !times.length || !activeClasses.length) return;
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

        const tmin = times[0], tmax = times[times.length - 1];
        const tRange = tmax - tmin || 1;
        const pad = stacked
            ? { top: 4, right: 16, bottom: 22, left: 80 }
            : { top: 10, right: 16, bottom: 22, left: 50 };
        const plotW = w - pad.left - pad.right;
        const plotH = h - pad.top - pad.bottom;
        const xFor = (t) => pad.left + ((t - tmin) / tRange) * plotW;

        if (stacked) {
            const n = activeClasses.length;
            const gap = 3;
            const laneH = (plotH - gap * Math.max(0, n - 1)) / n;

            for (let li = 0; li < n; li++) {
                const cls = activeClasses[li];
                const curve = curves[cls.id];
                if (!curve) continue;
                const top = pad.top + li * (laneH + gap);
                const yFor = (v) =>
                    top + laneH - ((v - yRange.min) / (yRange.max - yRange.min)) * laneH;

                // Lane background
                ctx.fillStyle = '#0f0f0f';
                ctx.fillRect(pad.left, top, plotW, laneH);

                // Zero line
                if (yRange.min < 0 && yRange.max > 0) {
                    ctx.strokeStyle = '#222';
                    ctx.lineWidth = 1;
                    ctx.setLineDash([3, 3]);
                    ctx.beginPath();
                    ctx.moveTo(pad.left, yFor(0));
                    ctx.lineTo(pad.left + plotW, yFor(0));
                    ctx.stroke();
                    ctx.setLineDash([]);
                }

                // Baseline shade
                if (tmin < 0) {
                    ctx.fillStyle = 'rgba(255,255,255,0.02)';
                    ctx.fillRect(xFor(tmin), top, xFor(0) - xFor(tmin), laneH);
                }

                // Cue line
                ctx.strokeStyle = '#333';
                ctx.lineWidth = 1;
                ctx.setLineDash([2, 2]);
                ctx.beginPath();
                ctx.moveTo(xFor(0), top);
                ctx.lineTo(xFor(0), top + laneH);
                ctx.stroke();
                ctx.setLineDash([]);

                // Fill under curve
                ctx.globalAlpha = 0.08;
                ctx.fillStyle = cls.color;
                ctx.beginPath();
                for (let i = 0; i < times.length; i++) {
                    const x = xFor(times[i]), y = yFor(curve[i]);
                    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
                }
                ctx.lineTo(xFor(times[times.length - 1]), yFor(0));
                ctx.lineTo(xFor(times[0]), yFor(0));
                ctx.closePath();
                ctx.fill();
                ctx.globalAlpha = 1;

                // Curve line
                ctx.strokeStyle = cls.color;
                ctx.lineWidth = 2;
                ctx.beginPath();
                for (let i = 0; i < times.length; i++) {
                    const x = xFor(times[i]), y = yFor(curve[i]);
                    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
                }
                ctx.stroke();

                // Playhead
                if (currentTimeIndex >= 0 && currentTimeIndex < times.length) {
                    const xp = xFor(times[currentTimeIndex]);
                    ctx.strokeStyle = '#6ee7b7';
                    ctx.lineWidth = 1.5;
                    ctx.beginPath();
                    ctx.moveTo(xp, top);
                    ctx.lineTo(xp, top + laneH);
                    ctx.stroke();
                    ctx.fillStyle = cls.color;
                    ctx.beginPath();
                    ctx.arc(xp, yFor(curve[currentTimeIndex]), 3.5, 0, Math.PI * 2);
                    ctx.fill();
                }

                // Class label + value
                ctx.fillStyle = cls.color;
                ctx.font = '11px system-ui';
                ctx.textAlign = 'right';
                ctx.fillText(cls.label, pad.left - 8, top + laneH / 2 - 2);
                if (currentTimeIndex >= 0 && currentTimeIndex < curve.length) {
                    const v = curve[currentTimeIndex];
                    ctx.fillStyle = '#777';
                    ctx.font = '10px "Consolas", monospace';
                    ctx.fillText(
                        `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`,
                        pad.left - 8,
                        top + laneH / 2 + 12,
                    );
                }
            }
        } else {
            // --- Overlay mode ---
            const yFor = (v) =>
                pad.top + plotH - ((v - yRange.min) / (yRange.max - yRange.min)) * plotH;

            // Grid
            ctx.strokeStyle = '#1a1a1a';
            ctx.lineWidth = 1;
            ctx.font = '10px system-ui';
            ctx.fillStyle = '#555';
            ctx.textAlign = 'right';
            const yStep = niceStep(yRange.max - yRange.min, 5);
            for (
                let yv = Math.ceil(yRange.min / yStep) * yStep;
                yv <= yRange.max;
                yv += yStep
            ) {
                const y = yFor(yv);
                ctx.beginPath();
                ctx.moveTo(pad.left, y);
                ctx.lineTo(pad.left + plotW, y);
                ctx.stroke();
                ctx.fillText(`${yv.toFixed(0)}%`, pad.left - 6, y + 3);
            }

            // Zero line
            if (yRange.min < 0 && yRange.max > 0) {
                ctx.strokeStyle = '#333';
                ctx.setLineDash([4, 4]);
                ctx.beginPath();
                ctx.moveTo(pad.left, yFor(0));
                ctx.lineTo(pad.left + plotW, yFor(0));
                ctx.stroke();
                ctx.setLineDash([]);
            }

            // Baseline shade
            if (tmin < 0) {
                ctx.fillStyle = 'rgba(255,255,255,0.03)';
                ctx.fillRect(xFor(tmin), pad.top, xFor(0) - xFor(tmin), plotH);
            }

            // Cue line
            ctx.strokeStyle = '#444';
            ctx.setLineDash([3, 3]);
            ctx.beginPath();
            ctx.moveTo(xFor(0), pad.top);
            ctx.lineTo(xFor(0), pad.top + plotH);
            ctx.stroke();
            ctx.setLineDash([]);

            // Curves
            for (const cls of activeClasses) {
                const curve = curves[cls.id];
                if (!curve) continue;
                ctx.strokeStyle = cls.color;
                ctx.lineWidth = 2;
                ctx.beginPath();
                for (let i = 0; i < times.length; i++) {
                    const x = xFor(times[i]), y = yFor(curve[i]);
                    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
                }
                ctx.stroke();
            }

            // Playhead + dots
            if (currentTimeIndex >= 0 && currentTimeIndex < times.length) {
                const xp = xFor(times[currentTimeIndex]);
                ctx.strokeStyle = '#6ee7b7';
                ctx.lineWidth = 1.5;
                ctx.beginPath();
                ctx.moveTo(xp, pad.top);
                ctx.lineTo(xp, pad.top + plotH);
                ctx.stroke();
                for (const cls of activeClasses) {
                    const curve = curves[cls.id];
                    if (!curve) continue;
                    ctx.fillStyle = cls.color;
                    ctx.beginPath();
                    ctx.arc(xp, yFor(curve[currentTimeIndex]), 4, 0, Math.PI * 2);
                    ctx.fill();
                }
            }

            // Legend
            ctx.textAlign = 'right';
            ctx.font = '10px system-ui';
            let ly = pad.top + 14;
            for (const cls of activeClasses) {
                const curve = curves[cls.id];
                const val = curve?.[currentTimeIndex];
                let text = cls.label;
                if (val !== undefined)
                    text += ` ${val >= 0 ? '+' : ''}${val.toFixed(1)}%`;
                const tw = ctx.measureText(text).width;
                const lx = w - pad.right - 8;
                ctx.fillStyle = 'rgba(0,0,0,0.6)';
                ctx.fillRect(lx - tw - 18, ly - 10, tw + 22, 16);
                ctx.fillStyle = cls.color;
                ctx.beginPath();
                ctx.arc(lx - tw - 8, ly - 2, 3.5, 0, Math.PI * 2);
                ctx.fill();
                ctx.fillStyle = '#ccc';
                ctx.fillText(text, lx, ly + 1);
                ly += 20;
            }
        }

        // Time labels (shared)
        ctx.fillStyle = '#444';
        ctx.textAlign = 'center';
        ctx.font = '9px system-ui';
        const tStep = niceStep(tRange, 8);
        for (
            let t = Math.ceil(tmin / tStep) * tStep;
            t <= tmax;
            t += tStep
        ) {
            if (Math.abs(t) < 0.01) continue;
            ctx.fillText(`${t.toFixed(1)}s`, xFor(t), h - 4);
        }
        ctx.fillStyle = '#555';
        ctx.fillText('cue', xFor(0), h - 4);
    }, [times, curves, activeClasses, yRange, currentTimeIndex, stacked]);

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
            const padL = stacked ? 80 : 50;
            const plotW = rect.width - padL - 16;
            const tmin = times[0], tmax = times[times.length - 1];
            const t = tmin + ((x - padL) / plotW) * (tmax - tmin);
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
        [times, onTimeChange, stacked],
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
