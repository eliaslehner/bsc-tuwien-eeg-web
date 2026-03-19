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
│       ├── Timeline.jsx         Bottom panel: session events + epoch scrubber + playback
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

A `'use client'` component that composes the three-panel layout: `DatasetPanel` (left), `BrainViewer` (centre), and `Timeline` (bottom). Manages seven state variables:

- `eegData` — the loaded `eeg_data.json` (fetched on mount)
- `selectedClasses` — a `Set` of active motor imagery class IDs (all four enabled by default)
- `selectedBand` — `'mu'` or `'beta'` (default: `'mu'`)
- `currentTimeIndex` — index into the downsampled time array (drives the heatmap)
- `playing` — whether the timeline auto-advances
- `activeRegion` — brain region name from 3D hover
- `heatmapEnabled` — toggles between atlas region colours and ERD/ERS heatmap

All callbacks are wrapped in `useCallback` to avoid unnecessary child re-renders. The class toggle creates a new `Set` on each call so React detects the state change by reference.

#### `BrainViewer.jsx` — Three.js 3D Renderer + Heatmap

The base scene setup (renderer, camera, lights, controls, raycasting, SSAO post-processing) is unchanged from the previous version. The main additions are heatmap rendering and an enhanced tooltip.

**Heatmap Overlay**

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

**Enhanced Tooltip**

The hover handler now also checks `heatmapValuesRef` — a ref that stores the current per-region ERD/ERS values computed by the heatmap effect. When hovering in heatmap mode, the tooltip shows both the region name and the ERD/ERS percentage (e.g. `"L G_precentral (-23.4%)"` ).

**SSAO Post-Processing** and **backend-baked normals** are unchanged from the previous version.

#### `DatasetPanel.jsx` — Left Panel

Fetches its data from the `eegData` prop (loaded by `page.js`). Divided into four sections:

1. **Dataset Details** — grid showing name, subject ID, channel count, and sample rate. A `?` info popup shows the full dataset description text.
2. **Motor Imagery Classes** — four toggle buttons (left hand, right hand, feet, tongue), each with a coloured indicator dot matching the class colour, the class label, and a trial count (clean/total). Clicking a button toggles that class in the `selectedClasses` set. The heatmap shows the average across all selected classes.
3. **Frequency Band** — two toggle buttons for mu (8–13 Hz) and beta (13–30 Hz). Only one band is active at a time.
4. **Heatmap Toggle** — a single button that switches between atlas region colours and ERD/ERS heatmap mode.

#### `Timeline.jsx` — Bottom Panel

Contains two visualisation tracks and playback controls:

1. **Session events bar** — a thin horizontal track showing all 288 trial events from the recording session as coloured ticks. Each tick's horizontal position corresponds to its timestamp relative to the session duration, and its colour matches the motor imagery class. Events from deselected classes are hidden.
2. **Epoch scrubber** — an HTML `<input type="range">` slider spanning the epoch time window (−0.5 to 4.0 s). A semi-transparent overlay marks the baseline period, and a vertical line marks the cue onset at t=0. Dragging the slider updates `currentTimeIndex` which drives the brain heatmap. Below the slider, labels show the time axis bounds and the cue position.

A **play/pause button** (CSS-only triangle/bars, no emoji) auto-advances the time index at ~12.5 fps (80 ms interval) using `setInterval`. The current time in seconds is displayed on the right in monospace font.

The play button uses a `useRef` to track the current index inside the interval callback, avoiding the stale closure problem that would occur if it read `currentTimeIndex` directly from props.

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

##### `load_gdf(filepath)`

Loads a GDF file using `mne.io.read_raw_gdf` with `preload=True`. Returns the raw MNE object, the events array (extracted via `mne.events_from_annotations`), and the event_id mapping. MNE's GDF reader stores event types as string annotations (e.g. `'769'`), so the event_id dict maps these strings to MNE's internal integer codes.

##### `setup_channels(raw)`

Sets proper channel types on the raw object. The GDF files have 25 channels — the first 22 are EEG, the last 3 are EOG. Channel names may have `'EEG-'` or `'EOG-'` prefixes from the GDF header which are stripped. The EOG channels are marked with `raw.set_channel_types` so that MNE's artifact removal tools can identify them.

##### `extract_session_events(events, event_id, sfreq)`

Builds a list of motor imagery cue events with their sample positions and timestamps. Only events matching the four class codes (769–772) are included. This list is used by the frontend's session timeline to show coloured event markers across the recording duration.

##### `get_trial_counts(events, event_id)`

