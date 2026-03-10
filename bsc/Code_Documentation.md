# Code Documentation
## Table of Contents

1. [Backend Architecture Overview](#1-backend-architecture-overview)
2. [Configuration — `config.py` & `.env`](#2-configuration--configpy--env)
3. [Model Loading — `model/loader.py`](#3-model-loading--modelloaderpy)
4. [Mesh Generation — `model/pointcloud.py`](#4-mesh-generation--modelpointcloudpy)
5. [Atlas & Gap-Fill — `regions/atlas.py`](#5-atlas--gap-fill--regionsatlaspy)
6. [Region Colour Palette — `regions/palette.py`](#6-region-colour-palette--regionspalettepy)
7. [Region Mapping — `regions/mapping.py`](#7-region-mapping--regionsmappingpy)
8. [Electrode Mapping — `electrode/mapping.py`](#8-electrode-mapping--electrodemappingpy)
9. [Viewer — `viewer/viewer.py`](#9-viewer--viewerviewerpy)
10. [Pipeline Entry Point — `main.py`](#10-pipeline-entry-point--mainpy)
11. [Frontend — Browser 3D Brain Viewer](#11-frontend--browser-3d-brain-viewer)

---

## Sources
- Nibabel: https://nipy.org/nibabel/manual.html#manual
- Nilearn: https://nilearn.github.io/stable/index.html
- Open3D: https://www.open3d.org/docs/release/
- scikit-image (Marching Cubes): https://scikit-image.org/docs/stable/api/skimage.measure.html#skimage.measure.marching_cubes

## 1. Backend Architecture Overview

### Old vs New Structure

The old codebase consisted of four standalone Python scripts (`PointCloud.py`, `BrainRegions.py`, `ElectrodeMapping.py`, `Viewer.py`) that all lived in the project root. Each script had its own hardcoded paths, its own copy of shared logic (like loading NIfTI files or computing the centroid), and had to be run individually in the right order.

The new codebase reorganises everything into a proper Python package under `backend/`. The scripts have been broken up into focused modules grouped by responsibility:

```
backend/
├── __init__.py
├── .env                     Environment variables (paths, parameters)
├── config.py                Centralised Config dataclass
├── main.py                  Single entry point for the whole pipeline
├── model/
│   ├── loader.py            NIfTI loading & masking
│   └── pointcloud.py        Mesh generation (Marching Cubes)
├── regions/
│   ├── atlas.py             Atlas fetching, resampling, gap-fill
│   ├── palette.py           Region colour palette
│   └── mapping.py           PLY vertex → region mapping (legacy path)
├── electrode/
│   └── mapping.py           Electrode → region + JSON export
├── viewer/
│   └── viewer.py            Interactive Open3D viewer
├── eeg/
│   └── __init__.py          (placeholder for future EEG processing)
└── testing/
    └── __init__.py          (placeholder for tests)
```

The key benefits of this restructuring:
- **Single entry point**: `python -m backend.main` runs the full pipeline in sequence — no need to remember which script to run first.
- **No duplicated code**: shared functions like NIfTI loading and centroid computation live in one place (`model/loader.py`).
- **Configurable via `.env`**: all paths, parameters, and feature flags are read from a `.env` file and exposed through a `Config` dataclass — no more editing hardcoded constants in multiple files.
- **Each module is independently importable**: you can import just `backend.regions.atlas` or `backend.electrode.mapping` without pulling in everything.

---

## 2. Configuration — `config.py` & `.env`

### Purpose

Replaces the hardcoded constants that were scattered across the old scripts. All configuration is now centralised in a single `Config` dataclass that reads values from a `.env` file in the `backend/` directory.

### How It Works

`config.py` uses `python-dotenv` to load the `.env` file, then defines a `@dataclass` where every field has a default that reads from `os.getenv(...)`. This means you can either set values in `.env` or override them with environment variables at runtime.

#### `_resolve_device(requested)`

Handles the `DEVICE` setting. When set to `'auto'` (the default), it checks for CUDA first, then Apple MPS, then falls back to CPU. This is an improvement over the old code which just checked for MPS.

#### `Config` Dataclass Fields

The dataclass groups configuration into categories:

- **Input Data** — paths to the skull-stripped NIfTI, the full T1w volume, and the brain mask. The old code only used a single brain NIfTI; the new code uses three separate inputs for more accurate masking.
- **Export Directories** — where point clouds, region-mapped meshes, and frontend data go. The old code used `./assets/pointcloud_exports` and `./assets/brainmapping_exports`; the new code moves these under `./data/model/`.
- **Output Filenames** — the PLY and JSON filenames are now configurable instead of hardcoded.
- **Point Cloud Parameters** — threshold, position noise, alpha, normal radius, normal max nearest neighbours. Same values as before but now configurable.
- **Marching Cubes Parameters** — `mc_level` (isosurface level, default 0.15), `mc_step_size` (voxel step, default 1), and `mesh_target_faces` (decimation target, 0 = no decimation). These are new — the old code didn't use Marching Cubes at all.
- **Export Options** — `copy_mapped_mesh_to_frontend` flag to auto-copy the mapped PLY into the frontend's `public/data/` directory.
- **EEG Channels** — the 22-channel list is now a comma-separated string in `.env` instead of a Python list literal.

Derived paths like `mapped_mesh_ply_path` and `output_json_path` are computed as `@property` methods that join directory + filename.

### Design Decisions

| Decision | Rationale |
|---|---|
| **Dataclass + `.env`** | Makes the pipeline configurable without editing source code. The `.env` is gitignored on deployments, so each machine can have its own paths. |
| **`auto` device resolution** | Supports CUDA, MPS, and CPU without the user having to know which GPU framework is available. |
| **Separate T1w + mask inputs** | The old code used a single skull-stripped NIfTI. The new approach loads the full T1w volume and applies the brain mask explicitly, which gives better control over the masking threshold and produces a cleaner isosurface. |

---

## 3. Model Loading — `model/loader.py`

### Purpose

Consolidates all NIfTI loading and preprocessing into one module. The old code had `load_nii_image()` and `load_nii_to_tensor()` duplicated across `PointCloud.py`, `BrainRegions.py`, and `ElectrodeMapping.py`.

### Key Functions

#### `load_nii_image(filepath)`

Same as before — loads a NIfTI file via nibabel and returns the image object.

#### `load_nii_to_tensor(filepath, device)`

Same as before — loads the NIfTI, normalises to [0,1], returns a PyTorch tensor.

#### `compute_pointcloud_centroid(vol_tensor, threshold)`

Same logic as before — finds all voxels above threshold and computes their mean position. This was previously duplicated in `BrainRegions.py` and `ElectrodeMapping.py`, now it lives in one place.

#### `compute_brain_mask(brain_nii, threshold)`

New function. Takes a NIfTI image, normalises its intensity data to [0,1], and returns a boolean mask of voxels above the threshold. This was previously inlined in `ElectrodeMapping.py`'s `load_atlas()`.

#### `load_masked_volume(t1w_path, mask_path)`

New function — this is the big addition. Instead of using a pre-skull-stripped NIfTI (like the old code did), this loads the full T1w volume and a separate brain mask, multiplies them together, and normalises only the brain voxels to [0,1]. Non-brain voxels are set to 0. This produces a cleaner volume for isosurface extraction because the masking boundary is sharp rather than depending on whatever threshold the skull-stripping tool used.

### Design Decisions

| Decision | Rationale |
|---|---|
| **Centralised loader** | Eliminates code duplication — three scripts used to have their own copy of `load_nii_to_tensor`. |
| **Separate T1w + mask** | Gives explicit control over what counts as brain vs background. The old skull-stripped NIfTI sometimes had artefacts at the boundary. |

---

## 4. Mesh Generation — `model/pointcloud.py`

### Purpose

This is the most significantly changed module. The old `PointCloud.py` generated a point cloud by thresholding voxels, adding jitter, centering, flipping Y, applying a colour gradient, and then optionally converting to a mesh using **Alpha Shapes**. The new code replaces the Alpha Shapes approach entirely with **Marching Cubes** from `scikit-image`.

### What Changed and Why

**Alpha Shapes** worked by wrapping a surface around a noisy point cloud. This had several problems:
- It depended on the jittered point cloud, so the mesh quality was sensitive to the `position_noise` parameter.
- The `alpha` parameter was hard to tune — too small and you get holes, too large and you lose detail.
- The resulting mesh had no direct correspondence to the original voxel grid, making region mapping inaccurate (you had to reverse-transform vertices back to voxel space and hope they landed on the right label).

**Marching Cubes** operates directly on the 3D volume data. It extracts an isosurface at a given intensity level, producing vertices that sit exactly on the volume boundary. This means:
- No jitter needed, so the mesh is deterministic.
- Region IDs can be assigned in voxel space before any transforms are applied (forward-carry), which is more accurate than reverse-mapping.
- The mesh quality is controlled by `mc_level` (which intensity value defines the surface) and `mc_step_size` (resolution).

### Key Functions

#### `assign_vertex_region_ids(vertices_voxel, atlas_volume)`

New function. Takes vertex positions in voxel space (before centering/flipping), rounds each to the nearest integer index, clamps to volume bounds, and looks up the atlas label. This is the "forward-carry" approach — region IDs are assigned while the vertices are still aligned to the atlas, so there's no reverse-transform step needed.

#### `fill_unlabelled_from_neighbours(region_ids, faces)`

New function. Some vertices may land on unlabelled voxels (atlas label 0), especially at the brain surface boundary. Instead of the old EDT-based gap-fill (which operates on the 3D volume), this uses the **mesh adjacency** — for each unlabelled vertex, it looks at the region IDs of its direct mesh neighbours and adopts the most common non-zero label. This is done iteratively in BFS-like passes until no more vertices can be filled.

Using mesh adjacency is better than the volume-based approach here because the vertices aren't on a regular grid (they sit on the isosurface), so volumetric EDT wouldn't align well.

#### `color_vertices_by_region(region_ids, id_to_palette_idx, palette)`

Simple helper — maps each vertex's region ID → palette index → RGB colour.

#### `generate_and_export(config, masked_volume, atlas_volume, id_to_palette_idx, palette)`

The main pipeline function. Steps:

1. **Run Marching Cubes** on the masked volume (`skimage.measure.marching_cubes`) with the configured level and step size.
2. **Build an Open3D mesh** from the resulting vertices and faces.
3. **Optionally decimate** — if `mesh_target_faces` is set, use Open3D's `simplify_quadric_decimation` to reduce triangle count. Decimation happens in voxel space before region assignment so that the simplified vertices still accurately map to atlas labels.
4. **Forward-carry region IDs** — call `assign_vertex_region_ids` on the voxel-space vertices.
5. **Fill unlabelled vertices** via mesh adjacency if any exist.
6. **Colour vertices** by region.
7. **Centre + flip Y** — same transforms as the old `PointCloud.py` (`verts -= centroid`, `verts[:, 1] = -verts[:, 1]`), but now there's also a **face winding flip** (`faces[:, ::-1]`) to compensate for the Y-axis flip. Without this, the normals would point inward and Three.js `FrontSide` culling would show the inside of the mesh.
8. **Orient triangles + compute normals** — `mesh.orient_triangles()` ensures consistent outward-facing winding, then `compute_vertex_normals()` generates the per-vertex normals that the frontend will use.
9. **Export** the mapped PLY and optionally copy it to the frontend's `public/data/` directory.
10. **Return** the per-vertex region ID list for the electrode pipeline to reuse.

### Design Decisions

| Decision | Rationale |
|---|---|
| **Marching Cubes over Alpha Shapes** | Deterministic, operates directly on the volume, produces vertices in voxel space for accurate region assignment. |
| **Forward-carry region IDs** | Assigning labels before transforms avoids the inaccuracy of reverse-transforming and hoping to land on the correct atlas voxel. |
| **Mesh adjacency gap-fill** | Better suited for isosurface vertices than volumetric EDT since they don't sit on a regular grid. |
| **Face winding flip** | The Y-axis flip inverts the mesh handedness. Reversing the face winding (`[:, ::-1]`) compensates, so normals stay outward-facing. |
| **Decimation before region assignment** | Reduces polygon count while vertices are still in voxel space, so the simplified mesh still maps accurately to atlas labels. |
| **Normals baked in PLY** | The backend writes per-vertex normals into the PLY file. The frontend can use these directly instead of recomputing them (which would smooth over detail). |

---

## 5. Atlas & Gap-Fill — `regions/atlas.py`

### Purpose

Extracted from `BrainRegions.py` and `ElectrodeMapping.py`. Contains the Destrieux atlas fetching/resampling logic and the volumetric gap-fill. Functionally identical to the old code — just moved into its own module.

### Key Functions

#### `fetch_and_resample_atlas(brain_nii_img)`

Same as the old `fetch_destrieux_atlas()` — downloads the Destrieux 2009 atlas, resamples it into the subject's voxel space with nearest-neighbour interpolation, and builds the region name lookup dictionary.

#### `gap_fill_labels(atlas_volume, brain_mask)`

Same as the old `gap_fill_labels()` — finds unlabelled brain voxels and fills them with the nearest labelled neighbour using `scipy.ndimage.distance_transform_edt`. This is still used for the volumetric atlas itself; the mesh-specific gap-fill uses the adjacency approach in `pointcloud.py`.

---

## 6. Region Colour Palette — `regions/palette.py`

### Purpose

Extracted from both `BrainRegions.py` and `ElectrodeMapping.py`. Both old scripts had identical `build_region_palette()` functions — now there's just one.

### Key Function

#### `build_region_palette(names_map)`

Same logic as before — samples the `gist_ncar` colourmap at evenly spaced intervals, one colour per region. "Unlabelled" (ID 0) is forced to dark grey `[0.15, 0.15, 0.15]`. Returns the sorted IDs, full names dict, palette array, and ID-to-palette-index lookup.

---

## 7. Region Mapping — `regions/mapping.py`

### Purpose

Contains the old reverse-transform approach from `BrainRegions.py` — load a PLY, un-flip Y, un-center, look up atlas labels, assign colours, export. This is the **legacy path** that was used when the mesh was generated via Alpha Shapes.

In the new Marching Cubes pipeline, this module is not called by `main.py` because region IDs are forward-carried during mesh generation. It's kept in the codebase as an alternative path for processing externally generated PLY files.

### Key Functions

#### `map_vertices_to_regions(vertices, centroid, atlas_volume, id_to_palette_idx, palette)`

Same as the old `BrainRegions.py` version — un-flips Y, un-centers, rounds to voxel indices, samples atlas labels, assigns palette colours.

#### `process_ply_file(filepath, centroid, atlas_volume, id_to_palette_idx, palette, output_dir)`

Same as before — loads a PLY (mesh or point cloud), maps vertices, colours them, exports.

#### `map_all_ply_files(config, centroid, atlas_volume, id_to_palette_idx, palette)`

New orchestrator that processes all PLY files from the pointcloud export directory and optionally copies the mapped mesh to the frontend.

---

## 8. Electrode Mapping — `electrode/mapping.py`

### Purpose

Contains the EEG electrode-to-region mapping logic from the old `ElectrodeMapping.py`, plus the JSON builder. The core algorithm is unchanged — ray-casting from scalp inward toward the volume centre to find the nearest cortical region beneath each electrode.

### Key Functions

#### `get_electrode_mni_coords(channel_names)`

Unchanged — uses MNE's `standard_1020` montage to get MNI positions.

#### `mni_to_voxel(mni_coords_metres, nii_affine)`

Unchanged — converts metres → mm → voxel indices via inverse affine.

#### `map_electrodes_to_regions(channel_coords, brain_nii, atlas_volume, names_map)`

Unchanged — ray-casts from each electrode position toward the volume centre in 0.5-voxel steps.

#### `map_mesh_vertices_to_regions(mesh_ply_path, centroid, atlas_volume)`

Unchanged — reverse-transforms vertices and looks up atlas labels. This is now only called as a fallback when pre-computed vertex region IDs are not provided.

#### `build_output(electrode_mappings, names_map, palette, sorted_ids, full_names, id_to_palette_idx, vertex_region_ids)`

Unchanged — assembles the JSON structure with regions, electrodes, region_electrodes, and optionally vertex_region_ids.

#### `run_electrode_pipeline(config, brain_nii, atlas_volume, names_map, centroid, sorted_ids, full_names, palette, id_to_palette_idx, vertex_region_ids)`

New orchestrator function that runs the full electrode pipeline: get electrode coordinates → map to regions → optionally map mesh vertices → build JSON → write to disk. The key improvement is the `vertex_region_ids` parameter — if the caller (i.e. `main.py`) already computed vertex region IDs during Marching Cubes generation, those are reused and the expensive reverse-transform re-mapping is skipped.

### Design Decisions

| Decision | Rationale |
|---|---|
| **Reuse pre-computed vertex IDs** | The Marching Cubes pipeline already assigns region IDs per-vertex in voxel space (forward-carry). Recomputing them via reverse-transform would be both slower and less accurate. |
| **Orchestrator function** | `run_electrode_pipeline` consolidates the multi-step flow (montage → mapping → JSON) so `main.py` only needs one call. |

---

## 9. Viewer — `viewer/viewer.py`

### Purpose

Same interactive Open3D viewer as the old `Viewer.py`, moved into the `backend.viewer` subpackage. The only significant change is that it now reads directory paths from the `Config` dataclass instead of hardcoded constants.

### Key Functions

All functions (`load_ply`, `visualize`, `collect_ply_files`, `main`) are functionally identical to the old code. The `main()` function creates a `Config()` instance and uses `config.pointcloud_export_dir` and `config.brainmapping_export_dir` instead of the old hardcoded `POINTCLOUD_DIR` and `BRAINMAPPING_DIR`.

---

## 10. Pipeline Entry Point — `main.py`

### Purpose

Single-command entry point that runs the entire brain visualisation pipeline in sequence. Replaces the need to run `PointCloud.py`, `BrainRegions.py`, and `ElectrodeMapping.py` manually in the right order.

### Pipeline Steps

1. **Load NIfTI volumes** — loads the skull-stripped brain NIfTI (for atlas reference) and the masked T1w volume (for mesh generation).
2. **Destrieux atlas + gap-fill** — fetches and resamples the atlas, then gap-fills unlabelled voxels.
3. **Build region palette** — creates the colour lookup table.
4. **Mesh generation** — runs Marching Cubes, decimates, assigns region IDs (forward-carry), colours vertices, centres, flips Y, exports PLY.
5. **Electrode mapping & JSON export** — maps electrodes, reuses the pre-computed vertex region IDs, and writes `region_metadata.json`.
6. **Optional viewer** — if `SHOW_VIEWER=true` in `.env`, launches the Open3D viewer.

### Design Decisions

| Decision | Rationale |
|---|---|
| **Single entry point** | `python -m backend.main` runs everything. No more remembering which script to run first. |
| **Forward-pass of vertex IDs** | `generate_and_export` returns the per-vertex region IDs which are passed directly to `run_electrode_pipeline`, avoiding redundant computation. |

---

## 11. Frontend — Browser 3D Brain Viewer

### Purpose

A Next.js web application that renders the Destrieux-mapped brain mesh in 3D, lets the user rotate/zoom/pan the model, identifies the brain region under the cursor on hover, and displays a sidebar listing all 22 EEG electrodes grouped by their mapped brain region. Hovering an electrode group in the sidebar highlights the corresponding region on the 3D model.

### Technology Stack

| Component | Version |
|---|---|
| **Next.js** | 16.1.6 (App Router) |
| **React** | 19.2.3 |
| **Three.js** | 0.183.1 |
| **CSS** | Vanilla (no UI frameworks) |

### File Structure

```
frontend/
├── app/
│   ├── layout.js          Root layout, metadata title/description
│   ├── page.js             Main page, state management
│   ├── globals.css          Full CSS design system
│   └── components/
│       ├── BrainViewer.jsx  Three.js 3D renderer + hover/highlight + SSAO
│       └── ElectrodeSidebar.jsx  Electrode list grouped by region
├── public/
│   └── data/
│       ├── brain_mesh_destrieux_mapped.ply   Coloured brain mesh
│       └── region_metadata.json              Electrode + region data
├── package.json
├── next.config.mjs
└── jsconfig.json
```

### Components

#### `page.js` — Application Root

Unchanged from the old version. A `'use client'` component that composes `BrainViewer` and `ElectrodeSidebar`. Manages two state variables:

- `activeRegion` — set by hovering on the 3D brain (via `onRegionHover` callback)
- `sidebarRegion` — set by hovering an electrode group in the sidebar (via `onSidebarHover` callback)

The displayed region is `sidebarRegion || activeRegion` — sidebar hover takes priority. Both callbacks are wrapped in `useCallback` to avoid unnecessary re-renders.

#### `BrainViewer.jsx` — Three.js 3D Renderer

This component has been significantly enhanced compared to the old version. The base scene setup (renderer, camera, lights, controls, raycasting) is the same, but three major features were added:

**1. SSAO Post-Processing (Screen-Space Ambient Occlusion)**

The old code rendered the scene directly via `renderer.render(scene, camera)`. The new code uses a Three.js `EffectComposer` pipeline with three passes:
- `RenderPass` — standard scene render
- `SSAOPass` — screen-space ambient occlusion that darkens crevices and sulci on the brain surface, adding visual depth. Parameters are tuned for the brain mesh scale: `kernelRadius: 12` (in voxel units), `kernelSize: 64` samples, `intensity: 1.2`. The `normalMaterial.side` is set to `DoubleSide` to match the brain mesh material, otherwise the SSAO depth pass would cull back-faces and create dark artifacts.
- `OutputPass` — handles tone mapping and colour space conversion.

The animation loop now calls `composer.render()` instead of `renderer.render()`, and the resize handler also updates the composer size.

**2. Glow Overlay Mesh**

The old highlight effect dimmed non-target vertices to 15% brightness and coloured target vertices in green. This made the non-highlighted regions very dark and hard to read.

The new approach uses a two-mesh system:
- The **main mesh** keeps its original colours but becomes semi-transparent (`opacity: 0.25`, `depthWrite: false`) when a region is highlighted.
- A **glow overlay mesh** (cloned from the main mesh geometry) is shown on top. It uses an emissive `MeshPhongMaterial` (`emissive: [0.25, 0.55, 0.45]`, `emissiveIntensity: 0.6`) that gives the highlighted region a glowing appearance. Only vertices belonging to the target region keep their real positions; all other vertices are collapsed to the origin (`HIDDEN = 0`), making their triangles degenerate and invisible.

This produces a much cleaner visual effect — the highlighted region appears to glow through a translucent ghost of the rest of the brain.

**3. Backend-Baked Normals**

The old code always called `geometry.computeVertexNormals()` after loading the PLY. The new code checks if the PLY already contains normals (`geometry.attributes.normal`) and only computes them as a fallback. The backend now bakes high-quality normals into the PLY via Open3D's `compute_vertex_normals()` after `orient_triangles()`, so using those directly preserves the surface detail that Three.js's own normal averaging would smooth over.

**Hover detection** and **cleanup** are otherwise unchanged from the old version. The cleanup now additionally disposes the `EffectComposer`.

#### `ElectrodeSidebar.jsx` — Electrode List

Unchanged from the old version. Fetches `/data/region_metadata.json` on mount, groups electrodes by `region_name`, sorts alphabetically, and renders as hoverable region groups with electrode chips.

### CSS Design System (`globals.css`)

Unchanged from the old version.

| Element | Style |
|---|---|
| **Background** | `#0a0a0a` (near-black), borders `#222` |
| **Accent colour** | `#6ee7b7` (mint green) — used for active region text, tooltip text, hover borders, spinner |
| **Font** | `Segoe UI` / system-ui with `Consolas` / `Fira Code` for electrode chips |
| **Layout** | Full-height flexbox: header (fixed), content (flex row: viewer + sidebar) |
| **Sidebar** | Fixed 280px width, scrollable list with 4px custom scrollbar |
| **Loader** | Absolute overlay with CSS-only spinning border animation |
| **Tooltip** | `position: fixed`, `backdrop-filter: blur(8px)`, semi-transparent black background, rounded corners |
| **Transitions** | 0.15s ease on background, border-color, and color for interactive elements |

### Design Decisions

| Decision | Rationale |
|---|---|
| **Vanilla Three.js (no React-Three-Fiber)** | Lower abstraction overhead, easier to control the render loop and event handling, avoids extra dependencies for a single-mesh viewer. |
| **SSAO post-processing** | Makes the brain surface look more three-dimensional by darkening sulci (grooves). The brain mesh has lots of crevices that benefit from ambient occlusion. |
| **Glow overlay instead of vertex dimming** | Cleaner visual — the non-highlighted regions remain recognisable (semi-transparent) instead of becoming nearly black. The emissive glow makes the target region pop out more. |
| **Backend-baked normals** | Avoids Three.js's vertex normal averaging which would smooth over detail. The backend's normals are computed after triangle orientation, so they're more accurate. |
| **Vertex-colour Phong material** | The PLY file already contains per-vertex region colours from the backend, so vertex colouring is both simpler and more efficient than texture mapping. Phong shading adds surface depth. |
| **Per-vertex region ID lookup** | O(1) lookup via array index — no spatial search needed at hover time. The array is ~150 k entries with Marching Cubes (larger than the ~20 k from Alpha Shapes), still small enough to fetch as part of the JSON. |
| **Separate highlight `useEffect`** | Decouples the highlight logic from the main Three.js setup effect, making it reactive to `highlightRegion` prop changes without tearing down the scene. |
| **`useCallback` for parent callbacks** | Prevents child component re-renders when the parent re-renders for unrelated state changes. |
| **No build-time static generation** | The page is `'use client'` because the Three.js scene requires browser APIs (`WebGLRenderer`, `requestAnimationFrame`). |
| **Single JSON data file** | Both `BrainViewer` and `ElectrodeSidebar` fetch the same `region_metadata.json` independently. The file is small and gets browser-cached on the first request. |
