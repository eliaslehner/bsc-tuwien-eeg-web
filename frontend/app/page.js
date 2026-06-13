'use client';

import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
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
    
    const [selectedRuns, setSelectedRuns] = useState(new Set([0, 1, 2, 3, 4, 5]));
    const [contrastMode, setContrastMode] = useState(false);
    const [contrastOrder, setContrastOrder] = useState([null, null]);
    const [contrastPhenomenon, setContrastPhenomenon] = useState('erd'); // 'erd' | 'ers'
    const [erdThreshold, setErdThreshold] = useState(0);
    const [multiView, setMultiView] = useState(false);
    const [channelMode, setChannelMode] = useState('motor');
    // Midline electrodes (Fz, Cz, Pz, …) sit over the longitudinal fissure, so
    // their hemisphere is undetermined. When on, their value is applied to both
    // the left and right mirror regions (no arbitrary L/R bias). On by default.
    const [mirrorMidline, setMirrorMidline] = useState(true);

    useEffect(() => {
        fetch('/data/eeg_data.json')
            .then((r) => r.json())
            .then(setEegData)
            .catch(() => {});
    }, []);

    useEffect(() => {
        const nRuns = eegData?.dataset?.n_runs;
        if (!nRuns) return;
        setSelectedRuns(new Set(Array.from({ length: nRuns }, (_, i) => i)));
    }, [eegData?.dataset?.n_runs]);

    // On first load, place the playhead at a post-cue active moment (~1.0 s)
    // instead of t=-0.5 s (the baseline), where ERD/ERS is ~0 and the brain
    // overlay renders flat. The timeline axis still starts at -0.5 s; this only
    // moves the initial marker. Runs once, so it never overrides user scrubbing.
    const didInitTime = useRef(false);
    useEffect(() => {
        if (didInitTime.current) return;
        const times = eegData?.erd_ers?.[selectedBand]?.times;
        if (!times?.length) return;
        const target = 1.0; // seconds after cue
        let best = 0;
        for (let i = 1; i < times.length; i++) {
            if (Math.abs(times[i] - target) < Math.abs(times[best] - target)) best = i;
        }
        setCurrentTimeIndex(best);
        didInitTime.current = true;
    }, [eegData, selectedBand]);

    const handleRegionHover = useCallback(
        (name) => setActiveRegion(name),
        [],
    );
    const handleClassToggle = useCallback((className) => {
        setSelectedClasses((prev) => {
            const next = new Set(prev);
            if (next.has(className)) next.delete(className);
            else next.add(className);
            if (next.size !== 2) {
                setContrastMode(false);
                setContrastOrder([null, null]);
            } else {
                const arr = [...next];
                setContrastOrder((co) => {
                    if (co[0] && co[1] && next.has(co[0]) && next.has(co[1])) return co;
                    return arr;
                });
            }
            return next;
        });
    }, []);
    const handlePlayToggle = useCallback(() => setPlaying((p) => !p), []);
    const handleHeatmapToggle = useCallback(
        () => setHeatmapEnabled((h) => !h),
        [],
    );

    // Compute aggregated ERD/ERS data
    const activeData = useMemo(() => {
        if (!eegData || !eegData.erd_ers) return null;
        
        const n_runs = eegData.dataset?.n_runs ?? 6;
        const result = { ...eegData, erd_ers: { ...eegData.erd_ers } };

        // The exported per-trial values are band power normalised to the class
        // grand baseline (~1.0). We average the selected runs' trials and then
        // apply ONE baseline ratio (Pfurtscheller's ERD/ERS), so run selection
        // stays an exact ratio-of-means rather than a fragile mean-of-ratios.
        const baselineWindow = eegData.trial_timeline?.baseline ?? [-0.5, 0.0];

        for (const band of ['mu', 'beta']) {
            if (!eegData.erd_ers[band]) continue;

            const origClasses = eegData.erd_ers[band];
            const avgClasses = {};

            // Time bins inside the pre-cue baseline window.
            const times = origClasses.times || [];
            const baselineBins = [];
            for (let t = 0; t < times.length; t++) {
                if (times[t] >= baselineWindow[0] && times[t] < baselineWindow[1]) {
                    baselineBins.push(t);
                }
            }

            for (const cn in origClasses) {
                if (cn === 'times' || cn === 'range') continue;

                const trialsData = origClasses[cn]; // [n_trials, n_ch, n_times] norm. power
                if (!trialsData || !trialsData.length) continue;

                const n_trials = trialsData.length;
                const trials_per_run = Math.ceil(n_trials / n_runs);
                const trialRunIds = eegData.trial_run_ids?.[cn];
                const hasTrialRunIds = Array.isArray(trialRunIds)
                    && trialRunIds.length >= n_trials;

                const n_ch = trialsData[0].length;
                const n_times = trialsData[0][0].length;

                // Sum normalised power across the selected runs' trials.
                let sum = Array(n_ch).fill(0).map(() => Array(n_times).fill(0));
                let count = 0;

                for (let i = 0; i < n_trials; i++) {
                    const run_idx = hasTrialRunIds
                        ? trialRunIds[i]
                        : Math.floor(i / trials_per_run);
                    if (selectedRuns.has(run_idx)) {
                        for (let c = 0; c < n_ch; c++) {
                            for (let t = 0; t < n_times; t++) {
                                sum[c][t] += trialsData[i][c][t];
                            }
                        }
                        count++;
                    }
                }

                // ERD/ERS = (meanPower - baseline) / baseline * 100. The trial
                // count cancels, so we can work directly on the running totals.
                if (count > 0) {
                    for (let c = 0; c < n_ch; c++) {
                        let baseline = 0;
                        for (const t of baselineBins) baseline += sum[c][t];
                        baseline = baselineBins.length ? baseline / baselineBins.length : 0;
                        if (baseline > 0) {
                            for (let t = 0; t < n_times; t++) {
                                sum[c][t] = (sum[c][t] - baseline) / baseline * 100;
                            }
                        } else {
                            for (let t = 0; t < n_times; t++) sum[c][t] = 0;
                        }
                    }
                }
                avgClasses[cn] = sum;
            }

            result.erd_ers[band] = {
                ...origClasses,
                ...avgClasses
            };
        }
        return result;
    }, [eegData, selectedRuns]);

    return (
        <main className="app">
            <header className="header">
                <h1>Brain Viewer</h1>
                {activeRegion && (
                    <span className="header-region">
                        Region: <strong>{activeRegion}</strong>
                    </span>
                )}
                <div className="header-actions">
                    <button
                        className={`mirror-btn${mirrorMidline ? ' active' : ''}`}
                        onClick={() => setMirrorMidline((m) => !m)}
                        aria-pressed={mirrorMidline}
                        title="Mirror midline electrodes (Fz, FCz, Cz, CPz, Pz, POz) onto both hemispheres. Their true side is undetermined, so their value is applied to the left and right mirror regions equally."
                    >
                        <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                            <path d="M8 1.5v13" stroke="currentColor" strokeWidth="1.3" strokeDasharray="2 1.6" strokeLinecap="round"/>
                            <path d="M5 5.5 2 8l3 2.5M11 5.5l3 2.5-3 2.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                        <span>Mirror</span>
                    </button>
                    <button className="help-btn" onClick={() => document.getElementById('help-modal').showModal()} title="Help / Theory">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                            <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5"/>
                            <path d="M6 6a2 2 0 1 1 2.5 1.94c-.39.13-.5.44-.5.81V10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                            <circle cx="8" cy="12" r="0.75" fill="currentColor"/>
                        </svg>
                    </button>
                </div>
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
                    selectedRuns={selectedRuns}
                    setSelectedRuns={setSelectedRuns}
                    contrastMode={contrastMode}
                    setContrastMode={setContrastMode}
                    contrastOrder={contrastOrder}
                    setContrastOrder={setContrastOrder}
                    contrastPhenomenon={contrastPhenomenon}
                    setContrastPhenomenon={setContrastPhenomenon}
                    erdThreshold={erdThreshold}
                    setErdThreshold={setErdThreshold}
                    multiView={multiView}
                    setMultiView={setMultiView}
                />
                <BrainViewer
                    onRegionHover={handleRegionHover}
                    eegData={activeData}
                    selectedClasses={selectedClasses}
                    selectedBand={selectedBand}
                    currentTimeIndex={currentTimeIndex}
                    heatmapEnabled={heatmapEnabled}
                    contrastMode={contrastMode}
                    contrastOrder={contrastOrder}
                    contrastPhenomenon={contrastPhenomenon}
                    erdThreshold={erdThreshold}
                    multiView={multiView}
                    channelMode={channelMode}
                    mirrorMidline={mirrorMidline}
                />
            </div>

            <Timeline
                eegData={activeData}
                selectedClasses={selectedClasses}
                selectedBand={selectedBand}
                currentTimeIndex={currentTimeIndex}
                onTimeChange={setCurrentTimeIndex}
                playing={playing}
                onPlayToggle={handlePlayToggle}
                contrastMode={contrastMode}
                contrastOrder={contrastOrder}
                channelMode={channelMode}
                setChannelMode={setChannelMode}
            />
            
            <dialog id="help-modal" className="help-modal" onClick={(e) => { if (e.target.id === 'help-modal') e.target.close(); }}>
                <div className="help-modal-inner">
                    <div className="help-modal-header">
                        <h2>Motor Imagery BCI Theory</h2>
                        <button className="help-close-btn" onClick={() => document.getElementById('help-modal').close()}>
                            <svg width="14" height="14" viewBox="0 0 14 14"><path d="M1 1l12 12M13 1L1 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/></svg>
                        </button>
                    </div>
                    <div className="help-modal-body">
                        <div className="help-card">
                            <h3>Event-Related Desynchronization (ERD)</h3>
                            <p>
                                When you imagine a movement (like moving your left hand), the motor cortex responsible for that movement becomes
                                active. Counter-intuitively, this causes a <em>decrease</em> in the amplitude of brainwaves in the Mu (8–13 Hz)
                                and Beta (13–30 Hz) bands. This drop in power is called ERD.
                            </p>
                        </div>
                        <div className="help-card">
                            <h3>Contralateral Control</h3>
                            <p>
                                The brain&apos;s motor control is crossed (contralateral). Imagining moving your <strong>left hand</strong>
                                will show an ERD (suppression of Mu/Beta rhythm) in the <strong>right motor cortex</strong>, and vice versa.
                            </p>
                        </div>
                        <div className="help-divider" />
                        <h3>How to Use</h3>
                        <ul className="help-list">
                            <li><strong>Runs</strong> — Select which recording blocks to include in the average.</li>
                            <li><strong>Classes</strong> — Toggle left hand, right hand, feet, or tongue imagery.</li>
                            <li><strong>Contrast</strong> — Select exactly 2 classes to compute (Class 1) − (Class 2) subtraction.</li>
                            <li><strong>Threshold</strong> — Hide low-level noise to isolate active cortical areas.</li>
                            <li><strong>Multi-View</strong> — Split into Left Hemisphere, Top, and Right Hemisphere views.</li>
                            <li><strong>Mirror</strong> — Midline electrodes (Fz, Cz, Pz…) sit over the fissure and overlie both hemispheres; their value is applied to the left and right mirror regions equally instead of an arbitrary side.</li>
                        </ul>
                    </div>
                </div>
            </dialog>
        </main>
    );
}
