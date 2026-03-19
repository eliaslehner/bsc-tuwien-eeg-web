'use client';

import { useState, useCallback, useEffect } from 'react';
import BrainViewer from './components/BrainViewer';
import DatasetPanel from './components/DatasetPanel';
import Timeline from './components/Timeline';

export default function Home() {
    const [eegData, setEegData] = useState(null);
    const [selectedClasses, setSelectedClasses] = useState(
        new Set(['left_hand', 'right_hand', 'feet', 'tongue']),
    );
    const [selectedBand, setSelectedBand] = useState('mu');
    const [currentTimeIndex, setCurrentTimeIndex] = useState(0);
    const [playing, setPlaying] = useState(false);
    const [activeRegion, setActiveRegion] = useState(null);
    const [heatmapEnabled, setHeatmapEnabled] = useState(true);

    useEffect(() => {
        fetch('/data/eeg_data.json')
            .then((r) => r.json())
            .then(setEegData)
            .catch(() => {});
    }, []);

    const handleRegionHover = useCallback(
        (name) => setActiveRegion(name),
        [],
    );
    const handleClassToggle = useCallback((className) => {
        setSelectedClasses((prev) => {
            const next = new Set(prev);
            if (next.has(className)) next.delete(className);
            else next.add(className);
            return next;
        });
    }, []);
    const handlePlayToggle = useCallback(() => setPlaying((p) => !p), []);
    const handleHeatmapToggle = useCallback(
        () => setHeatmapEnabled((h) => !h),
        [],
    );

    return (
        <main className="app">
            <header className="header">
                <h1>Brain Viewer</h1>
                {activeRegion && (
                    <span className="header-region">
                        Region: <strong>{activeRegion}</strong>
                    </span>
                )}
            </header>

            <div className="content">
                <DatasetPanel
                    eegData={eegData}
                    selectedClasses={selectedClasses}
                    onClassToggle={handleClassToggle}
                    selectedBand={selectedBand}
                    onBandChange={setSelectedBand}
                    heatmapEnabled={heatmapEnabled}
                    onHeatmapToggle={handleHeatmapToggle}
                />
                <BrainViewer
                    onRegionHover={handleRegionHover}
                    eegData={eegData}
                    selectedClasses={selectedClasses}
                    selectedBand={selectedBand}
                    currentTimeIndex={currentTimeIndex}
                    heatmapEnabled={heatmapEnabled}
                />
            </div>

            <Timeline
                eegData={eegData}
                selectedClasses={selectedClasses}
                currentTimeIndex={currentTimeIndex}
                onTimeChange={setCurrentTimeIndex}
                playing={playing}
                onPlayToggle={handlePlayToggle}
            />
        </main>
    );
}
