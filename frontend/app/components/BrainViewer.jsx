'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { SSAOPass } from 'three/examples/jsm/postprocessing/SSAOPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
export default function BrainViewer({ onRegionHover, highlightRegion }) {
    const containerRef = useRef(null);
    const tooltipRef = useRef(null);
    const [loading, setLoading] = useState(true);

    const meshRef = useRef(null);
    const metaRef = useRef(null);
    const origColorsRef = useRef(null);
    const glowMeshRef = useRef(null);      // emissive overlay for highlighted region
    const materialRef = useRef(null);      // main MeshPhongMaterial (for opacity control)

    // ---- Highlight effect (sidebar → brain) ----
    useEffect(() => {
        const mesh = meshRef.current;
        const meta = metaRef.current;
        const origColors = origColorsRef.current;
        const glowMesh = glowMeshRef.current;
        const material = materialRef.current;
        if (!mesh || !meta || !origColors || !glowMesh || !material) return;

        const colors = mesh.geometry.attributes.color;
        const arr = colors.array;
        const glowColors = glowMesh.geometry.attributes.color;
        const glowArr = glowColors.array;
        const glowPositions = glowMesh.geometry.attributes.position.array;

        if (!highlightRegion) {
            // Restore: fully opaque, original colours, hide glow
            arr.set(origColors);
            colors.needsUpdate = true;
            material.transparent = false;
            material.opacity = 1.0;
            material.depthWrite = true;
            material.needsUpdate = true;
            glowMesh.visible = false;
            return;
        }

        // Find the region ID(s) matching this name
        const targetIds = new Set();
        for (const [id, name] of Object.entries(meta.idToName)) {
            if (name === highlightRegion) targetIds.add(Number(id));
        }

        const vids = meta.vertexRegionIds;
        const GLOW = [0.43, 0.90, 0.72];

        // Main mesh: keep original colours but make it semi-transparent
        arr.set(origColors);
        colors.needsUpdate = true;
        material.transparent = true;
        material.opacity = 0.25;
        material.depthWrite = false;
        material.needsUpdate = true;

        // Glow mesh: only show vertices belonging to the selected region
        const srcPos = mesh.geometry.attributes.position.array;
        const HIDDEN = 0; // collapse non-matching verts to origin (invisible degenerate tris)
        for (let i = 0; i < vids.length; i++) {
            const base = i * 3;
            if (targetIds.has(vids[i])) {
                glowPositions[base]     = srcPos[base];
                glowPositions[base + 1] = srcPos[base + 1];
                glowPositions[base + 2] = srcPos[base + 2];
                glowArr[base]     = GLOW[0];
                glowArr[base + 1] = GLOW[1];
                glowArr[base + 2] = GLOW[2];
            } else {
                glowPositions[base]     = HIDDEN;
                glowPositions[base + 1] = HIDDEN;
                glowPositions[base + 2] = HIDDEN;
                glowArr[base]     = 0;
                glowArr[base + 1] = 0;
                glowArr[base + 2] = 0;
            }
        }
        glowMesh.geometry.attributes.position.needsUpdate = true;
        glowColors.needsUpdate = true;
        glowMesh.visible = true;
    }, [highlightRegion]);

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
            5000
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

        // --- Post-processing setup ---
        const composer = new EffectComposer(renderer);
        const renderPass = new RenderPass(scene, camera);
        composer.addPass(renderPass);

        // SSAO — ambient occlusion to darken sulci and add surface depth
        // Parameters are tuned for brain-mesh scale (~150 voxel units across)
        const w = container.clientWidth;
        const h = container.clientHeight;
        const ssaoPass = new SSAOPass(scene, camera, w, h);
        ssaoPass.kernelRadius = 12;      // world-space sample radius (voxel units)
        ssaoPass.kernelSize = 64;        // more samples = cleaner AO
        ssaoPass.minDistance = 0.0003;   // ~1.5 voxel units — ignore micro self-intersections
        ssaoPass.maxDistance = 0.02;     // ~100 voxel units — cap so deep occluders don't bleed
        ssaoPass.intensity = 1.2;        // strength of the darkening
        // Match DoubleSide so the SSAO normal/depth pass doesn't cull
        // back-faces and create dark see-through artifacts
        ssaoPass.normalMaterial.side = THREE.DoubleSide;
        composer.addPass(ssaoPass);

        // Output (tone mapping / colour space)
        const outputPass = new OutputPass();
        composer.addPass(outputPass);

        // Load region metadata
        fetch('/data/region_metadata.json')
            .then((r) => r.json())
            .then((data) => {
                const idToName = {};
                for (const region of data.regions) {
                    idToName[region.id] = region.name;
                }
                idToName[0] = 'Unlabelled';

                metaRef.current = {
                    idToName,
                    vertexRegionIds: data.vertex_region_ids || [],
                    regions: data.regions,
                };
            });

        // Load brain mesh PLY
        const loader = new PLYLoader();
        loader.load('/data/brain_mesh_destrieux_mapped.ply', (geometry) => {
            // Use normals baked into the PLY by the backend (Open3D).
            // Calling computeVertexNormals() here would average them and
            // produce artificial smoothing across the entire surface.
            if (!geometry.attributes.normal) {
                geometry.computeVertexNormals();
            }

            const material = new THREE.MeshPhongMaterial({
                vertexColors: true,
                side: THREE.DoubleSide,
                shininess: 30,
                flatShading: false,
                transparent: false,
                opacity: 1.0,
                depthWrite: true,
            });
            materialRef.current = material;

            const brainMesh = new THREE.Mesh(geometry, material);
            scene.add(brainMesh);
            meshRef.current = brainMesh;

            const colorAttr = geometry.attributes.color;
            origColorsRef.current = new Float32Array(colorAttr.array);

            // Build glow overlay mesh (initially hidden)
            const glowGeom = geometry.clone();
            const glowMat = new THREE.MeshPhongMaterial({
                vertexColors: true,
                side: THREE.DoubleSide,
                emissive: new THREE.Color(0.25, 0.55, 0.45),
                emissiveIntensity: 0.6,
                shininess: 60,
                transparent: false,
                depthTest: true,
            });
            const glowMesh = new THREE.Mesh(glowGeom, glowMat);
            glowMesh.visible = false;
            glowMesh.renderOrder = 1;
            scene.add(glowMesh);
            glowMeshRef.current = glowMesh;

            // Centre camera on the mesh
            const box = new THREE.Box3().setFromObject(brainMesh);
            const centre = box.getCenter(new THREE.Vector3());
            const size = box.getSize(new THREE.Vector3());
            const maxDim = Math.max(size.x, size.y, size.z);
            camera.position.set(centre.x, centre.y, centre.z + maxDim * 1.5);
            controls.target.copy(centre);
            controls.update();

            setLoading(false);
        });

        // --- Hover handler ---
        let prevRegionName = null;
        const onMouseMove = (e) => {
            const brainMesh = meshRef.current;
            const meta = metaRef.current;
            if (!brainMesh || !meta || meta.vertexRegionIds.length === 0) return;

            const rect = container.getBoundingClientRect();
            mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
            mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

            raycaster.setFromCamera(mouse, camera);
            const intersects = raycaster.intersectObject(brainMesh);

            const tooltip = tooltipRef.current;
            if (intersects.length > 0) {
                const hit = intersects[0];
                const face = hit.face;
                const vertexIdx = face.a;

                const regionId = meta.vertexRegionIds[vertexIdx];
                const regionName = meta.idToName[regionId] || 'Unknown';

                if (tooltip) {
                    tooltip.textContent = regionName;
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

        // --- Animation loop (uses composer instead of direct renderer) ---
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
                        <p>Loading brain model…</p>
                    </div>
                )}
            </div>
            <div ref={tooltipRef} className="region-tooltip" />
        </>
    );
}
