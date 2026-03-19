'use client';

import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { SSAOPass } from 'three/examples/jsm/postprocessing/SSAOPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';

/**
 * Compute per-vertex heatmap colours from ERD/ERS data.
 *
 * Maps channel-level band power to brain regions via the electrode-region
 * mapping, then colours each vertex by its region's value using a diverging
 * blue (ERD) - grey - red (ERS) colour scale.
 */
function computeHeatmapColors(
    vertexRegionIds, eegData, selectedClasses, selectedBand, timeIndex,
) {
    const bandData = eegData?.erd_ers?.[selectedBand];
    if (!bandData || !vertexRegionIds?.length) return null;

    const channels = eegData.dataset.channels;
    const channelRegions = eegData.channel_regions;
    const activeClasses = [...selectedClasses].filter((c) => bandData[c]);
    if (activeClasses.length === 0) return null;

    // Per-channel average across selected classes at current time
    const channelValues = {};
    for (let i = 0; i < channels.length; i++) {
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

    const allVals = Object.values(regionAvg);
    if (allVals.length === 0) return null;
    const maxAbs = Math.max(...allVals.map(Math.abs), 1);

    const n = vertexRegionIds.length;
    const colors = new Float32Array(n * 3);

    for (let i = 0; i < n; i++) {
        const rid = vertexRegionIds[i];
        const val = regionAvg[rid];

        if (val !== undefined) {
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
}) {
    const containerRef = useRef(null);
    const tooltipRef = useRef(null);
    const [loading, setLoading] = useState(true);

    const meshRef = useRef(null);
    const metaRef = useRef(null);
    const origColorsRef = useRef(null);
    const materialRef = useRef(null);
    const heatmapValuesRef = useRef({});

    // ---- Heatmap effect ----
    useEffect(() => {
        const mesh = meshRef.current;
        const meta = metaRef.current;
        const origColors = origColorsRef.current;
        if (!mesh || !meta || !origColors) return;

        const colorAttr = mesh.geometry.attributes.color;

        if (!heatmapEnabled || !eegData) {
            colorAttr.array.set(origColors);
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
        );

        if (result) {
            colorAttr.array.set(result.colors);
            heatmapValuesRef.current = result.regionAvg;
        } else {
            colorAttr.array.set(origColors);
            heatmapValuesRef.current = {};
        }
        colorAttr.needsUpdate = true;
    }, [heatmapEnabled, eegData, selectedClasses, selectedBand, currentTimeIndex]);

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
            const size = box.getSize(new THREE.Vector3());
            const maxDim = Math.max(size.x, size.y, size.z);
            camera.position.set(
                centre.x,
                centre.y,
                centre.z + maxDim * 1.5,
            );
            controls.target.copy(centre);
            controls.update();

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
            composer.render();
        };
        animate();

        // --- Resize ---
        const onResize = () => {
            const rw = container.clientWidth;
            const rh = container.clientHeight;
            camera.aspect = rw / rh;
            camera.updateProjectionMatrix();
            renderer.setSize(rw, rh);
            composer.setSize(rw, rh);
        };
        window.addEventListener('resize', onResize);

        // --- Cleanup ---
        return () => {
            window.removeEventListener('resize', onResize);
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
            </div>
            <div ref={tooltipRef} className="region-tooltip" />
        </>
    );
}
