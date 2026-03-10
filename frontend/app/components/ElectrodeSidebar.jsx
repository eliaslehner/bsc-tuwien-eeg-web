'use client';

import { useEffect, useState } from 'react';

/**
 * ElectrodeSidebar — Lists electrodes grouped by brain region.
 *
 * Props:
 *   activeRegion — currently hovered region name on the brain (highlights it)
 *   onSidebarHover(regionName | null) — called when user hovers a region/electrode
 */
export default function ElectrodeSidebar({ activeRegion, onSidebarHover }) {
    const [data, setData] = useState(null);

    useEffect(() => {
        fetch('/data/region_metadata.json')
            .then((r) => r.json())
            .then(setData);
    }, []);

    if (!data) return <aside className="sidebar"><p>Loading…</p></aside>;

    // Build grouped structure: { regionName: [electrode names] }
    const grouped = {};
    for (const electrode of data.electrodes) {
        const rn = electrode.region_name;
        if (!grouped[rn]) grouped[rn] = [];
        grouped[rn].push(electrode.name);
    }

    const sortedRegions = Object.keys(grouped).sort();

    const isActive = (regionName) =>
        activeRegion === regionName || false;

    return (
        <aside className="sidebar">
            <h2>Electrode Mapping</h2>
            <p className="sidebar-subtitle">
                {data.electrodes.length} electrodes · {data.atlas}
            </p>
            <div className="sidebar-list">
                {sortedRegions.map((regionName) => (
                    <div
                        key={regionName}
                        className={`region-group ${isActive(regionName) ? 'region-active' : ''
                            }`}
                        onMouseEnter={() => onSidebarHover && onSidebarHover(regionName)}
                        onMouseLeave={() => onSidebarHover && onSidebarHover(null)}
                    >
                        <div className="region-name">{regionName}</div>
                        <div className="electrode-chips">
                            {grouped[regionName].map((ch) => (
                                <span
                                    key={ch}
                                    className="electrode-chip"
                                    onMouseEnter={(e) => {
                                        e.stopPropagation();
                                        onSidebarHover && onSidebarHover(regionName);
                                    }}
                                >
                                    {ch}
                                </span>
                            ))}
                        </div>
                    </div>
                ))}
            </div>
        </aside>
    );
}
