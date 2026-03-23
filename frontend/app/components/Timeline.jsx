'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import TimelineCurves from './TimelineCurves';
import TimelineHeatmap from './TimelineHeatmap';
import InfoPopup from './InfoPopup';

function detectRuns(events) {
    if (!events || events.length < 2) return [events || []];
    const sorted = [...events].sort((a, b) => a.time - b.time);
    const gaps = [];
    for (let i = 1; i < sorted.length; i++)
        gaps.push(sorted[i].time - sorted[i - 1].time);
    const median = [...gaps].sort((a, b) => a - b)[Math.floor(gaps.length / 2)];
    const threshold = median * 2.5;
    const runs = [];
    let start = 0;
    for (let i = 1; i < sorted.length; i++) {
        if (sorted[i].time - sorted[i - 1].time > threshold) {
            runs.push(sorted.slice(start, i));
            start = i;
        }
    }
    runs.push(sorted.slice(start));
    return runs;
}

const SPEED_OPTIONS = [
    { label: '0.5x', ms: 160 },
    { label: '1x', ms: 80 },
    { label: '2x', ms: 40 },
    { label: '4x', ms: 20 },
];

export default function Timeline({
    eegData,
    selectedClasses,
    selectedBand,
    currentTimeIndex,
    onTimeChange,
    playing,
    onPlayToggle,
}) {
    const [viewMode, setViewMode] = useState('curves');
    const [channelMode, setChannelMode] = useState('motor');
    const [stacked, setStacked] = useState(true);
    const [speedIdx, setSpeedIdx] = useState(1);

    const intervalRef = useRef(null);
    const indexRef = useRef(currentTimeIndex);
    indexRef.current = currentTimeIndex;

    const times = eegData?.erd_ers?.[selectedBand]?.times || [];
    const nTimes = times.length;
    const channels = eegData?.dataset?.channels || [];

    useEffect(() => {
        if (playing && nTimes > 0) {
            intervalRef.current = setInterval(() => {
                const next = (indexRef.current + 1) % nTimes;
                onTimeChange(next);
            }, SPEED_OPTIONS[speedIdx].ms);
        }
        return () => clearInterval(intervalRef.current);
    }, [playing, nTimes, onTimeChange, speedIdx]);

    const currentTime = times[currentTimeIndex] ?? 0;
    const tmin = times[0] ?? -0.5;
    const tmax = times[nTimes - 1] ?? 4.0;

    const runs = useMemo(() => detectRuns(eegData?.events), [eegData?.events]);
    const classColorMap = useMemo(() => {
        const map = {};
        for (const cls of eegData?.dataset?.classes || []) map[cls.id] = cls.color;
        return map;
    }, [eegData?.dataset?.classes]);

    const handleStep = useCallback(
        (dir) => {
            if (!nTimes) return;
            onTimeChange(Math.max(0, Math.min(nTimes - 1, currentTimeIndex + dir)));
        },
        [currentTimeIndex, nTimes, onTimeChange],
    );

    if (!eegData) {
        return (
            <div className="timeline">
                <div className="tl-empty">Loading EEG data...</div>
            </div>
        );
    }

    return (
        <div className="timeline">
            <div className="tl-toolbar">
                <div className="tl-playback">
                    <button
                        className="tl-btn tl-play-btn"
                        onClick={onPlayToggle}
                        title={playing ? 'Pause' : 'Play'}
                    >
                        {playing ? (
                            <span className="pause-icon" />
                        ) : (
                            <span className="play-icon" />
                        )}
                    </button>
                    <button
                        className="tl-btn"
                        onClick={() => handleStep(-1)}
                        title="Previous frame"
                    >
                        <svg width="10" height="10" viewBox="0 0 10 10">
                            <path
                                d="M8 1L3 5l5 4V1zM2 1v8"
                                stroke="currentColor"
                                fill="none"
                                strokeWidth="1.5"
                            />
                        </svg>
                    </button>
                    <button
                        className="tl-btn"
                        onClick={() => handleStep(1)}
                        title="Next frame"
                    >
                        <svg width="10" height="10" viewBox="0 0 10 10">
                            <path
                                d="M2 1l5 4-5 4V1zM8 1v8"
                                stroke="currentColor"
                                fill="none"
                                strokeWidth="1.5"
                            />
                        </svg>
                    </button>
                    <button
                        className="tl-btn tl-speed-btn"
                        onClick={() =>
                            setSpeedIdx((i) => (i + 1) % SPEED_OPTIONS.length)
                        }
                        title="Playback speed"
                    >
                        {SPEED_OPTIONS[speedIdx].label}
                    </button>
                </div>

                <div className="tl-tabs">
                    {['curves', 'heatmap', 'session'].map((mode) => (
                        <button
                            key={mode}
                            className={`tl-tab ${viewMode === mode ? 'tl-tab-active' : ''}`}
                            onClick={() => setViewMode(mode)}
                        >
                            {mode.charAt(0).toUpperCase() + mode.slice(1)}
                        </button>
                    ))}
                </div>

                <div className="tl-options">
                    {viewMode === 'curves' && (
                        <>
                            <select
                                className="tl-select"
                                value={channelMode}
                                onChange={(e) => setChannelMode(e.target.value)}
                            >
                                <option value="motor">Motor (C3, Cz, C4)</option>
                                <option value="all">All channels (avg)</option>
                                {channels.map((ch) => (
                                    <option key={ch} value={ch}>
                                        {ch}
                                    </option>
                                ))}
                            </select>
                            <button
                                className={`tl-btn tl-layout-btn ${stacked ? 'tl-btn-active' : ''}`}
                                onClick={() => setStacked(!stacked)}
                                title={
                                    stacked
                                        ? 'Switch to overlay'
                                        : 'Switch to stacked'
                                }
                            >
                                {stacked ? 'Stacked' : 'Overlay'}
                            </button>
                        </>
                    )}
                </div>

                <div className="tl-time-display">
                    <span className="tl-time">{currentTime.toFixed(2)}s</span>
                    <InfoPopup text="Curves: ERD/ERS time courses per motor imagery class. Heatmap: channel x time activation matrix. Session: trial structure across runs. Click canvas to jump to a time point." />
                </div>
            </div>

            <div className="tl-content">
                {viewMode === 'curves' && (
                    <TimelineCurves
                        eegData={eegData}
                        selectedClasses={selectedClasses}
                        selectedBand={selectedBand}
                        currentTimeIndex={currentTimeIndex}
                        onTimeChange={onTimeChange}
                        channelMode={channelMode}
                        stacked={stacked}
                    />
                )}
                {viewMode === 'heatmap' && (
                    <TimelineHeatmap
                        eegData={eegData}
                        selectedClasses={selectedClasses}
                        selectedBand={selectedBand}
                        currentTimeIndex={currentTimeIndex}
                        onTimeChange={onTimeChange}
                    />
                )}
                {viewMode === 'session' && (
                    <div className="tl-session">
                        <p className="tl-session-note">
                            ERD/ERS data is averaged across all runs. Run-level
                            filtering requires per-run export from the backend.
                        </p>
                        {runs.map((run, ri) => (
                            <div key={ri} className="tl-run">
                                <div className="tl-run-header">
                                    <span className="tl-run-label">
                                        Run {ri + 1}
                                    </span>
                                    <span className="tl-run-count">
                                        {run.length} trials
                                    </span>
                                </div>
                                <div className="tl-run-trials">
                                    {run.map((evt, ei) => (
                                        <div
                                            key={ei}
                                            className={`tl-trial ${selectedClasses.has(evt.class) ? '' : 'tl-trial-dim'}`}
                                            style={{
                                                backgroundColor:
                                                    classColorMap[evt.class] ||
                                                    '#444',
                                            }}
                                            title={`${evt.class} @ ${evt.time.toFixed(1)}s`}
                                        />
                                    ))}
                                </div>
                                <div className="tl-run-stats">
                                    {eegData.dataset.classes.map((cls) => {
                                        const count = run.filter(
                                            (e) => e.class === cls.id,
                                        ).length;
                                        return count > 0 ? (
                                            <span
                                                key={cls.id}
                                                className="tl-run-stat"
                                                style={{ color: cls.color }}
                                            >
                                                {count}
                                            </span>
                                        ) : null;
                                    })}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <div className="tl-slider-row">
                <span className="tl-slider-label">{tmin.toFixed(1)}s</span>
                <div className="tl-slider-wrap">
                    <input
                        type="range"
                        className="tl-slider"
                        min={0}
                        max={Math.max(0, nTimes - 1)}
                        value={currentTimeIndex}
                        onChange={(e) => onTimeChange(Number(e.target.value))}
                    />
                </div>
                <span className="tl-slider-label">{tmax.toFixed(1)}s</span>
            </div>
        </div>
    );
}
