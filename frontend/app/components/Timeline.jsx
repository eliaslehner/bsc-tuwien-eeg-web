'use client';

import { useEffect, useRef, useCallback } from 'react';
import InfoPopup from './InfoPopup';

export default function Timeline({
    eegData,
    selectedClasses,
    currentTimeIndex,
    onTimeChange,
    playing,
    onPlayToggle,
}) {
    const intervalRef = useRef(null);
    const indexRef = useRef(currentTimeIndex);
    indexRef.current = currentTimeIndex;

    const times = eegData?.erd_ers?.mu?.times || [];
    const nTimes = times.length;

    const classColorMap = {};
    if (eegData?.dataset?.classes) {
        for (const cls of eegData.dataset.classes) {
            classColorMap[cls.id] = cls.color;
        }
    }

    // Auto-play
    useEffect(() => {
        if (playing && nTimes > 0) {
            intervalRef.current = setInterval(() => {
                const next = (indexRef.current + 1) % nTimes;
                onTimeChange(next);
            }, 80);
        }
        return () => clearInterval(intervalRef.current);
    }, [playing, nTimes, onTimeChange]);

    const currentTime = times[currentTimeIndex] ?? 0;
    const tmin = times[0] ?? -0.5;
    const tmax = times[nTimes - 1] ?? 4.0;
    const range = tmax - tmin || 1;
    const cuePercent = ((0 - tmin) / range) * 100;

    // Session events filtered by selected classes
    const sessionEvents = (eegData?.events || []).filter(
        (e) => selectedClasses.has(e.class)
    );
    const sessionDuration = eegData?.dataset?.duration || 1;

    return (
        <div className="timeline">
            <div className="timeline-controls">
                <button
                    className="play-btn"
                    onClick={onPlayToggle}
                    title={playing ? 'Pause' : 'Play'}
                >
                    {playing ? (
                        <span className="pause-icon" />
                    ) : (
                        <span className="play-icon" />
                    )}
                </button>

                <div className="timeline-tracks">
                    {/* Session events overview */}
                    <div className="session-bar">
                        <span className="track-label">Session</span>
                        <div className="session-track">
                            {sessionEvents.map((evt, i) => (
                                <div
                                    key={i}
                                    className="event-tick"
                                    style={{
                                        left: `${(evt.time / sessionDuration) * 100}%`,
                                        backgroundColor:
                                            classColorMap[evt.class] || '#666',
                                    }}
                                />
                            ))}
                        </div>
                    </div>

                    {/* Epoch time scrubber */}
                    <div className="epoch-bar">
                        <span className="track-label">Trial</span>
                        <div className="epoch-track">
                            <div
                                className="epoch-region epoch-baseline"
                                style={{
                                    left: '0%',
                                    width: `${cuePercent}%`,
                                }}
                            />
                            <div
                                className="epoch-cue-line"
                                style={{ left: `${cuePercent}%` }}
                            />
                            <input
                                type="range"
                                className="epoch-slider"
                                min={0}
                                max={Math.max(0, nTimes - 1)}
                                value={currentTimeIndex}
                                onChange={(e) =>
                                    onTimeChange(Number(e.target.value))
                                }
                            />
                        </div>
                        <div className="epoch-labels">
                            <span>{tmin.toFixed(1)}s</span>
                            <span className="epoch-cue-label">cue</span>
                            <span>{tmax.toFixed(1)}s</span>
                        </div>
                    </div>
                </div>

                <div className="timeline-info">
                    <span className="timeline-time">
                        {currentTime.toFixed(2)}s
                    </span>
                    <InfoPopup text="Averaged trial epoch. Drag the slider to select a time point. The brain heatmap shows ERD/ERS activity at the selected time. Dark region marks the baseline period." />
                </div>
            </div>
        </div>
    );
}
