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
                    <InfoPopup text="Select which runs to include in the average. (Assumes 6 runs total)" />
                </div>
                <div className="run-selector">
                    {[0, 1, 2, 3, 4, 5].map((run) => (
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
                    <h2>Analysis Tools</h2>
                    <InfoPopup text="Use contrast mode to subtract the second selected class from the first. Adjust threshold to hide noise." />
                </div>
                
                <div style={{ marginBottom: '10px' }}>
                    <label className={`analysis-check ${selectedClasses.size !== 2 ? 'analysis-check-disabled' : ''}`}>
                        <input
                            type="checkbox"
                            checked={contrastMode}
                            onChange={(e) => setContrastMode(e.target.checked)}
                            disabled={selectedClasses.size !== 2}
                        />
                        Contrast Mode
                    </label>
                    {selectedClasses.size !== 2 && (
                        <span className="analysis-hint">Select exactly 2 classes</span>
                    )}
                    {contrastMode && contrastOrder[0] && contrastOrder[1] && (
                        <div className="contrast-order">
                            <span className="contrast-order-label">
                                {dataset.classes.find(c => c.id === contrastOrder[0])?.label ?? contrastOrder[0]}
                            </span>
                            <span className="contrast-order-minus">−</span>
                            <span className="contrast-order-label">
                                {dataset.classes.find(c => c.id === contrastOrder[1])?.label ?? contrastOrder[1]}
                            </span>
                            <button
                                className="contrast-swap-btn"
                                onClick={() => setContrastOrder([contrastOrder[1], contrastOrder[0]])}
                                title="Swap subtraction order"
                            >
                                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                                    <path d="M3 2l-2 2 2 2"/>
                                    <path d="M9 6l2 2-2 2"/>
                                    <path d="M1 4h10M1 8h10"/>
                                </svg>
                            </button>
                        </div>
                    )}
                </div>

                <div className="analysis-field">
                    <label className="analysis-slider-label">
                        ERD Drop Threshold: {erdThreshold}%
                    </label>
                    <input
                        type="range"
                        className="analysis-slider"
                        min="0" max="50" step="1"
                        value={erdThreshold}
                        onChange={(e) => setErdThreshold(parseInt(e.target.value, 10))}
                    />
                </div>

                <div className="analysis-field">
                    <label className="analysis-check">
                        <input
                            type="checkbox"
                            checked={multiView}
                            onChange={(e) => setMultiView(e.target.checked)}
                        />
                        Split 3D Multi-View
                    </label>
                </div>
            </div>

            <div className="panel-section">
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
