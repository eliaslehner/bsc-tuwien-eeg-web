'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { SSAOPass } from 'three/examples/jsm/postprocessing/SSAOPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { activeChannelsFor } from '../lib/eeg';

/**
 * Compute per-vertex heatmap colours from ERD/ERS data.
 *
 * Maps channel-level band power to brain regions via the electrode-region
 * mapping, then colours each vertex by its region's value using a diverging
 * blue (ERD) - grey - red (ERS) colour scale.
 */
function computeRegionAveragesAtTime(
    eegData, selectedClasses, selectedBand, timeIndex, contrastMode, contrastOrder, channelMode,
) {
    const bandData = eegData?.erd_ers?.[selectedBand];
    if (!bandData) return null;

    const channels = eegData.dataset.channels;
    const channelRegions = eegData.channel_regions;
    const activeClasses = [...selectedClasses].filter((c) => bandData[c]);
    if (activeClasses.length === 0) return null;

    const activeChannelSet = new Set(activeChannelsFor(channelMode || 'all', channels));

    // Per-channel value computation
    const channelValues = {};
    for (let i = 0; i < channels.length; i++) {
        if (!activeChannelSet.has(channels[i])) continue;
        if (contrastMode && activeClasses.length === 2) {
            const c1 = contrastOrder?.[0] || activeClasses[0];
            const c2 = contrastOrder?.[1] || activeClasses[1];
            const v1 = bandData[c1]?.[i]?.[timeIndex] ?? 0;
            const v2 = bandData[c2]?.[i]?.[timeIndex] ?? 0;
            channelValues[channels[i]] = v1 - v2;
        } else {
            let sum = 0;
            let count = 0;
            for (const cls of activeClasses) {
                const cd = bandData[cls];
                if (cd?.[i]) {
                    sum += cd[i][timeIndex] ?? 0;
                    count++;
                }
            }
            if (count > 0) channelValues[channels[i]] = sum / count;
        }
    }

    // Map channels to regions
    const regionBuckets = {};
    for (const [ch, value] of Object.entries(channelValues)) {
        const region = channelRegions?.[ch];
        if (region) {
            const rid = region.region_id;
            if (!regionBuckets[rid]) regionBuckets[rid] = [];
            regionBuckets[rid].push(value);
        }
    }

    const regionAvg = {};
    for (const [rid, vals] of Object.entries(regionBuckets)) {
        regionAvg[rid] = vals.reduce((a, b) => a + b, 0) / vals.length;
    }

    return regionAvg;
}

function computeHeatmapMaxAbs(
    eegData, selectedClasses, selectedBand, contrastMode, contrastOrder, channelMode,
) {
    const bandData = eegData?.erd_ers?.[selectedBand];
    const times = bandData?.times || [];
    if (!bandData || times.length === 0) return 1;

    let maxAbs = 1;
    for (let timeIndex = 0; timeIndex < times.length; timeIndex++) {
        const regionAvg = computeRegionAveragesAtTime(
            eegData,
            selectedClasses,
            selectedBand,
            timeIndex,
            contrastMode,
            contrastOrder,
            channelMode,
        );
        if (!regionAvg) continue;

        for (const value of Object.values(regionAvg)) {
            maxAbs = Math.max(maxAbs, Math.abs(value));
        }
    }

    return maxAbs;
}

