'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import TimelineCurves from './TimelineCurves';
import TimelineHeatmap from './TimelineHeatmap';
import InfoPopup from './InfoPopup';

const ZOOM_LEVELS = [1, 2, 4, 8];

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
    contrastMode,
    contrastOrder,
}) {
    const [viewMode, setViewMode] = useState('curves');
    const [channelMode, setChannelMode] = useState('motor');
    const [stacked, setStacked] = useState(true);
    const [speedIdx, setSpeedIdx] = useState(1);
    const [zoomLevel, setZoomLevel] = useState(0);

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

    useEffect(() => {
        if (channelMode === 'all_individual' && selectedClasses.size !== 1) {
            setChannelMode('motor');
        }
    }, [selectedClasses.size, channelMode]);

    const currentTime = times[currentTimeIndex] ?? 0;
    const tmin = times[0] ?? -0.5;
    const tmax = times[nTimes - 1] ?? 4.0;

    const handleStep = useCallback(
        (dir) => {
            if (!nTimes) return;
            onTimeChange(Math.max(0, Math.min(nTimes - 1, currentTimeIndex + dir)));
        },
        [currentTimeIndex, nTimes, onTimeChange],
    );

    const zoomFactor = ZOOM_LEVELS[zoomLevel];
    const visibleRange = (() => {
        if (zoomLevel === 0 || nTimes === 0) return { start: 0, end: nTimes - 1 };
        const windowSize = Math.max(2, Math.floor(nTimes / zoomFactor));
        const half = Math.floor(windowSize / 2);
        let start = currentTimeIndex - half;
        let end = start + windowSize - 1;
        if (start < 0) { end -= start; start = 0; }
        if (end >= nTimes) { start -= (end - nTimes + 1); end = nTimes - 1; start = Math.max(0, start); }
        return { start, end };
    })();

    const handleZoomIn = useCallback(() => {
        setZoomLevel((z) => Math.min(z + 1, ZOOM_LEVELS.length - 1));
    }, []);
    const handleZoomOut = useCallback(() => {
        setZoomLevel((z) => Math.max(z - 1, 0));
    }, []);
    const handleWheel = useCallback((e) => {
        e.preventDefault();
        if (e.deltaY < 0) setZoomLevel((z) => Math.min(z + 1, ZOOM_LEVELS.length - 1));
        else setZoomLevel((z) => Math.max(z - 1, 0));
    }, []);

    const contentRef = useRef(null);
    useEffect(() => {
        const el = contentRef.current;
        if (!el) return;
        el.addEventListener('wheel', handleWheel, { passive: false });
        return () => el.removeEventListener('wheel', handleWheel);
    }, [handleWheel]);

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
                    {['curves', 'heatmap'].map((mode) => (
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
                                <option 
                                    value="all_individual" 
                                    disabled={selectedClasses.size !== 1}
                                >
                                    All channels (individual lines)*
                                </option>
                                {channels.map((ch) => (
                                    <option key={ch} value={ch}>
                                        {ch}
                                    </option>
                                ))}
                            </select>
                            {selectedClasses.size !== 1 && channelMode === 'all_individual' && (
                                <span style={{fontSize: '10px', color: '#ff4444', marginLeft: '8px'}}>*Requires exactly 1 class</span>
                            )}
                            <button
                                className={`tl-btn tl-layout-btn ${stacked ? 'tl-btn-active' : ''}`}
                                onClick={() => setStacked(!stacked)}
                                disabled={selectedClasses.size <= 1}
                                title={
                                    selectedClasses.size <= 1
                                        ? 'Select multiple classes to switch layout'
                                        : stacked
                                            ? 'Switch to overlay'
                                            : 'Switch to stacked'
                                }
                            >
                                {stacked ? 'Stacked' : 'Overlay'}
                            </button>
                        </>
                    )}
                </div>

                <div className="tl-zoom-controls">
                    <button className="tl-btn" onClick={handleZoomOut} disabled={zoomLevel === 0} title="Zoom out">
                        <svg width="10" height="10" viewBox="0 0 10 10"><path d="M2 5h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                    </button>
                    <span className="tl-zoom-label">{zoomFactor === 1 ? 'Fit' : `${zoomFactor}x`}</span>
                    <button className="tl-btn" onClick={handleZoomIn} disabled={zoomLevel === ZOOM_LEVELS.length - 1} title="Zoom in">
                        <svg width="10" height="10" viewBox="0 0 10 10"><path d="M5 2v6M2 5h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                    </button>
                </div>

                <div className="tl-time-display">
                    <span className="tl-time">{currentTime.toFixed(2)}s</span>
                    <InfoPopup text="Curves: ERD/ERS time courses per motor imagery class. Heatmap: channel x time activation matrix. Scroll to zoom. Click canvas to jump to a time point." />
                </div>
            </div>

            <div className="tl-content" ref={contentRef}>
                {viewMode === 'curves' && (
                    <TimelineCurves
                        eegData={eegData}
                        selectedClasses={selectedClasses}
                        selectedBand={selectedBand}
                        currentTimeIndex={currentTimeIndex}
                        onTimeChange={onTimeChange}
                        channelMode={channelMode}
                        stacked={stacked}
                        visibleRange={visibleRange}
                        contrastMode={contrastMode}
                        contrastOrder={contrastOrder}
                    />
                )}
                {viewMode === 'heatmap' && (
                    <TimelineHeatmap
                        eegData={eegData}
                        selectedClasses={selectedClasses}
                        selectedBand={selectedBand}
                        currentTimeIndex={currentTimeIndex}
                        onTimeChange={onTimeChange}
                        visibleRange={visibleRange}
                    />
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
