'use client';

import { useState, useCallback } from 'react';
import BrainViewer from './components/BrainViewer';
import ElectrodeSidebar from './components/ElectrodeSidebar';

export default function Home() {
  const [activeRegion, setActiveRegion] = useState(null);
  const [sidebarRegion, setSidebarRegion] = useState(null);

  // Stable callbacks to avoid unnecessary re-renders
  const handleRegionHover = useCallback((name) => setActiveRegion(name), []);
  const handleSidebarHover = useCallback((name) => setSidebarRegion(name), []);

  // Show whichever source is active — sidebar hover takes priority
  const displayedRegion = sidebarRegion || activeRegion;

  return (
    <main className="app">
      <header className="header">
        <h1>Brain Viewer</h1>
        {displayedRegion && (
          <span className="header-region">
            Region: <strong>{displayedRegion}</strong>
          </span>
        )}
      </header>
      <div className="content">
        <BrainViewer
          onRegionHover={handleRegionHover}
          highlightRegion={sidebarRegion}
        />
        <ElectrodeSidebar
          activeRegion={displayedRegion}
          onSidebarHover={handleSidebarHover}
        />
      </div>
    </main>
  );
}