function computeHeatmapColors(
    vertexRegionIds, eegData, selectedClasses, selectedBand, timeIndex,
    contrastMode, contrastOrder, erdThreshold, channelMode, maxAbs,
) {
    if (!vertexRegionIds?.length) return null;

    const regionAvg = computeRegionAveragesAtTime(
        eegData,
        selectedClasses,
        selectedBand,
        timeIndex,
        contrastMode,
        contrastOrder,
        channelMode,
    );

    const allVals = Object.values(regionAvg || {});
    if (allVals.length === 0) return null;

    const n = vertexRegionIds.length;
    const colors = new Float32Array(n * 3);

    for (let i = 0; i < n; i++) {
        const rid = vertexRegionIds[i];
        const val = regionAvg[rid];

        if (val !== undefined) {
            // Apply threshold filter
            if (Math.abs(val) < (erdThreshold || 0)) {
                // Below threshold: neutral dark grey
                colors[i * 3]     = 0.2;
                colors[i * 3 + 1] = 0.2;
                colors[i * 3 + 2] = 0.2;
            } else {
                const norm = Math.max(-1, Math.min(1, val / maxAbs));
                if (norm < 0) {
                    // Blue — ERD / desynchronisation
                    const t = -norm;
                    colors[i * 3]     = 0.15 * (1 - t) + 0.10 * t;
                    colors[i * 3 + 1] = 0.15 * (1 - t) + 0.40 * t;
                    colors[i * 3 + 2] = 0.15 * (1 - t) + 0.90 * t;
                } else {
                    // Red — ERS / synchronisation
                    const t = norm;
                    colors[i * 3]     = 0.15 * (1 - t) + 0.90 * t;
                    colors[i * 3 + 1] = 0.15 * (1 - t) + 0.20 * t;
                    colors[i * 3 + 2] = 0.15 * (1 - t) + 0.10 * t;
                }
            }
        } else {
            // No electrode maps here — dark grey
            colors[i * 3]     = 0.12;
            colors[i * 3 + 1] = 0.12;
            colors[i * 3 + 2] = 0.12;
        }
    }

    return { colors, regionAvg };
}

