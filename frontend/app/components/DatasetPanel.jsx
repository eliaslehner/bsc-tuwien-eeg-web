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