Counts total trials per class from the event stream. Used to populate the dataset metadata (e.g. "72 trials per class").

#### `processing.py`

##### `remove_eog_artifacts(raw, eeg_channels, eog_channels)`

Removes EOG contamination from the EEG using `mne.preprocessing.EOGRegression`, which fits a linear regression model of the 3 EOG channels onto the 22 EEG channels and subtracts the predicted EOG component. This is the approach recommended by the dataset documentation ("linear regression"). Falls back to a 2 Hz highpass filter if the regression fails (e.g. if the EOG channels are flat or missing).

##### `preprocess_raw(raw, eeg_channels, eog_channels)`

Runs the full preprocessing sequence: EOG artifact removal → pick EEG channels only → bandpass filter (0.5–40 Hz). The order matters — EOG regression needs both EEG and EOG channels present, so channel picking happens after.

##### `create_epochs(raw, events, event_id, tmin, tmax)`

Creates MNE `Epochs` around the motor imagery cue events (769–772) with the specified time window (default: −0.5 to +4.0 s relative to cue onset). The baseline period (−0.5 to 0 s) captures the fixation-cross rest state before the cue appears.

Artifact rejection works by finding all events with type 1023 (expert-marked rejected trials) in the original event stream, then identifying which epochs fall within the same trial window (±8 s). Those epochs are dropped via `epochs.drop()` with reason `'artifact'`.

##### `compute_band_erd_ers(epochs, l_freq, h_freq, baseline_tmin, baseline_tmax)`

Computes Event-Related Desynchronisation / Synchronisation (ERD/ERS) for a given frequency band. The steps are:

1. For each motor imagery class, select the corresponding epochs.
2. Bandpass filter the epochs to the target band (e.g. 8–13 Hz for mu).
3. Apply the Hilbert transform (`scipy.signal.hilbert`) to get the analytic signal, then take |analytic|² for instantaneous power.
4. Average power across all trials of that class.
5. Compute baseline power as the mean over the baseline time window.
6. Express ERD/ERS as percentage change: `(power − baseline) / baseline × 100`.

Negative values indicate desynchronisation (ERD), which is the expected pattern during motor imagery — the sensorimotor rhythm is suppressed when the subject imagines movement. Positive values indicate synchronisation (ERS), sometimes seen as a post-movement rebound.

Returns a dict mapping class names to (n_channels, n_times) arrays and the corresponding time vector.

##### `downsample_timecourse(data, times, n_bins)`

Downsamples the ERD/ERS time courses to a fixed number of bins (default 90) for JSON export. Uses `np.linspace` to pick evenly spaced indices from the full-resolution data. At 250 Hz with a 4.5 s epoch, the raw data has 1125 time points — downsampling to 90 bins (one every ~50 ms) keeps the JSON small (~128 KB total) while preserving the temporal structure.

#### `export.py`

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

The temporal envelope uses a sigmoid onset at ~0.3 s post-cue with exponential decay, matching the typical ERD time course observed in real motor imagery data. Channel lateralisation is determined by the electrode numbering convention (odd numbers = left hemisphere, even = right, `z` suffix = midline). Small Gaussian noise is added for visual realism.

Also generates 288 synthetic session events distributed across 6 runs with randomised inter-trial intervals.

##### `export_eeg_json(output_path, data)`

Writes the JSON to disk and reports the file size.

#### `__init__.py` — Pipeline Orchestrator

##### `run_eeg_pipeline(config, electrode_mappings)`

Top-level function called by `main.py`. The flow is:

1. Build the `channel_regions` dict from the electrode pipeline output.
2. Look for a GDF file at `{eeg_data_dir}/{eeg_subject}{eeg_session}.gdf`.
3. If found: load → preprocess → epoch → compute ERD/ERS for mu and beta bands → downsample → build JSON.
4. If not found: generate synthetic demo data.
5. Export to `frontend/public/data/eeg_data.json`.

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
| **Synthetic data fallback** | Lets the frontend be developed and tested without requiring the actual GDF files. The synthetic patterns are spatially and temporally realistic enough to verify the heatmap and timeline logic. |
| **Downsampling to 90 bins** | Keeps the JSON under 130 KB (22 channels × 90 times × 4 classes × 2 bands ≈ 15,840 values). The full 1125-sample resolution is unnecessary for the visualisation. |
| **Channel-to-region mapping from electrode pipeline** | Reuses the existing electrode → Destrieux region assignment rather than re-deriving it. Ensures consistency between the electrode metadata and the EEG heatmap. |
