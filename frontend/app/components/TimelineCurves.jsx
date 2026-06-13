'use client';

import { useEffect, useRef, useCallback, useMemo, useState } from 'react';
import { MOTOR_CHANNELS } from '../lib/eeg';

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
    channelMode, stacked, visibleRange, contrastMode, contrastOrder,
}) {
    const canvasRef = useRef(null);
    const containerRef = useRef(null);
    const [mousePos, setMousePos] = useState(null);

    const bandData = eegData?.erd_ers?.[selectedBand];
    const times = bandData?.times || [];
    const channels = eegData?.dataset?.channels || [];
    const classes = eegData?.dataset?.classes || [];
    const activeClasses = useMemo(
        () => classes.filter((c) => selectedClasses.has(c.id)),
        [classes, selectedClasses],
    );

    const channelIndices = useMemo(() => {
        if (channelMode === 'all' || channelMode === 'all_individual') return channels.map((_, i) => i);
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
            
            if (channelMode === 'all_individual') {
                result[cls.id] = { individual: true, lines: [] };
                for (const ci of channelIndices) {
                    if (cd[ci]) {
                        result[cls.id].lines.push({ chName: channels[ci], data: cd[ci] });
                    }
                }
            } else {
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
        }
        return result;
    }, [bandData, times, activeClasses, channelIndices, channelMode, channels]);

    const diffCurve = useMemo(() => {
        if (!contrastMode || !contrastOrder?.[0] || !contrastOrder?.[1]) return null;
        const c1 = curves[contrastOrder[0]];
        const c2 = curves[contrastOrder[1]];
        if (!c1 || !c2 || c1.individual || c2.individual) return null;
        // Absolute difference: the contrast is order-independent (the brain colours
        // by the stronger class either way), so the curve shows the magnitude only.
        return c1.map((v, i) => Math.abs(v - c2[i]));
    }, [contrastMode, contrastOrder, curves]);

    const yRange = useMemo(() => {
        let min = 0, max = 0;
        for (const c of Object.values(curves)) {
            if (c.individual) {
                for (const line of c.lines) {
                    for (const v of line.data) {
                        if (v < min) min = v;
                        if (v > max) max = v;
                    }
                }
            } else {
                for (const v of c) {
                    if (v < min) min = v;
                    if (v > max) max = v;
                }
            }
        }
        if (diffCurve) {
            for (const v of diffCurve) {
                if (v < min) min = v;
                if (v > max) max = v;
            }
        }
        const p = Math.max((max - min) * 0.15, 5);
        return { min: min - p, max: max + p };
    }, [curves, diffCurve]);

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

        const vStart = visibleRange?.start ?? 0;
        const vEnd = visibleRange?.end ?? (times.length - 1);
        const tmin = times[vStart], tmax = times[vEnd];
        const tRange = tmax - tmin || 1;
        const pad = stacked
            ? { top: 4, right: 16, bottom: 22, left: 80 }
            : { top: 10, right: 16, bottom: 22, left: 50 };
        const plotW = w - pad.left - pad.right;
        const plotH = h - pad.top - pad.bottom;
        const xFor = (t) => pad.left + ((t - tmin) / tRange) * plotW;

        if (stacked) {
            const hasDiff = !!diffCurve;
            const n = activeClasses.length + (hasDiff ? 1 : 0);
            const gap = 3;
            const laneH = (plotH - gap * Math.max(0, n - 1)) / n;

            for (let li = 0; li < activeClasses.length; li++) {
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

                // Fill under averaged curves
                if (!curve.individual) {
                    ctx.globalAlpha = 0.08;
                    ctx.fillStyle = cls.color;
                    ctx.beginPath();
                    for (let i = vStart; i <= vEnd; i++) {
                        const x = xFor(times[i]), y = yFor(curve[i]);
                        i === vStart ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
                    }
                    ctx.lineTo(xFor(times[vEnd]), yFor(0));
                    ctx.lineTo(xFor(times[vStart]), yFor(0));
                    ctx.closePath();
                    ctx.fill();
                    ctx.globalAlpha = 1;
                }

                // Curve line(s)
                if (curve.individual) {
                    // Find hovered electrode (nearest to mouse Y at playhead X)
                    let hoveredIdx = -1;
                    if (mousePos && currentTimeIndex >= 0 && currentTimeIndex < times.length) {
                        let bestDist = Infinity;
                        for (let cIdx = 0; cIdx < curve.lines.length; cIdx++) {
                            const yVal = yFor(curve.lines[cIdx].data[currentTimeIndex]);
                            const dist = Math.abs(mousePos.y - yVal);
                            if (dist < bestDist) {
                                bestDist = dist;
                                hoveredIdx = cIdx;
                            }
                        }
                        if (bestDist > 30) hoveredIdx = -1;
                    }

                    for (let cIdx = 0; cIdx < curve.lines.length; cIdx++) {
                        const lineData = curve.lines[cIdx].data;
                        const isHovered = cIdx === hoveredIdx;
                        ctx.strokeStyle = cls.color;
                        ctx.globalAlpha = isHovered ? 1 : 0.3;
                        ctx.lineWidth = isHovered ? 2 : 1;
                        ctx.beginPath();
                        for (let i = vStart; i <= vEnd; i++) {
                            const x = xFor(times[i]), y = yFor(lineData[i]);
                            i === vStart ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
                        }
                        ctx.stroke();
                    }
                    ctx.globalAlpha = 1;

                    // Draw electrode tooltip for hovered line
                    if (hoveredIdx >= 0 && mousePos) {
                        const chName = curve.lines[hoveredIdx].chName;
                        const val = curve.lines[hoveredIdx].data[currentTimeIndex];
                        const label = `${chName}: ${val >= 0 ? '+' : ''}${val.toFixed(1)}%`;
                        ctx.font = '11px system-ui';
                        const tw = ctx.measureText(label).width;
                        const tx = Math.min(mousePos.x + 12, w - tw - 8);
                        const ty = Math.max(mousePos.y - 10, top + 14);
                        ctx.fillStyle = 'rgba(0,0,0,0.8)';
                        ctx.fillRect(tx - 4, ty - 11, tw + 8, 16);
                        ctx.fillStyle = cls.color;
                        ctx.fillText(label, tx, ty);
                    }

                    // Playhead
                    if (currentTimeIndex >= 0 && currentTimeIndex < times.length) {
                        const xp = xFor(times[currentTimeIndex]);
                        ctx.strokeStyle = '#6ee7b7';
                        ctx.lineWidth = 1.5;
                        ctx.beginPath();
                        ctx.moveTo(xp, top);
                        ctx.lineTo(xp, top + laneH);
                        ctx.stroke();
                    }
                } else {
                    // Standard single curve
                    ctx.strokeStyle = cls.color;
                    ctx.lineWidth = 2;
                    ctx.beginPath();
                    for (let i = vStart; i <= vEnd; i++) {
                        const x = xFor(times[i]), y = yFor(curve[i]);
                        i === vStart ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
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
                }

                // Class label + value
                ctx.fillStyle = cls.color;
                ctx.font = '11px system-ui';
                ctx.textAlign = 'right';
                ctx.fillText(cls.label, pad.left - 8, top + laneH / 2 - 2);
                if (!curve.individual && currentTimeIndex >= 0 && currentTimeIndex < curve.length) {
                    const v = curve[currentTimeIndex];
                    ctx.fillStyle = '#777';
                    ctx.font = '10px "Consolas", monospace';
                    ctx.fillText(
                        `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`,
                        pad.left - 8,
                        top + laneH / 2 + 12,
                    );
                } else if (curve.individual) {
                    ctx.fillStyle = '#777';
                    ctx.font = '9px "Consolas", monospace';
                    ctx.fillText('All Chs', pad.left - 8, top + laneH / 2 + 12);
                }
            }

            // Difference curve lane (stacked)
            if (hasDiff) {
                const diffColor = '#6ee7b7';
                const li = activeClasses.length;
                const top = pad.top + li * (laneH + gap);
                const yFor = (v) =>
                    top + laneH - ((v - yRange.min) / (yRange.max - yRange.min)) * laneH;

                ctx.fillStyle = '#0a0f0d';
                ctx.fillRect(pad.left, top, plotW, laneH);

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

                ctx.strokeStyle = '#333';
                ctx.lineWidth = 1;
                ctx.setLineDash([2, 2]);
                ctx.beginPath();
                ctx.moveTo(xFor(0), top);
                ctx.lineTo(xFor(0), top + laneH);
                ctx.stroke();
                ctx.setLineDash([]);

                // Fill
                ctx.globalAlpha = 0.1;
                ctx.fillStyle = diffColor;
                ctx.beginPath();
                for (let i = vStart; i <= vEnd; i++) {
                    const x = xFor(times[i]), y = yFor(diffCurve[i]);
                    i === vStart ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
                }
                ctx.lineTo(xFor(times[vEnd]), yFor(0));
                ctx.lineTo(xFor(times[vStart]), yFor(0));
                ctx.closePath();
                ctx.fill();
                ctx.globalAlpha = 1;

                // Line
                ctx.strokeStyle = diffColor;
                ctx.lineWidth = 2;
                ctx.beginPath();
                for (let i = vStart; i <= vEnd; i++) {
                    const x = xFor(times[i]), y = yFor(diffCurve[i]);
                    i === vStart ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
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
                    ctx.fillStyle = diffColor;
                    ctx.beginPath();
                    ctx.arc(xp, yFor(diffCurve[currentTimeIndex]), 3.5, 0, Math.PI * 2);
                    ctx.fill();
                }

                // Label
                ctx.fillStyle = diffColor;
                ctx.font = '11px system-ui';
                ctx.textAlign = 'right';
                ctx.fillText('Diff', pad.left - 8, top + laneH / 2 - 2);
                if (currentTimeIndex >= 0 && currentTimeIndex < diffCurve.length) {
                    const v = diffCurve[currentTimeIndex];
                    ctx.fillStyle = '#777';
                    ctx.font = '10px "Consolas", monospace';
                    ctx.fillText(`${v >= 0 ? '+' : ''}${v.toFixed(1)}%`, pad.left - 8, top + laneH / 2 + 12);
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
                if (curve.individual) {
                    let hoveredIdx = -1;
                    if (mousePos && currentTimeIndex >= 0 && currentTimeIndex < times.length) {
                        let bestDist = Infinity;
                        for (let cIdx = 0; cIdx < curve.lines.length; cIdx++) {
                            const yVal = yFor(curve.lines[cIdx].data[currentTimeIndex]);
                            const dist = Math.abs(mousePos.y - yVal);
                            if (dist < bestDist) {
                                bestDist = dist;
                                hoveredIdx = cIdx;
                            }
                        }
                        if (bestDist > 30) hoveredIdx = -1;
                    }
                    for (let cIdx = 0; cIdx < curve.lines.length; cIdx++) {
                        const lineData = curve.lines[cIdx].data;
                        const isHovered = cIdx === hoveredIdx;
                        ctx.strokeStyle = cls.color;
                        ctx.globalAlpha = isHovered ? 1 : 0.3;
                        ctx.lineWidth = isHovered ? 2 : 1;
                        ctx.beginPath();
                        for (let i = vStart; i <= vEnd; i++) {
                            const x = xFor(times[i]), y = yFor(lineData[i]);
                            i === vStart ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
                        }
                        ctx.stroke();
                    }
                    ctx.globalAlpha = 1;
                    if (hoveredIdx >= 0 && mousePos) {
                        const chName = curve.lines[hoveredIdx].chName;
                        const val = curve.lines[hoveredIdx].data[currentTimeIndex];
                        const label = `${chName}: ${val >= 0 ? '+' : ''}${val.toFixed(1)}%`;
                        ctx.font = '11px system-ui';
                        const tw = ctx.measureText(label).width;
                        const tx = Math.min(mousePos.x + 12, w - tw - 8);
                        const ty = Math.max(mousePos.y - 10, pad.top + 14);
                        ctx.fillStyle = 'rgba(0,0,0,0.8)';
                        ctx.fillRect(tx - 4, ty - 11, tw + 8, 16);
                        ctx.fillStyle = cls.color;
                        ctx.fillText(label, tx, ty);
                    }
                } else {
                    ctx.strokeStyle = cls.color;
                    ctx.lineWidth = 2;
                    ctx.beginPath();
                    for (let i = vStart; i <= vEnd; i++) {
                        const x = xFor(times[i]), y = yFor(curve[i]);
                        i === vStart ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
                    }
                    ctx.stroke();
                }
            }

            // Difference curve (overlay)
            if (diffCurve) {
                const diffColor = '#6ee7b7';
                ctx.strokeStyle = diffColor;
                ctx.lineWidth = 2;
                ctx.setLineDash([6, 3]);
                ctx.beginPath();
                for (let i = vStart; i <= vEnd; i++) {
                    const x = xFor(times[i]), y = yFor(diffCurve[i]);
                    i === vStart ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
                }
                ctx.stroke();
                ctx.setLineDash([]);
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
                    if (!curve || curve.individual) continue;
                    ctx.fillStyle = cls.color;
                    ctx.beginPath();
                    ctx.arc(xp, yFor(curve[currentTimeIndex]), 4, 0, Math.PI * 2);
                    ctx.fill();
                }
                if (diffCurve) {
                    ctx.fillStyle = '#6ee7b7';
                    ctx.beginPath();
                    ctx.arc(xp, yFor(diffCurve[currentTimeIndex]), 4, 0, Math.PI * 2);
                    ctx.fill();
                }
            }

            // Legend
            ctx.textAlign = 'right';
            ctx.font = '10px system-ui';
            let ly = pad.top + 14;
            for (const cls of activeClasses) {
                const curve = curves[cls.id];
                const val = curve && !curve.individual ? curve[currentTimeIndex] : undefined;
                let text = cls.label;
                if (curve && curve.individual) {
                    text += ` (Individual)`;
                } else if (val !== undefined) {
                    text += ` ${val >= 0 ? '+' : ''}${val.toFixed(1)}%`;
                }
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
            if (diffCurve) {
                const diffColor = '#6ee7b7';
                const val = diffCurve[currentTimeIndex];
                let text = `Diff ${val !== undefined ? val.toFixed(1) + '%' : ''}`;
                const tw = ctx.measureText(text).width;
                const lx = w - pad.right - 8;
                ctx.fillStyle = 'rgba(0,0,0,0.6)';
                ctx.fillRect(lx - tw - 18, ly - 10, tw + 22, 16);
                ctx.fillStyle = diffColor;
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
    }, [times, curves, activeClasses, yRange, currentTimeIndex, stacked, mousePos, visibleRange, diffCurve]);

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
            const vS = visibleRange?.start ?? 0;
            const vE = visibleRange?.end ?? (times.length - 1);
            const tmin = times[vS], tmax = times[vE];
            const t = tmin + ((x - padL) / plotW) * (tmax - tmin);
            let best = vS,
                bestD = Infinity;
            for (let i = vS; i <= vE; i++) {
                const d = Math.abs(times[i] - t);
                if (d < bestD) {
                    bestD = d;
                    best = i;
                }
            }
            onTimeChange(best);
        },
        [times, onTimeChange, stacked, visibleRange],
    );

    const handleMouseMove = useCallback((e) => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const rect = canvas.getBoundingClientRect();
        setMousePos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
    }, []);

    const handleMouseLeave = useCallback(() => setMousePos(null), []);

    if (activeClasses.length === 0) {
        return (
            <div className="tl-canvas-wrap">
                <div className="tl-empty-state">
                    <span className="tl-empty-icon">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M3 12h4l3-9 4 18 3-9h4"/></svg>
                    </span>
                    <p>Select at least one motor imagery class to view curves</p>
                </div>
            </div>
        );
    }

    return (
        <div ref={containerRef} className="tl-canvas-wrap">
            <canvas
                ref={canvasRef}
                className="tl-canvas"
                onClick={handleClick}
                onMouseMove={channelMode === 'all_individual' ? handleMouseMove : undefined}
                onMouseLeave={channelMode === 'all_individual' ? handleMouseLeave : undefined}
            />
        </div>
    );
}