export default function BrainViewer({
    onRegionHover,
    eegData,
    selectedClasses,
    selectedBand,
    currentTimeIndex,
    heatmapEnabled,
    contrastMode,
    contrastOrder,
    erdThreshold,
    multiView,
    channelMode,
}) {
    const containerRef = useRef(null);
    const tooltipRef = useRef(null);
    const [loading, setLoading] = useState(true);

    const meshRef = useRef(null);
    const metaRef = useRef(null);
    const origColorsRef = useRef(null);
    const materialRef = useRef(null);
    const heatmapValuesRef = useRef({});
    const controlsRef = useRef(null);
    const configRef = useRef({ multiView });

    useEffect(() => {
        configRef.current.multiView = multiView;
    }, [multiView]);

    const heatmapMaxAbs = useMemo(
        () => computeHeatmapMaxAbs(
            eegData,
            selectedClasses,
            selectedBand,
            contrastMode,
            contrastOrder,
            channelMode,
        ),
        [eegData, selectedClasses, selectedBand, contrastMode, contrastOrder, channelMode],
    );

    // ---- Heatmap effect ----
    useEffect(() => {
        const mesh = meshRef.current;
        const meta = metaRef.current;
        const origColors = origColorsRef.current;
        if (!mesh || !meta || !origColors) return;

        const colorAttr = mesh.geometry.attributes.color;

        const activeClasses = [...selectedClasses].filter(
            (c) => eegData?.erd_ers?.[selectedBand]?.[c]
        );

        if (!heatmapEnabled || !eegData || activeClasses.length === 0) {
            // Show neutral grey when heatmap is off or no classes are active
            const n = colorAttr.array.length / 3;
            for (let i = 0; i < n; i++) {
                colorAttr.array[i * 3]     = 0.18;
                colorAttr.array[i * 3 + 1] = 0.18;
                colorAttr.array[i * 3 + 2] = 0.18;
            }
            colorAttr.needsUpdate = true;
            heatmapValuesRef.current = {};
            return;
        }

        const result = computeHeatmapColors(
            meta.vertexRegionIds,
            eegData,
            selectedClasses,
            selectedBand,
            currentTimeIndex,
            contrastMode,
            contrastOrder,
            erdThreshold,
            channelMode,
            heatmapMaxAbs,
        );

        if (result) {
            colorAttr.array.set(result.colors);
            heatmapValuesRef.current = result.regionAvg;
        } else {
            // No valid result — neutral grey
            const n = colorAttr.array.length / 3;
            for (let i = 0; i < n; i++) {
                colorAttr.array[i * 3]     = 0.18;
                colorAttr.array[i * 3 + 1] = 0.18;
                colorAttr.array[i * 3 + 2] = 0.18;
            }
            heatmapValuesRef.current = {};
        }
        colorAttr.needsUpdate = true;
    }, [loading, heatmapEnabled, eegData, selectedClasses, selectedBand, currentTimeIndex, contrastMode, contrastOrder, erdThreshold, channelMode, heatmapMaxAbs]);

    // ---- Three.js setup (once) ----
    useEffect(() => {
        const container = containerRef.current;
        if (!container) return;

        // --- Renderer ---
        const renderer = new THREE.WebGLRenderer({ antialias: true });
        renderer.setSize(container.clientWidth, container.clientHeight);
        renderer.setPixelRatio(window.devicePixelRatio);
        renderer.setClearColor(0x000000);
        container.appendChild(renderer.domElement);

        // --- Scene ---
        const scene = new THREE.Scene();

        // --- Camera ---
        const camera = new THREE.PerspectiveCamera(
            50,
            container.clientWidth / container.clientHeight,
            0.1,
            5000,
        );
        camera.position.set(0, 0, 250);

        // --- Lights ---
        const ambient = new THREE.AmbientLight(0xffffff, 0.6);
        scene.add(ambient);
        const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
        dirLight.position.set(100, 100, 200);
        scene.add(dirLight);
        const dirLight2 = new THREE.DirectionalLight(0xffffff, 0.3);
        dirLight2.position.set(-100, -50, -100);
        scene.add(dirLight2);

        // --- Controls ---
        const controls = new OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.08;
        controls.rotateSpeed = 0.8;
        controlsRef.current = controls;

        // --- Raycasting ---
        const raycaster = new THREE.Raycaster();
        const mouse = new THREE.Vector2();

        // --- Post-processing (SSAO) ---
        const composer = new EffectComposer(renderer);
        composer.addPass(new RenderPass(scene, camera));

        const w = container.clientWidth;
        const h = container.clientHeight;
        const ssaoPass = new SSAOPass(scene, camera, w, h);
        ssaoPass.kernelRadius = 12;
        ssaoPass.kernelSize = 64;
        ssaoPass.minDistance = 0.0003;
        ssaoPass.maxDistance = 0.02;
        ssaoPass.intensity = 1.2;
        ssaoPass.normalMaterial.side = THREE.DoubleSide;
        composer.addPass(ssaoPass);
        composer.addPass(new OutputPass());

        // --- Load region metadata ---
        fetch('/data/region_metadata.json')
            .then((r) => r.json())
            .then((data) => {
                const idToName = { 0: 'Unlabelled' };
                for (const region of data.regions) {
                    idToName[region.id] = region.name;
                }
                metaRef.current = {
                    idToName,
                    vertexRegionIds: data.vertex_region_ids || [],
                    regions: data.regions,
                };
            });

        // --- Multi-View Cameras ---
        const MULTI_FOV = 50;
        const MULTI_MARGIN = 1.18;
        const leftCamera = new THREE.PerspectiveCamera(MULTI_FOV, 1, 0.1, 5000);
        const topCamera = new THREE.PerspectiveCamera(MULTI_FOV, 1, 0.1, 5000);
        const rightCamera = new THREE.PerspectiveCamera(MULTI_FOV, 1, 0.1, 5000);

        let centerPoint = new THREE.Vector3();
        let maxDimVal = 100;
        let brainRadius = 100;
        let multiViewReady = false;

        // Distance at which a sphere of `brainRadius` fits inside a perspective
        // camera with `MULTI_FOV` vertical FOV and the pane's aspect ratio.
        // Sphere-based fit is orientation-independent: the sphere's silhouette is
        // a circle of radius R from any direction, so its angular radius is
        // arcsin(R/d). For the sphere to fit, arcsin(R/d) <= half-FOV in the
        // tighter axis (whichever of vertical/horizontal is narrower).
        const halfFovV = THREE.MathUtils.degToRad(MULTI_FOV) / 2;
        const fitDistance = (aspect) => {
            const halfFovH = Math.atan(aspect * Math.tan(halfFovV));
            const tighter = Math.min(halfFovV, halfFovH);
            return (brainRadius / Math.sin(tighter)) * MULTI_MARGIN;
        };

        // --- Load brain mesh PLY ---
        const loader = new PLYLoader();
        loader.load('/data/brain_mesh_destrieux_mapped.ply', (geometry) => {
            if (!geometry.attributes.normal) {
                geometry.computeVertexNormals();
            }

            const material = new THREE.MeshPhongMaterial({
                vertexColors: true,
                side: THREE.DoubleSide,
                shininess: 30,
                flatShading: false,
            });
            materialRef.current = material;

            const brainMesh = new THREE.Mesh(geometry, material);
            scene.add(brainMesh);
            meshRef.current = brainMesh;

            origColorsRef.current = new Float32Array(
                geometry.attributes.color.array,
            );

            // Centre camera on the mesh
            const box = new THREE.Box3().setFromObject(brainMesh);
            const centre = box.getCenter(new THREE.Vector3());
            centerPoint.copy(centre);
            const size = box.getSize(new THREE.Vector3());
            const maxDim = Math.max(size.x, size.y, size.z);
            maxDimVal = maxDim;
            
            camera.position.set(
                centre.x,
                centre.y,
                centre.z + maxDim * 1.5,
            );
            controls.target.copy(centre);
            controls.update();
            controls.saveState();

            // Mesh axis convention (empirically determined): -X anterior,
            // +X posterior, +Y superior, ±Z lateral (left/right ear).
            // Left/right Z signs are chosen to match typical viewer convention;
            // verify against C3 (left motor) visibility and swap if reversed.
            // Multi-view positions are recomputed per frame to fit each pane's aspect.
            geometry.computeBoundingSphere();
            brainRadius = geometry.boundingSphere?.radius
                ?? Math.sqrt(size.x * size.x + size.y * size.y + size.z * size.z) / 2;
            leftCamera.up.set(0, 1, 0);
            rightCamera.up.set(0, 1, 0);
            topCamera.up.set(-1, 0, 0);
            multiViewReady = true;

            setLoading(false);
        });

        // --- Hover handler ---
        let prevRegionName = null;
        const onMouseMove = (e) => {
            const brainMesh = meshRef.current;
            const meta = metaRef.current;
            if (!brainMesh || !meta || !meta.vertexRegionIds.length) return;

            const rect = container.getBoundingClientRect();
            mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
            mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

            raycaster.setFromCamera(mouse, camera);
            const intersects = raycaster.intersectObject(brainMesh);

            const tooltip = tooltipRef.current;
            if (intersects.length > 0) {
                const vertexIdx = intersects[0].face.a;
                const regionId = meta.vertexRegionIds[vertexIdx];
                const regionName = meta.idToName[regionId] || 'Unknown';

                // Include ERD/ERS value when heatmap is active
                const erdValue = heatmapValuesRef.current[regionId];
                let tooltipText = regionName;
                if (erdValue !== undefined) {
                    const sign = erdValue > 0 ? '+' : '';
                    tooltipText += ` (${sign}${erdValue.toFixed(1)}%)`;
                }

                if (tooltip) {
                    tooltip.textContent = tooltipText;
                    tooltip.style.left = e.clientX + 15 + 'px';
                    tooltip.style.top = e.clientY + 15 + 'px';
                    tooltip.style.display = 'block';
                }

                if (regionName !== prevRegionName) {
                    prevRegionName = regionName;
                    if (onRegionHover) onRegionHover(regionName);
                }
            } else {
                if (tooltip) tooltip.style.display = 'none';
                if (prevRegionName !== null) {
                    prevRegionName = null;
                    if (onRegionHover) onRegionHover(null);
                }
            }
        };

        container.addEventListener('mousemove', onMouseMove);

        // --- Animation loop ---
        let frameId;
        const animate = () => {
            frameId = requestAnimationFrame(animate);
            controls.update();
            
            if (configRef.current.multiView && multiViewReady) {
                // Split-screen render (Left, Top, Right). Each pane's camera
                // distance is fit to the brain bbox using that pane's aspect,
                // so the brain never clips regardless of window width.
                const w = container.clientWidth;
                const h = container.clientHeight;
                const w3 = Math.floor(w / 3);
                const wRight = w - w3 * 2;

                renderer.setScissorTest(true);

                // Left Hemisphere — view dir -Z
                const aspectL = w3 / h;
                const distL = fitDistance(aspectL);
                leftCamera.position.set(centerPoint.x, centerPoint.y, centerPoint.z + distL);
                leftCamera.lookAt(centerPoint);
                leftCamera.aspect = aspectL;
                leftCamera.updateProjectionMatrix();
                renderer.setViewport(0, 0, w3, h);
                renderer.setScissor(0, 0, w3, h);
                renderer.render(scene, leftCamera);

                // Top View — view dir -Y, anterior at top of screen via up=(-1,0,0)
                const aspectT = w3 / h;
                const distT = fitDistance(aspectT);
                topCamera.position.set(centerPoint.x, centerPoint.y + distT, centerPoint.z);
                topCamera.lookAt(centerPoint);
                topCamera.aspect = aspectT;
                topCamera.updateProjectionMatrix();
                renderer.setViewport(w3, 0, w3, h);
                renderer.setScissor(w3, 0, w3, h);
                renderer.render(scene, topCamera);

                // Right Hemisphere — view dir +Z
                const aspectR = wRight / h;
                const distR = fitDistance(aspectR);
                rightCamera.position.set(centerPoint.x, centerPoint.y, centerPoint.z - distR);
                rightCamera.lookAt(centerPoint);
                rightCamera.aspect = aspectR;
                rightCamera.updateProjectionMatrix();
                renderer.setViewport(w3 * 2, 0, wRight, h);
                renderer.setScissor(w3 * 2, 0, wRight, h);
                renderer.render(scene, rightCamera);

                renderer.setScissorTest(false);
            } else if (configRef.current.multiView) {
                // Multi-view requested but mesh not yet loaded — clear black
                renderer.setViewport(0, 0, container.clientWidth, container.clientHeight);
                renderer.clear();
            } else {
                // Default SSAO Render
                renderer.setViewport(0, 0, container.clientWidth, container.clientHeight);
                composer.render();
            }
        };
        animate();

        // --- Resize ---
        const onResize = () => {
            const rw = container.clientWidth;
            const rh = container.clientHeight;
            if (rw === 0 || rh === 0) return;
            camera.aspect = rw / rh;
            camera.updateProjectionMatrix();
            renderer.setSize(rw, rh);
            composer.setSize(rw, rh);
        };
        const ro = new ResizeObserver(onResize);
        ro.observe(container);

        // --- Cleanup ---
        return () => {
            ro.disconnect();
            container.removeEventListener('mousemove', onMouseMove);
            cancelAnimationFrame(frameId);
            composer.dispose();
            renderer.dispose();
            if (container.contains(renderer.domElement)) {
                container.removeChild(renderer.domElement);
            }
        };
    }, []);

    return (
        <>
            <div ref={containerRef} className="viewer-container">
                {loading && (
                    <div className="loader">
                        <div className="spinner" />
                        <p>Loading brain model...</p>
                    </div>
                )}
                {!loading && multiView && (
                    <div className="multi-view-labels">
                        <span className="multi-view-label">Left</span>
                        <span className="multi-view-label">Top</span>
                        <span className="multi-view-label">Right</span>
                    </div>
                )}
                {!loading && !multiView && (
                    <button
                        className="brain-reset-btn"
                        onClick={() => controlsRef.current?.reset()}
                        title="Reset view"
                        aria-label="Reset view"
                    >
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                            <path d="M2 7a5 5 0 1 0 1.5-3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                            <path d="M2 2v3h3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                    </button>
                )}
                {heatmapEnabled && !loading && (
                    <div className="brain-legend">
                        <div className="brain-legend-bar">
                            <div className="brain-legend-gradient" />
                            <div className="brain-legend-labels">
                                <span>ERS +</span>
                                <span>0</span>
                                <span>ERD −</span>
                            </div>
                        </div>
                        <div className="brain-legend-desc">
                            <span className="brain-legend-item"><span className="brain-legend-dot brain-legend-dot-red" />Synchronization (power increase)</span>
                            <span className="brain-legend-item"><span className="brain-legend-dot brain-legend-dot-blue" />Desynchronization (power decrease)</span>
                        </div>
                    </div>
                )}
            </div>
            <div ref={tooltipRef} className="region-tooltip" />
        </>
    );
}
