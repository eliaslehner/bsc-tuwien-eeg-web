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
12. [EEG Processing — `eeg/`](#12-eeg-processing--eeg)

---

## Sources
- Nibabel: https://nipy.org/nibabel/manual.html#manual
- Nilearn: https://nilearn.github.io/stable/index.html
- Open3D: https://www.open3d.org/docs/release/
- scikit-image (Marching Cubes): https://scikit-image.org/docs/stable/api/skimage.measure.html#skimage.measure.marching_cubes
- MNE-Python: https://mne.tools/stable/index.html
- SciPy (Hilbert transform): https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.hilbert.html

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
│   ├── __init__.py          Pipeline orchestrator (run_eeg_pipeline)
│   ├── loader.py            GDF loading via MNE-Python
│   ├── processing.py        EOG removal, epoching, ERD/ERS
│   └── export.py            JSON builder + synthetic data generator
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
- **EEG Processing** — directory for GDF data files, subject/session identifiers, epoch time window (default −0.5 to 4.0 s), baseline window (−0.5 to 0 s), frequency band definitions (mu: 8–13 Hz, beta: 13–30 Hz), downsampling bin count (default 90), and output filename. These control the EEG processing pipeline in `backend/eeg/`.

Derived paths like `mapped_mesh_ply_path`, `output_json_path`, and `eeg_output_path` are computed as `@property` methods that join directory + filename.

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
5. **Electrode mapping & JSON export** — maps electrodes, reuses the pre-computed vertex region IDs, and writes `region_metadata.json`. The return value (electrode mappings) is captured and passed forward to step 6.
6. **EEG processing & export** — loads GDF data (or generates synthetic data), preprocesses, computes ERD/ERS, and writes `eeg_data.json`. Receives the electrode mappings from step 5 so it can build the channel-to-region mapping for the frontend heatmap.
7. **Optional viewer** — if `SHOW_VIEWER=true` in `.env`, launches the Open3D viewer.

### Design Decisions

| Decision | Rationale |
|---|---|
| **Single entry point** | `python -m backend.main` runs everything. No more remembering which script to run first. |
| **Forward-pass of vertex IDs** | `generate_and_export` returns the per-vertex region IDs which are passed directly to `run_electrode_pipeline`, avoiding redundant computation. |
| **Forward-pass of electrode mappings** | `run_electrode_pipeline` returns its output dict, and the `electrodes` list is passed to `run_eeg_pipeline` so the channel-to-region mapping doesn't need to be recomputed or read back from disk. |
| **Batch pre-computation instead of a runtime server** | The proposal mentioned a lightweight Flask/FastAPI server with REST or WebSocket delivery. The implemented system deliberately replaces that with static JSON exports because the thesis use-case is deterministic replay of recorded sessions, not live streaming. Pre-computation makes scrubbing instant and avoids server round-trips during the demo. |

---

## 11. Frontend — Browser 3D Brain Viewer

### Purpose

A Next.js web application that renders the Destrieux-mapped brain mesh in 3D with an EEG activity heatmap overlay. The user can rotate/zoom/pan the model, identify brain regions on hover, filter by motor imagery class, select a frequency band, and scrub through the averaged trial epoch to see how the ERD/ERS pattern evolves over time. A left panel shows dataset details and controls, the centre area contains the 3D viewer, and a bottom timeline provides session overview and epoch time scrubbing.

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
│   ├── layout.js              Root layout, metadata title/description
│   ├── page.js                 Main page, state management, three-panel layout
│   ├── globals.css              Full CSS design system
│   └── components/
│       ├── BrainViewer.jsx      Three.js 3D renderer + SSAO + heatmap overlay
│       ├── DatasetPanel.jsx     Left panel: dataset info, class filters, band selector
│       ├── Timeline.jsx         Bottom panel: zoomable epoch scrubber + playback
│       ├── TimelineCurves.jsx   Per-channel ERD/ERS curve visualisation
│       ├── TimelineHeatmap.jsx  Heatmap grid view for time-series data
│       ├── InfoPopup.jsx        Small "?" icon that opens an explanation popup
│       └── ElectrodeSidebar.jsx (kept but unused — was the old electrode list sidebar)
├── public/
│   └── data/
│       ├── brain_mesh_destrieux_mapped.ply   Coloured brain mesh
│       ├── region_metadata.json              Electrode + region data + vertex IDs
│       └── eeg_data.json                     EEG ERD/ERS data + session events
├── package.json
├── next.config.mjs
└── jsconfig.json
```

### Components

#### `page.js` — Application Root

A `'use client'` component that composes the three-panel layout: `DatasetPanel` (left), `BrainViewer` (centre), and `Timeline` (bottom). Manages twelve state variables:

- `eegData` — the loaded `eeg_data.json` (fetched on mount)
- `selectedClasses` — a `Set` of active motor imagery class IDs (all four enabled by default)
- `selectedBand` — `'mu'` or `'beta'` (default: `'mu'`)
- `currentTimeIndex` — index into the downsampled time array (drives the heatmap)
- `playing` — whether the timeline auto-advances
- `activeRegion` — brain region name from 3D hover
- `heatmapEnabled` — toggles between atlas region colours and ERD/ERS heatmap
- `selectedRuns` — a `Set` of run indices (0–5, all six enabled by default). Controls which of the 6 session runs contribute to the averaged ERD/ERS values.
- `contrastMode` — boolean, enables subtraction view (Class A − Class B) instead of averaging
- `contrastOrder` — two-element array `[classA, classB]` defining the subtraction order. Set automatically when exactly two classes are selected; reset to `[null, null]` otherwise.
- `erdThreshold` — number (0–50), hides ERD/ERS values whose absolute magnitude falls below this percentage, rendering them as neutral grey on the heatmap
- `multiView` — boolean, switches the 3D viewer from a single interactive camera to a three-panel split view (left hemisphere, top, right hemisphere)

A `useMemo` hook computes `activeData` — a filtered and re-aggregated version of `eegData` that only includes trials from the selected runs. This derived object is what gets passed to child components, so changing the run selection automatically updates the heatmap and timeline without re-fetching the JSON.

The page also includes a **help modal** (toggled by a `?` button in the header) that provides theory context about motor imagery, contralateral control, and ERD/ERS interpretation.

All callbacks are wrapped in `useCallback` to avoid unnecessary child re-renders. The class toggle creates a new `Set` on each call so React detects the state change by reference. Contrast mode is automatically disabled when `selectedClasses` size is not exactly 2.

#### `BrainViewer.jsx` — Three.js 3D Renderer + Heatmap

The base scene setup handles WebGL rendering, camera, lights, orbit controls, raycasting, and SSAO post-processing. The component accepts props for `eegData`, `selectedClasses`, `selectedBand`, `currentTimeIndex`, `heatmapEnabled`, `contrastMode`, `contrastOrder`, `erdThreshold`, and `multiView`.

**Heatmap and Contrast Overlay**

A dedicated `useEffect` reacts to changes in `heatmapEnabled`, `selectedClasses`, `selectedBand`, `currentTimeIndex`, and `eegData`. When the heatmap is enabled, it computes per-vertex colours via the `computeHeatmapColors` helper function:

1. For each of the 22 channels, average the ERD/ERS values across all selected classes at the current time index.
2. Map each channel to its brain region via the `channel_regions` dict from the EEG JSON.
3. For regions with multiple electrodes, average their values.
4. For each mesh vertex, look up its region ID (from `vertex_region_ids`), find the region's ERD/ERS value, and compute a colour from a diverging scale:
   - **Blue** (ERD / desynchronisation / negative values) — `rgb(0.10, 0.40, 0.90)` at maximum
   - **Dark grey** (neutral / zero) — `rgb(0.15, 0.15, 0.15)`
   - **Red** (ERS / synchronisation / positive values) — `rgb(0.90, 0.20, 0.10)` at maximum
5. Vertices in regions that have no electrode mapping stay dark grey (`rgb(0.12, 0.12, 0.12)`).

The colour scale is normalised to the maximum absolute value across all mapped regions, so the full blue-to-red range is always used regardless of the actual ERD/ERS magnitude.

When the heatmap is disabled, the original vertex colours (stored in `origColorsRef`) are restored.

**Contrast Subtraction Mode**

When `contrastMode` is enabled, the heatmap shows the difference between two classes instead of the average. The `contrastOrder` array `[classA, classB]` defines the subtraction — the per-channel ERD/ERS values of class B are subtracted from class A. This highlights regions where the two classes differ most (e.g. left vs right hand shows a strong lateralisation pattern).

**ERD Thresholding**

The `erdThreshold` prop suppresses small, insignificant ERD/ERS values. Any vertex whose region's absolute ERD/ERS value falls below the threshold is coloured as neutral dark grey (`rgb(0.2, 0.2, 0.2)`). This lets the user filter out noise and focus on the most active regions.

**Multi-Camera Split View**

When `multiView` is enabled, the renderer switches from the single interactive OrbitControls camera to a three-viewport layout rendered in a single frame. Each viewport has a fixed camera angle:
- **Left panel** — camera positioned on −X, looking at the right hemisphere
- **Centre panel** — camera positioned on +Y, looking down (top view)
- **Right panel** — camera positioned on +X, looking at the left hemisphere

The SSAO post-processing is disabled in multi-view mode (each viewport is rendered with a plain `renderer.render()` call). OrbitControls are also disabled since the cameras are fixed.

**Legend**

A DOM-based legend is rendered in the bottom-right of the viewer when the heatmap is enabled. It shows a vertical gradient bar from red (ERS, top) through grey (neutral) to blue (ERD, bottom), with labels and short descriptions. The legend uses `backdrop-filter: blur` styling consistent with the tooltip.

**Enhanced Tooltip**

The hover handler now also checks `heatmapValuesRef` — a ref that stores the current per-region ERD/ERS values computed by the heatmap effect. When hovering in heatmap mode, the tooltip shows both the region name and the ERD/ERS percentage (e.g. `"L G_precentral (-23.4%)"` ).

**SSAO Post-Processing** and **backend-baked normals** are unchanged from the previous version.

#### `DatasetPanel.jsx` — Left Panel

Fetches its data from the `eegData` prop (loaded by `page.js`). Receives props for all control state and setter callbacks (`selectedRuns`/`setSelectedRuns`, `contrastMode`/`setContrastMode`, `contrastOrder`/`setContrastOrder`, `erdThreshold`/`setErdThreshold`, `multiView`/`setMultiView`). Divided into five sections:

1. **Dataset Details** — grid showing name, subject ID, channel count, and sample rate. A `?` info popup shows the full dataset description text.
2. **Run Selector** — a row of six toggle buttons (R1–R6) that control which of the session's 6 runs are included in the ERD/ERS aggregation. Toggling a run adds/removes its index from the `selectedRuns` set, which propagates up to `page.js` where the `activeData` memo recomputes.
3. **Motor Imagery Classes** — four toggle buttons (left hand, right hand, feet, tongue). Clicking a button toggles that class in the `selectedClasses` set. Below this, an **Analysis Tools** subsection provides:
   - **Contrast Mode** — a checkbox that enables subtraction view. Automatically disabled (with a hint) when exactly two classes are not selected. When enabled, shows the current contrast order (e.g. "Left Hand − Right Hand") with a swap button to reverse the subtraction direction.
   - **ERD Threshold Slider** — a range input (0–50%) that hides low-magnitude ERD/ERS values on the heatmap. The current threshold value is shown as a label.
   - **Multi-View Toggle** — a checkbox that switches the 3D viewer to the three-panel split layout.
4. **Frequency Band** — two toggle buttons for mu (8–13 Hz) and beta (13–30 Hz). Only one band is active at a time.
5. **Heatmap Toggle** — ON/OFF button to switch between the atlas region colours and the ERD/ERS heatmap overlay.

#### `Timeline.jsx` — Bottom Panel

The timeline acts as the master timeline controller. It receives `contrastMode` and `contrastOrder` props from `page.js` and forwards them to child views. It manages several internal state variables:

- `viewMode` — `'curves'` or `'heatmap'`, toggled via a layout button
- `channelMode` — which channels to display: `'motor'` (C3, Cz, C4), `'all'` (all averaged), `'all_individual'` (all 22 as separate lines), or a specific channel name
- `stacked` — boolean, toggles between stacked (one lane per class) and overlay (all on same plot) layout in the curves view
- `speedIdx` — index into `SPEED_OPTIONS` array: 0.5×, 1×, 2×, 4× playback speed
- `zoomLevel` — index into `ZOOM_LEVELS = [1, 2, 4, 8]`

**Zoom** — The `visibleRange` is computed from `zoomLevel` and `currentTimeIndex`. At zoom level 1 (1×), the entire epoch is visible; at level 3 (8×), only 1/8 of the time points are shown, centred on the playhead. The zoom can be changed via +/− buttons or mouse wheel scroll on the timeline.

**Playback Controls** — A play/pause button, previous/next frame buttons, and a speed selector. The play interval uses `setInterval` with the duration from `SPEED_OPTIONS`. The play button uses a `useRef` to track the current index inside the interval callback, avoiding the stale closure problem.

**Epoch Scrubber** — A styled `<input type="range">` at the bottom spanning the full epoch (tmin to tmax). Dragging it updates `currentTimeIndex`. The current time in seconds is displayed in monospace font.

**Child Views** — Based on `viewMode`, the timeline renders either `TimelineCurves` or `TimelineHeatmap`, passing down `visibleRange`, `channelMode`, `stacked`, `contrastMode`, and `contrastOrder`.

#### `TimelineCurves.jsx` — Per-Channel ERD/ERS Curves

Canvas-based rendering of ERD/ERS time courses. Supports multiple viewing modes:

- **`motor`** — shows only C3, Cz, C4 (the primary sensorimotor channels)
- **`all`** — averages all 22 channels into a single curve per class
- **`all_individual`** — draws all 22 channels as separate lines per class, with hover detection that highlights the nearest electrode and shows a tooltip (`{channelName}: {value.toFixed(1)}%`)
- **Individual channel** — a specific channel name, showing just that channel's curve

**Layout modes:**
- **Stacked** — each selected class gets its own horizontal lane with independent Y-axis scaling
- **Overlay** — all classes plotted on the same axes with a shared Y scale

**Contrast curve** — when `contrastMode` is enabled, a dashed teal line (`#6ee7b7`) is drawn showing the Class A − Class B difference. In stacked mode this gets its own lane; in overlay mode it's drawn on top.

The drawing logic respects `visibleRange` so only the zoomed time window is rendered. A green vertical playhead line marks the current time index, with dots at the intersection of each curve. The helper function `niceStep(range, maxTicks)` computes clean axis tick intervals.

Clicking on the canvas jumps the playhead to that time point.

#### `TimelineHeatmap.jsx` — Channel × Time Heatmap Grid

Canvas-based rendering of a 2D grid with channels on the Y-axis and time on the X-axis. Each cell is coloured by its ERD/ERS value using a diverging blue–grey–red scale (the `erdToColor` function, same scheme as the 3D heatmap).

Channels are ordered by a fixed `CHANNEL_ORDER` array (Fz, FC3, FC1, FCz, FC2, FC4, C3, C1, Cz, C2, C4, C6, CP3, CP1, CPz, CP2, CP4, P3, Pz, P4, POz, Oz — front to back). Visual group separators (`GROUP_BREAKS` at indices [6, 13, 18]) divide the channels into frontal/central/centroparietal/parietal bands.

Features:
- **Channel labels** on the left with adaptive font sizing
- **Time axis** at the bottom with `niceStep`-computed tick labels
- **Cue line** — vertical dashed line at t=0 (cue onset)
- **Playhead** — solid vertical line at current time
- **Colour legend** — vertical gradient bar on the right side with ± percentage labels
- Only cells within `visibleRange` are rendered, adapting cell width to fill the canvas

Clicking jumps the playhead to that time point.

#### `InfoPopup.jsx` — Contextual Help

A small circular `?` button that opens an absolutely-positioned popup with explanatory text. Clicking outside the popup closes it (via a `mousedown` listener added in a `useEffect`). Used next to each section header in the dataset panel and in the timeline.

#### `ElectrodeSidebar.jsx` — (Unused)

The old electrode list sidebar is kept in the codebase but no longer imported by `page.js`. Hovering the brain still works via the tooltip — the sidebar is no longer needed for region identification.

### CSS Design System (`globals.css`)

The CSS was restructured for the three-panel layout.

| Element | Style |
|---|---|
| **Background** | `#0a0a0a` (near-black), borders `#222` |
| **Accent colour** | `#6ee7b7` (mint green) — used for active region text, tooltip text, hover borders, spinner, active band/heatmap buttons, slider thumb, time display |
| **Font** | `Segoe UI` / system-ui with `Consolas` / `Fira Code` for monospace elements (trial counts, time display) |
| **Layout** | Full-height flexbox column: header (fixed) → content (flex row: dataset panel + viewer, flex: 1) → timeline (fixed) |
| **Dataset panel** | Fixed 260px width, scrollable, sections separated by `#1a1a1a` borders |
| **Class buttons** | Flex row with coloured indicator, label, and trial count. Active state has green-tinted background |
| **Band/heatmap buttons** | Toggle style with active state using `#6ee7b7` accent border and text |
| **Info popup** | 18px circle with `?`, absolute-positioned dropdown on click, `box-shadow` for depth |
| **Timeline** | Bottom bar with play button (32px circle), two stacked tracks (session bar + epoch scrubber), time readout |
| **Epoch slider** | Custom-styled `<input type="range">` with `#6ee7b7` thumb, `#2a2a2a` track |
| **Run selector** | Flex row of R1–R6 buttons, green (`#6ee7b7`) highlight when active |
| **Analysis tools** | Grouped controls: checkbox styling with accent colour, slider with custom thumb/track, hint text for disabled states |
| **Contrast order** | Horizontal flex display showing `Class A − Class B` with a swap button |
| **Brain legend** | Bottom-right positioned, vertical gradient bar (red → grey → blue), `backdrop-filter: blur` |
| **Help modal** | Full-screen dialog with backdrop blur, card-based sections explaining motor imagery theory |
| **Timeline zoom** | +/− buttons and zoom level indicator in the timeline controls bar |
| **Timeline speed** | Speed selector button cycling through 0.5×–4× labels |
| **Loader** | Absolute overlay with CSS-only spinning border animation |
| **Tooltip** | `position: fixed`, `backdrop-filter: blur(8px)`, semi-transparent black background, rounded corners |
| **Transitions** | 0.15s ease on background, border-color, and color for interactive elements |

### Design Decisions

| Decision | Rationale |
|---|---|
| **Vanilla Three.js (no React-Three-Fiber)** | Lower abstraction overhead, easier to control the render loop and event handling, avoids extra dependencies for a single-mesh viewer. |
| **SSAO post-processing** | Makes the brain surface look more three-dimensional by darkening sulci (grooves). The brain mesh has lots of crevices that benefit from ambient occlusion. |
| **Backend-baked normals** | Avoids Three.js's vertex normal averaging which would smooth over detail. The backend's normals are computed after triangle orientation, so they're more accurate. |
| **Vertex-colour Phong material** | The PLY file already contains per-vertex region colours from the backend, so vertex colouring is both simpler and more efficient than texture mapping. Phong shading adds surface depth. |
| **Per-vertex region ID lookup** | O(1) lookup via array index — no spatial search needed at hover time. The array is ~150 k entries with Marching Cubes (larger than the ~20 k from Alpha Shapes), still small enough to fetch as part of the JSON. |
| **Separate heatmap `useEffect`** | Decouples the heatmap colouring from the main Three.js setup effect. The heatmap effect runs on every time/class/band change without tearing down the scene. |
| **Region-based heatmap (not interpolated)** | Each electrode maps to a Destrieux region, and all vertices in that region get the electrode's ERD/ERS value. This is simple and leverages the existing electrode-to-region mapping. Spatial interpolation (e.g. spherical splines) could be added later for smoother gradients. |
| **Diverging blue-red colour scale** | Matches the established EEG convention: blue for desynchronisation (ERD), red for synchronisation (ERS). The neutral centre is dark grey rather than white to fit the dark theme. |
| **`useCallback` for parent callbacks** | Prevents child component re-renders when the parent re-renders for unrelated state changes. |
| **Set for selectedClasses** | A `Set` provides O(1) `has`/`add`/`delete` for the class toggle. React detects state changes by reference, and the toggle callback always creates a new `Set`, so this works correctly with `useState`. |
| **Static JSON data files** | Both `region_metadata.json` and `eeg_data.json` are served as static files from `public/data/`. No running backend server is needed — the data is pre-computed when the pipeline runs. Files are small enough to browser-cache. |
| **No build-time static generation** | The page is `'use client'` because the Three.js scene requires browser APIs (`WebGLRenderer`, `requestAnimationFrame`). |
| **Info popups instead of dedicated panel** | Small `?` icons next to section headers open inline explanation text. This keeps the UI compact without needing a separate help panel or modal system. |
| **Run-level aggregation via `useMemo`** | The `activeData` memo recomputes whenever `selectedRuns` or `eegData` changes, filtering trial data before it reaches child components. This keeps the per-run selection logic in one place rather than spreading it across every consumer. |
| **Canvas-based timeline rendering** | `TimelineCurves` and `TimelineHeatmap` use `<canvas>` instead of SVG or DOM elements. Canvas handles the 22 channels × 90 time bins × multiple classes more efficiently than creating thousands of DOM nodes. |
| **Fixed channel ordering in heatmap** | The `CHANNEL_ORDER` array ensures a consistent front-to-back spatial layout regardless of the order channels appear in the JSON. Group breaks add visual structure matching the electrode montage topology. |
| **Zoom via `visibleRange`** | Instead of re-sampling data at different resolutions, the zoom simply narrows the index range that child components render. This is simpler and avoids data loss at high zoom. |

---

## 12. EEG Processing — `eeg/`

### Purpose

Processes EEG data from the BCI Competition IV 2a dataset (Graz motor imagery) and exports a JSON file that the frontend uses to render heatmaps, event timelines, and class-filtered visualisations. The module is designed to work in batch mode — all processing happens upfront when the pipeline runs, and the frontend fetches the pre-computed results as a static JSON file.

When no GDF data files are available, the module generates synthetic demo data with realistic spatial and temporal ERD/ERS patterns so the frontend can be developed and tested independently.

### Module Structure

```
backend/eeg/
├── __init__.py          Pipeline orchestrator (run_eeg_pipeline)
├── loader.py            GDF file loading via MNE-Python
├── processing.py        Preprocessing + feature extraction
└── export.py            JSON builder + synthetic data generator
```

### Dataset — BCI Competition IV 2a

The dataset contains cue-based motor imagery EEG from 9 subjects. Each subject performed four tasks: imagination of left hand movement (class 1), right hand (class 2), both feet (class 3), and tongue (class 4). Data was recorded with 22 Ag/AgCl EEG electrodes plus 3 EOG channels at 250 Hz. Each session consists of 6 runs with 48 trials per run (12 per class), totalling 288 trials per session. The trial timing is: fixation cross at t=0, cue arrow at t=2 s, motor imagery from t=2 s to t=6 s, break until ~t=8 s.

The data is stored in GDF format. Event types 769–772 mark the cue onsets for the four classes, and event type 1023 marks trials flagged as containing artifacts by expert scoring.

### Key Functions

#### `loader.py`

The module also defines two constants: `CLASS_INFO` — a dict mapping class names (`'left_hand'`, `'right_hand'`, `'feet'`, `'tongue'`) to their GDF event codes (769–772), display labels, and colours; and `STANDARD_EEG_CHANNELS` — the ordered list of the 22 standard 10-20 channel names used by the dataset.

##### `find_gdf_file(data_dir, subject, session)`

Looks for a GDF file matching the pattern `{subject}{session}.gdf` in the given directory. Returns the path if found, `None` otherwise.

##### `load_gdf(filepath)`

Loads a GDF file using `mne.io.read_raw_gdf` with `preload=True`. Returns the raw MNE object, the events array (extracted via `mne.events_from_annotations`), and the event_id mapping. MNE's GDF reader stores event types as string annotations (e.g. `'769'`), so the event_id dict maps these strings to MNE's internal integer codes.

##### `setup_channels(raw)`

Sets proper channel types and names on the raw object. The GDF files have 25 channels — the first 22 are EEG, the last 3 are EOG. The function unconditionally renames the first 22 channels to the known standard 10-20 names from `STANDARD_EEG_CHANNELS` and the last 3 to `EOG-left`, `EOG-central`, `EOG-right`. This is robust against varying GDF naming conventions — some files have `'EEG-'`/`'EOG-'` prefixes, others store duplicate `'EEG'` labels that MNE numbers as `EEG-0`, `EEG-1`, etc. The EOG channels are marked with `raw.set_channel_types` so that MNE's artifact removal tools can identify them.

##### `extract_session_events(events, event_id, sfreq)`

Builds a list of motor imagery cue events with their sample positions and timestamps. Only events matching the four class codes (769–772) are included. This list is used by the frontend's session timeline to show coloured event markers across the recording duration.

##### `get_trial_counts(events, event_id)`

Counts total trials per class from the event stream. Used to populate the dataset metadata (e.g. "72 trials per class").

#### `processing.py`

##### `remove_eog_artifacts(raw, eeg_channels, eog_channels)`

Removes EOG contamination from the EEG using `mne.preprocessing.EOGRegression`, which fits a linear regression model of the 3 EOG channels onto the 22 EEG channels and subtracts the predicted EOG component. This is the approach recommended by the dataset documentation ("linear regression"). Falls back to a 2 Hz highpass filter if the regression fails (e.g. if the EOG channels are flat or missing).

##### `preprocess_raw(raw, eeg_channels, eog_channels)`

Runs the full preprocessing sequence: EOG artifact removal → pick EEG channels only → **CAR re-referencing** → bandpass filter (0.5–40 Hz). The order matters — EOG regression needs both EEG and EOG channels present so channel picking happens after, and CAR must happen after picking so the average is computed over the 22 EEG channels only (not the EOG channels).

The CAR step (`raw.set_eeg_reference('average', projection=False)`) removes the hardware left-mastoid reference bias that is baked into the raw recordings. Without it, right-hemisphere amplitudes are systematically inflated relative to left-hemisphere amplitudes, which would cause the ERD/ERS heatmap to be asymmetric purely due to the reference geometry rather than any real lateralised brain activity.

##### `create_epochs(raw, events, event_id, tmin, tmax)`

Creates MNE `Epochs` around the motor imagery cue events (769–772) with the specified time window (default: −0.5 to +4.0 s relative to cue onset). The baseline period (−0.5 to 0 s) captures the fixation-cross rest state before the cue appears.

Artifact rejection works by finding all events with type 1023 (expert-marked rejected trials) in the original event stream, then identifying which epochs fall within the same trial window (±8 s). Those epochs are dropped via `epochs.drop()` with reason `'artifact'`.

##### `compute_band_erd_ers(epochs, l_freq, h_freq, baseline_tmin, baseline_tmax)`

Computes Event-Related Desynchronisation / Synchronisation (ERD/ERS) for a given frequency band. The steps are:

1. For each motor imagery class, select the corresponding epochs.
2. Bandpass filter the epochs to the target band (e.g. 8–13 Hz for mu).
3. Apply the Hilbert transform (`scipy.signal.hilbert`) to get the analytic signal, then take |analytic|² for instantaneous power.
4. Computes per-trial power and per-trial baseline power over the baseline time window, rather than averaging across all trials initially.
5. Compute baseline power as the mean over the baseline time window per trial. The baseline is clamped to `np.finfo(float).tiny` (~2.2e-308) to prevent division by zero without distorting near-zero baselines.
6. Express ERD/ERS as percentage change: `(power − baseline) / baseline × 100` for each trial.

Negative values indicate desynchronisation (ERD), which is the expected pattern during motor imagery — the sensorimotor rhythm is suppressed when the subject imagines movement. Positive values indicate synchronisation (ERS), sometimes seen as a post-movement rebound.

Returns a dict mapping class names to per-trial `(n_trials, n_channels, n_times)` arrays and the corresponding time vector.

##### `get_class_epoch_counts(epochs)`

Returns a dict mapping class event IDs to the number of clean (non-dropped) epochs per class. Used to populate the `clean_counts` field in the exported JSON, which the frontend displays as "X/Y trials" in the class buttons.

##### `downsample_timecourse(data, times, n_bins)`

Downsamples the ERD/ERS time courses to a fixed number of bins (default 90) for JSON export. Uses `np.linspace` to pick evenly spaced indices from the full-resolution data. It robustly supports trailing dimensions when slicing time points, ensuring it can gracefully handle the new per-trial `(n_trials, n_channels, n_times)` array shapes alongside averages. At 250 Hz with a 4.5 s epoch, the raw data has 1125 time points — downsampling to 90 bins (one every ~50 ms) keeps the JSON small (~128 KB total) while preserving the temporal structure.

#### `export.py`

##### `build_channel_regions(electrode_mappings)`

Converts the electrode pipeline output (list of electrode mapping dicts) into a `channel_regions` dict that maps each channel name to its Destrieux region ID and name. This is the bridge between the electrode pipeline (step 5) and the EEG pipeline (step 6).

##### `build_eeg_json(dataset_info, session_events, erd_ers_data, channel_regions)`

Assembles the complete JSON structure that the frontend consumes. The structure contains:

- `dataset` — metadata (name, subject, sample rate, channels, per-class trial counts)
- `trial_timeline` — epoch time window and baseline period
- `events` — all 288 session events with timestamps and class labels
- `erd_ers` — per-band (mu, beta) ERD/ERS data as 2D arrays [n_channels × n_times] for each class
- `channel_regions` — maps each channel name to its Destrieux region ID and name (from the electrode pipeline)

All numpy arrays are converted to nested Python lists with values rounded to 2 decimal places.

##### `generate_synthetic_data(channels, channel_regions)`

Generates realistic-looking synthetic ERD/ERS data when no GDF files are available. The synthetic patterns model the known spatial characteristics of motor imagery:

- **Left hand imagery** — contralateral ERD over right hemisphere channels (C4, FC4, CP4)
- **Right hand imagery** — contralateral ERD over left hemisphere channels (C3, FC3, CP3)
- **Feet imagery** — ERD concentrated over central/midline channels (Cz, FCz, CPz)
- **Tongue imagery** — more distributed, weaker pattern

It now generates this data on a per-trial basis (e.g. `n_sim_trials=68` per class) with a higher per-trial noise level for added visual realism, returning properly nested arrays with fixes around the `clean_counts` metric. The temporal envelope uses a sigmoid onset at ~0.3 s post-cue with exponential decay, matching the typical ERD time course observed in real motor imagery data. Channel lateralisation is determined by the electrode numbering convention (odd numbers = left hemisphere, even = right, `z` suffix = midline).

Also generates 288 synthetic session events distributed across 6 runs with randomised inter-trial intervals.

##### `export_eeg_json(output_path, data)`

Writes the JSON to disk and reports the file size.

#### `__init__.py` — Pipeline Orchestrator

##### `run_eeg_pipeline(config, electrode_mappings)`

Top-level function called by `main.py`. Delegates to `_process_gdf` for real data or `generate_synthetic_data` for demo data. The flow is:

1. Build the `channel_regions` dict from the electrode pipeline output.
2. Look for a GDF file at `{eeg_data_dir}/{eeg_subject}{eeg_session}.gdf`.
3. If found: load → preprocess → epoch → compute ERD/ERS for mu and beta bands → downsample → build JSON.
4. If not found: generate synthetic demo data.
5. Export to `frontend/public/data/eeg_data.json`.

##### `_process_gdf(config, gdf_path, channel_regions)`

Internal helper that handles the real-data path: loads the GDF file, runs preprocessing (EOG removal → channel picking → CAR → bandpass), creates epochs, computes ERD/ERS for both mu and beta bands, downsamples, and assembles the JSON structure. Separated from `run_eeg_pipeline` to keep the orchestrator readable.

The `electrode_mappings` parameter comes from step 5 of the main pipeline (electrode mapping). It provides the channel → brain region association that the frontend needs to map per-channel ERD/ERS values onto the 3D brain mesh.

### Configuration Fields

| Field | Default | Description |
|---|---|---|
| `EEG_DATA_DIR` | `./data/eeg` | Directory containing GDF files |
| `EEG_SUBJECT` | `A01` | Subject ID (A01–A09) |
| `EEG_SESSION` | `T` | Session type (T = training, E = evaluation) |
| `EEG_EPOCH_TMIN` | `−0.5` | Epoch start relative to cue (seconds) |
| `EEG_EPOCH_TMAX` | `4.0` | Epoch end relative to cue (seconds) |
| `EEG_BASELINE_TMIN` | `−0.5` | Baseline window start (seconds) |
| `EEG_BASELINE_TMAX` | `0.0` | Baseline window end (seconds) |
| `EEG_DOWNSAMPLE_BINS` | `90` | Number of time bins in exported JSON |
| `EEG_OUTPUT_FILENAME` | `eeg_data.json` | Output filename |

The mu (8–13 Hz) and beta (13–30 Hz) band ranges are defined as Python tuples in the Config dataclass and are not configurable via `.env`.

### Design Decisions

| Decision | Rationale |
|---|---|
| **Batch processing, not streaming** | All EEG data is processed when the backend pipeline runs. The frontend fetches the pre-computed JSON as a static file. This avoids the complexity of a running backend server while keeping frontend interactions instant after the initial load. |
| **Hilbert transform for band power** | More computationally efficient than Morlet wavelets for the visualisation use case. Gives a smooth instantaneous power estimate suitable for the ~50 ms time resolution of the exported data. |
| **EOG regression over ICA** | Linear regression is simpler, faster, and recommended by the dataset documentation. ICA would require manual component inspection which doesn't fit an automated pipeline. |
| **CAR re-referencing before bandpass** | The dataset was recorded with a left-mastoid hardware reference, which artificially inflates right-hemisphere amplitudes. Re-referencing to the common average removes this bias before any power computation. CAR is applied after channel picking so the average is computed over only the 22 EEG channels. |
| **Synthetic data fallback** | Lets the frontend be developed and tested without requiring the actual GDF files. The synthetic patterns are spatially and temporally realistic enough to verify the heatmap and timeline logic. |
| **Downsampling to 90 bins** | Keeps the JSON under 130 KB (22 channels × 90 times × 4 classes × 2 bands ≈ 15,840 values). The full 1125-sample resolution is unnecessary for the visualisation. |
| **Channel-to-region mapping from electrode pipeline** | Reuses the existing electrode → Destrieux region assignment rather than re-deriving it. Ensures consistency between the electrode metadata and the EEG heatmap. |
