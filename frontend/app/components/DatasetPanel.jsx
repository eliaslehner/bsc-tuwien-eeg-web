'use client';

import InfoPopup from './InfoPopup';

export default function DatasetPanel({
    eegData,
    selectedClasses,
    onClassToggle,
    selectedBand,
    onBandChange,
    heatmapEnabled,
    onHeatmapToggle,
    selectedRuns,
    setSelectedRuns,
    contrastMode,
    setContrastMode,
    contrastOrder,
    setContrastOrder,
    contrastPhenomenon,
    setContrastPhenomenon,
    erdThreshold,
    setErdThreshold,
    multiView,
    setMultiView,
}) {
    if (!eegData) {
        return (
            <aside className="dataset-panel">
                <p className="panel-loading">Loading dataset...</p>
            </aside>
        );
    }

    const { dataset } = eegData;
    const nRuns = dataset.n_runs || 6;
    const runs = Array.from({ length: nRuns }, (_, i) => i);
    const hasTrialRunIds = Object.keys(eegData.trial_run_ids || {}).length > 0;

    return (
        <aside className="dataset-panel">
            <div className="panel-section">
                <div className="panel-header">
                    <h2>Dataset Details</h2>
                    <InfoPopup text={dataset.description} />
                </div>
                <div className="detail-grid">
                    <span className="detail-label">Name</span>
                    <span className="detail-value">{dataset.name}</span>
                    <span className="detail-label">Subject</span>
                    <span className="detail-value">{dataset.subject}</span>
                    <span className="detail-label">Channels</span>
                    <span className="detail-value">{dataset.n_channels}</span>
                    <span className="detail-label">Sample Rate</span>
                    <span className="detail-value">{dataset.sfreq} Hz</span>
                </div>
            </div>

            <div className="panel-section">
                <div className="panel-header">
                    <h2>Runs</h2>
                    <InfoPopup text={hasTrialRunIds ? 'Select which recording runs to include in the average.' : 'Select which runs to include in the average. Older data exports split trials evenly across runs.'} />
                </div>
                <div className="run-selector">
                    {runs.map((run) => (
                        <button
                            key={run}
                            className={`run-btn ${selectedRuns.has(run) ? 'run-active' : ''}`}
                            onClick={() => {
                                const next = new Set(selectedRuns);
                                if (next.has(run)) next.delete(run); else next.add(run);
                                setSelectedRuns(next);
                            }}
                        >
                            R{run + 1}
                        </button>
                    ))}
                </div>
            </div>

            <div className="panel-section">
                <div className="panel-header">
                    <h2>Motor Imagery Classes</h2>
                    <InfoPopup text="Toggle motor imagery classes to filter the display. The brain heatmap shows averaged ERD/ERS for selected classes. Numbers indicate clean / total trials." />
                </div>
                <div className="class-filters">
                    {dataset.classes.map((cls) => (
                        <button
                            key={cls.id}
                            className={`class-btn ${selectedClasses.has(cls.id) ? 'class-active' : ''}`}
                            onClick={() => onClassToggle(cls.id)}
                        >
                            <span
                                className="class-indicator"
                                style={{ backgroundColor: cls.color }}
                            />
                            <span className="class-label">{cls.label}</span>
                            <span className="class-count">
                                {cls.n_clean}/{cls.n_trials}
                            </span>
                        </button>
                    ))}
                </div>
            </div>

            <div className="panel-section">
                <div className="panel-header">
                    <h2>Frequency Band</h2>
                    <InfoPopup text="Mu (8-13 Hz): sensorimotor rhythm, suppressed during motor imagery. Beta (13-30 Hz): also desynchronises during motor planning." />
                </div>
                <div className="band-selector">
                    {['mu', 'beta'].map((band) => (
                        <button
                            key={band}
                            className={`band-btn ${selectedBand === band ? 'band-active' : ''}`}
                            onClick={() => onBandChange(band)}
                        >
                            {band === 'mu' ? 'Mu (8-13 Hz)' : 'Beta (13-30 Hz)'}
                        </button>
                    ))}
                </div>
            </div>

            <div className="panel-section">
                <div className="panel-header">
                    <h2>ERD Threshold Slider</h2>
                    <InfoPopup text="Hide regions where the absolute ERD/ERS value falls below this percentage. Useful for suppressing noise." />
                </div>
                <div className="threshold-row">
                    <span className="threshold-bound">0%</span>
                    <input
                        type="range"
                        className="analysis-slider"
                        min="0" max="100" step="1"
                        value={erdThreshold}
                        onChange={(e) => setErdThreshold(parseInt(e.target.value, 10))}
                    />
                    <span className="threshold-bound">100%</span>
                </div>
                <input
                    type="number"
                    className="threshold-value"
                    min="0" max="100" step="1"
                    value={erdThreshold}
                    onChange={(e) => {
                        const v = parseInt(e.target.value, 10);
                        if (Number.isNaN(v)) { setErdThreshold(0); return; }
                        setErdThreshold(Math.max(0, Math.min(100, v)));
                    }}
                />
            </div>

            <div className="panel-section">
                <div className="panel-header">
                    <h2>Analysis Tool</h2>
                    <InfoPopup text="Use contrast mode to subtract the second selected class from the first." />
                </div>

                <button
                    className={`heatmap-toggle ${contrastMode ? 'heatmap-on' : ''}`}
                    onClick={() => setContrastMode(!contrastMode)}
                    disabled={selectedClasses.size !== 2}
                >
                    Contrast Mode {contrastMode ? 'ON' : 'OFF'}
                </button>
                {selectedClasses.size !== 2 && (
                    <span className="analysis-hint">Select exactly 2 classes</span>
                )}
                {contrastMode && contrastOrder[0] && contrastOrder[1] && (
                    <div className="contrast-order contrast-order-active">
                        <span className="contrast-order-label">
                            {dataset.classes.find(c => c.id === contrastOrder[0])?.label ?? contrastOrder[0]}
                        </span>
                        <span className="contrast-order-vs">vs</span>
                        <span className="contrast-order-label">
                            {dataset.classes.find(c => c.id === contrastOrder[1])?.label ?? contrastOrder[1]}
                        </span>
                    </div>
                )}
                {contrastMode && (
                    <div className="erd-ers-toggle" role="group" aria-label="Contrast phenomenon">
                        <button
                            className={contrastPhenomenon === 'erd' ? 'active' : ''}
                            onClick={() => setContrastPhenomenon('erd')}
                        >ERD</button>
                        <button
                            className={contrastPhenomenon === 'ers' ? 'active' : ''}
                            onClick={() => setContrastPhenomenon('ers')}
                        >ERS</button>
                    </div>
                )}
            </div>

            <div className="panel-section">
                <div className="panel-header">
                    <h2>3D Multi-View</h2>
                    <InfoPopup text="Splits the viewport into multiple synchronized angles of the brain (top, side, front) so you can inspect activity from several perspectives at once." />
                </div>
                <button
                    className={`heatmap-toggle ${multiView ? 'heatmap-on' : ''}`}
                    onClick={() => setMultiView(!multiView)}
                >
                    3D Multi-View {multiView ? 'ON' : 'OFF'}
                </button>
            </div>

            <div className="panel-section">
                <div className="panel-header">
                    <h2>Heatmap</h2>
                    <InfoPopup text="Overlays ERD/ERS activity onto the brain mesh as a red/blue diverging colormap. Red = synchronisation (ERS), blue = desynchronisation (ERD)." />
                </div>
                <button
                    className={`heatmap-toggle ${heatmapEnabled ? 'heatmap-on' : ''}`}
                    onClick={onHeatmapToggle}
                >
                    Heatmap {heatmapEnabled ? 'ON' : 'OFF'}
                </button>
            </div>
        </aside>
    );
}
