# Documentation and Notes for the written Part

## Mapping regions of the brain - 6.02.2026

**cortical = relating to the outer layer of the cerebrum (cerebrum = (big)brain)**

To map regions of the brain to be able to show a `lighting up`-effect in the browser later on I first had to do some research.

I googled for mapping brain regions and came across the keyword `atlas`.

From there I looked up what an atlas is and searched for libraries.

I came across `FreeSurfer` as a software and `nilearn` as a python library.

Because `FreeSurfer` is far larger in size to download and the documentation for the mapping of brain regions found under the name `Cortical Parcellation` on their website under `https://surfer.nmr.mgh.harvard.edu/fswiki/CorticalParcellation` which basically has the atlas saved in a file and the documentation even specifies the path to access three different atlas types, I decided to first check out the library `nilearn` as it is far more efficient to just install a package via pip to test this idea. The website of nilearn shows an example for loading and plotting of a cortical surface atlas, accessed under `https://nilearn.github.io/stable/auto_examples/01_plotting/plot_surf_atlas.html`.

I chose to map regions in volumetric (voxel) space first, then convert to a point cloud — rather than the other way around. This is more accurate because:
- The Destrieux 2009 atlas is a volumetric MNI-space atlas (3D NIfTI), so resampling it directly onto the subject's NIfTI grid with nearest-neighbour interpolation preserves crisp label boundaries.
- Approximating region boundaries after converting to a point cloud would introduce spatial error from the jitter and centring transforms.

I initially looked at the Harvard-Oxford atlas but ended up going with the Destrieux 2009 atlas (`nilearn.datasets.fetch_atlas_destrieux_2009` with `lateralized=True`) because it gives a much finer parcellation — it has around 150 regions compared to Harvard-Oxford's 48 cortical + 21 subcortical. More regions means more granular mapping which is better for the lighting up effect later.

The pipeline in `BrainRegions.py` works like this:

1. Load the skull-stripped `.nii` file and also load it as a tensor (same way `PointCloud.py` does it) so we can compute the exact same centroid that was subtracted during point cloud generation.
2. Fetch the Destrieux 2009 atlas with `nilearn.datasets.fetch_atlas_destrieux_2009` and resample it into the subject's voxel space using `nilearn.image.resample_to_img` with `interpolation='nearest'`.
3. Gap-fill unlabelled brain voxels: some voxels inside the brain mask end up with no atlas label (label 0) because the atlas doesn't perfectly cover every voxel after resampling. To fix this I use `scipy.ndimage.distance_transform_edt` to find the nearest labelled voxel for each unlabelled one and copy that label over. This fills in the gaps so there are no holes in the region mapping.
4. Build a colour palette using the `gist_ncar` colormap, one unique colour per region. Unlabelled voxels (if any remain) get dark grey.
5. For each `.ply` file exported by `PointCloud.py`: load the vertices, reverse the transforms that were applied during export (un-flip Y axis, un-center by adding back the centroid), round to nearest voxel index, look up the atlas label, and assign the corresponding colour.
6. Export the coloured point cloud or mesh as a new `.ply` file into `assets/brainmapping_exports/`.

The tricky part was reversing the transforms from `PointCloud.py`. That script centers the points by subtracting the mean and flips the Y axis. So in `BrainRegions.py` I have to undo those in reverse order — first un-flip Y (negate it again), then add the centroid back. The centroid is recomputed from the same NIfTI volume with the same threshold so it matches exactly.

## Viewer script

Also wrote a small `Viewer.py` script that lets you quickly view any of the exported `.ply` files without having to re-run the whole pipeline. It can load from both the `pointcloud_exports` and `brainmapping_exports` directories. If there are multiple files it gives you a numbered list to pick from or you can view them all sequentially. Supports both point clouds and triangle meshes — it checks if there are triangles in the file and renders accordingly. Nothing fancy, just a convenience thing so I dont have to open meshlab or something every time I want to check the output.

## Mapping EEG electrodes to brain regions - 25.02.2026

The next step after having the atlas-coloured brain mesh was to figure out which brain region each of the 22 EEG electrodes from the BCI Competition 2008 dataset maps to. This is needed so that later in the browser I can show which electrodes sit above which cortical area.

The core problem is that EEG electrodes sit on the scalp — they are outside the skull-stripped brain volume. So if you just take an electrode's MNI coordinate and look up the atlas label at that voxel you will get nothing, because that position is in air (outside the brain). To solve this I used a ray-casting approach: for each electrode I shoot a ray from its scalp position inward toward the centre of the brain volume, stepping in half-voxel increments along that ray until the first labelled voxel is hit. That voxel's Destrieux region becomes the electrode's assignment.

The electrode coordinates come from MNE-Python's built-in `standard_1020` montage. MNE provides the positions in metres (MNI space), so before using the NIfTI affine to convert to voxel indices I multiply by 1000 to get millimetres. The inverse of the NIfTI affine then maps from MNI-mm into voxel (i, j, k) space.

I reused the same atlas loading and gap-filling logic from `BrainRegions.py` — fetch the Destrieux 2009 atlas, resample it into subject space with nearest-neighbour interpolation, and fill any unlabelled brain voxels using scipy's Euclidean distance transform. This guarantees every brain voxel has a region label, so the inward ray is certain to hit something.

Besides the electrode-to-region mapping I also mapped every vertex of the exported PLY mesh to its atlas region. This is needed so the browser viewer can identify which region the user is hovering over. The trick is to reverse the transforms that `PointCloud.py` applied during export — un-flip the Y axis (negate it again) and add back the centroid. The centroid is recomputed from the same NIfTI with the same threshold to make sure it matches exactly. After reversing the transforms each vertex is back in voxel space, so I round to the nearest integer index, clamp to volume bounds, and read the atlas label.

The output is a single JSON file (`region_metadata.json`) that contains: an array of all Destrieux regions with their ID, name and colour; an array of the 22 electrodes with their MNI coordinates, voxel hit-point, region ID and region name; a mapping of region IDs to their electrode lists; and the per-vertex region ID array for the full mesh. This one file is all the browser needs.

The colour palette uses the same `gist_ncar` colourmap approach as `BrainRegions.py` so the colours are consistent between the Python viewer and the browser.

## Frontend browser viewer - 25.02.2026

For the browser-based viewer I set up a Next.js project (v16) with React 19 and Three.js. The idea was to keep it simple — no extra UI libraries, just plain CSS and vanilla Three.js via the `three` npm package.

The app has two main components: `BrainViewer` and `ElectrodeSidebar`, composed together in `page.js`. The page manages two pieces of state — `activeRegion` (set by hovering on the brain) and `sidebarRegion` (set by hovering in the sidebar). The sidebar hover takes priority so that when you hover an electrode group in the sidebar the corresponding region lights up on the brain.

`BrainViewer` sets up a standard Three.js scene: a WebGL renderer, a perspective camera, two directional lights plus an ambient light for even illumination, and `OrbitControls` for rotate/zoom/pan. The PLY mesh is loaded with Three.js's built-in `PLYLoader`. After loading I compute the bounding box to automatically position the camera at a good viewing distance.

For hover detection I use Three.js raycasting. On every `mousemove` event the mouse position is converted to normalised device coordinates, a ray is cast into the scene, and if it hits the brain mesh I look up the vertex index of the hit face. That vertex index is used to index into the `vertex_region_ids` array from the metadata JSON to find the region ID, which is then resolved to a region name. A tooltip follows the cursor showing the region name.

When a region is hovered from the sidebar, the `highlightRegion` prop triggers a `useEffect` that recolours the mesh: vertices belonging to the target region get a bright green-ish highlight colour (`#6ee7b7`), and all other vertices are dimmed to 15% of their original brightness. When the hover ends, the original vertex colours are restored from a stored `Float32Array` copy. This gives a clear visual indication of where each electrode group sits on the cortex.

`ElectrodeSidebar` fetches the same `region_metadata.json` and groups the electrodes by their region name. Each group shows the region name with the electrode channel names as small chip-style labels below it. Hovering a group or chip fires `onSidebarHover`, which propagates back through the page state to `BrainViewer`.

The CSS follows a dark theme (background `#0a0a0a`, borders in `#222`) to match the kind of dark-on-dark look you would expect for a medical visualisation tool. The layout uses flexbox — the sidebar is a fixed 280px on the right, the 3D viewer fills the rest. A loading spinner overlay shows while the PLY file is being fetched and parsed. The tooltip is styled as a floating pill with a blurred background.

## Backend refactoring into a Python package - 10.03.2026

The four standalone scripts (`PointCloud.py`, `BrainRegions.py`, `ElectrodeMapping.py`, `Viewer.py`) were getting messy, with lots of duplicated code (the NIfTI loading was copy-pasted in three places, the centroid computation was in two places, the palette building was in two places) and you had to remember to run them in the right order.

I restructured everything into a proper Python package under `backend/`. The scripts were split into focused modules: `model/loader.py` for NIfTI loading, `model/pointcloud.py` for mesh generation, `regions/atlas.py` for the Destrieux atlas fetching and gap-fill, `regions/palette.py` for the colour palette, `regions/mapping.py` for the old PLY vertex mapping, `electrode/mapping.py` for the electrode-to-region mapping and JSON export, and `viewer/viewer.py` for the Open3D viewer.

There is now a `main.py` that runs the full pipeline end-to-end with `python -m backend.main`. No more running scripts individually.

I also added a `Config` dataclass in `config.py` that reads all configuration from a `.env` file. Every path, threshold, parameter, and feature flag is now configurable without editing source code. The device selection now supports CUDA too (the old code only checked for MPS), with an `auto` mode that picks the best available option.

The data inputs changed too. Instead of using a single skull-stripped NIfTI (`A00063008_NFB3_T1w_brain.nii`), the pipeline now loads the full T1w volume (`A00063008_NFB3_T1w.nii`) and applies a separate brain mask (`A00063008_NFB3_T1w_brainmask.nii`). The `load_masked_volume` function multiplies them together and normalises only the brain voxels. This gives a sharper masking boundary which produces a cleaner isosurface with Marching Cubes.

## Switching from Alpha Shapes to Marching Cubes for mesh generation - 10.03.2026

This was the biggest technical change. The old pipeline generated a point cloud by thresholding voxels, adding random jitter, and then wrapping a surface around it using Open3D's Alpha Shapes. This worked but had problems:
- The mesh quality depended heavily on the jitter noise and the alpha parameter.
- There was no direct correspondence between mesh vertices and the original voxel grid, so mapping atlas regions required reverse-transforming vertices back to voxel space and hoping they landed on the right label.
- Alpha Shapes can leave holes or produce overly smooth surfaces depending on the parameter.

I switched to Marching Cubes from scikit-image (`skimage.measure.marching_cubes`). Marching Cubes extracts an isosurface directly from the 3D volume at a given intensity level. The big advantage is that the vertices come out already in voxel space, so I can assign atlas region IDs right there before doing any transforms. I call this "forward-carry" , the region IDs travel forward with the vertices through the centering and Y-flip transforms, instead of being looked up after the fact by reversing those transforms.

For vertices that land on unlabelled atlas voxels (label 0), I wrote a mesh-adjacency-based gap-fill instead of using the volumetric EDT approach. For each unlabelled vertex it looks at its mesh neighbours (adjacent triangles) and takes the most common non-zero label. This works better than EDT for isosurface vertices because they don't sit on a regular voxel grid.

One thing I had to fix was the face winding. When you flip the Y axis (`verts[:, 1] = -verts[:, 1]`), the mesh handedness inverts, meaning all the normals end up pointing inward. The fix is to reverse the face winding order (`faces[:, ::-1]`) before recomputing normals. I also call `mesh.orient_triangles()` to ensure consistent outward-facing winding.

I added optional mesh decimation via Open3D's `simplify_quadric_decimation`. The Marching Cubes output can have a lot more faces than needed, so this lets you set a target face count in the `.env` file. Decimation happens in voxel space before region assignment, so the simplified vertices still map accurately to atlas labels.

The `generate_and_export` function now returns the per-vertex region ID list, which gets passed directly to the electrode pipeline. This means `electrode/mapping.py` can skip the expensive reverse-transform re-mapping of mesh vertices entirely.

## Frontend enhancements — SSAO and glow overlay - 10.03.2026

Two visual improvements to `BrainViewer.jsx`:

**SSAO (Screen-Space Ambient Occlusion):** The old version rendered the scene with a single `renderer.render()` call. I added a Three.js post-processing pipeline using `EffectComposer` with an `SSAOPass`. This darkens the sulci (grooves) on the brain surface, which adds a lot of visual depth. The parameters (`kernelRadius: 12`, `kernelSize: 64`, `intensity: 1.2`) are tuned for the scale of the brain mesh. One important detail: I had to set `ssaoPass.normalMaterial.side = THREE.DoubleSide` to match the brain mesh material, otherwise the SSAO depth pass culls back-faces and creates dark see-through artifacts.

**Glow overlay highlight:** The old highlight effect dimmed all non-target vertices to 15% brightness and recoloured target vertices green. This made the rest of the brain nearly invisible. The new approach uses two meshes: the main mesh goes semi-transparent (`opacity: 0.25`) and a separate glow overlay mesh (cloned geometry, emissive material) is shown on top. Only vertices belonging to the highlighted region keep their real positions; all other vertices are collapsed to the origin so their triangles become degenerate and invisible. The emissive material (`emissive: [0.25, 0.55, 0.45]`, `emissiveIntensity: 0.6`) gives the highlighted region a nice glow effect that looks much cleaner than the old dimming approach.

I also changed the normal handling. Instead of always calling `geometry.computeVertexNormals()` after loading the PLY, the frontend now checks if the PLY already has normals baked in by the backend. The backend writes per-vertex normals after `orient_triangles()` and `compute_vertex_normals()`, so they're higher quality than what Three.js would compute on its own (which just averages face normals).

## EEG processing pipeline and frontend overhaul - 19.03.2026

This was the big missing piece — the `backend/eeg/` module was just a placeholder `__init__.py` until now. The goal was to load the actual BCI Competition IV 2a EEG data (or generate realistic synthetic data when the GDF files aren't available), process it into something the browser can visualise, and build out the frontend to match the layout I sketched in the Browser Layout PDF.

### Backend — EEG processing

The BCI Competition IV 2a dataset uses GDF files, which MNE-Python can read directly with `mne.io.read_raw_gdf`. Each file has 25 channels — 22 EEG electrodes in the 10-20 system plus 3 EOG channels for artifact removal. The events are stored as annotations in the GDF and MNE extracts them as string keys (`'769'`, `'770'`, etc.) mapped to internal integer codes. This string-key quirk is important because when you create epochs you have to use the string form, not the original GDF integer.

I split the EEG code into three modules:

**`loader.py`** handles GDF loading and event extraction. One thing I had to deal with was the channel naming — GDF files from this dataset sometimes have `'EEG-'` prefixes on the channel names (like `'EEG-Fz'` instead of just `'Fz'`), so `setup_channels` strips those and also sets the last 3 channels to `'eog'` type so MNE knows what they are.

**`processing.py`** does the actual signal processing. For EOG artifact removal I used `mne.preprocessing.EOGRegression` which fits a linear regression of the 3 EOG channels onto the EEG and subtracts the predicted component. The dataset documentation specifically recommends linear regression as one of the methods, and it's simpler than ICA (which would need manual component inspection). If the regression fails for whatever reason (flat EOG channels, etc.), it falls back to a 2 Hz highpass filter which at least removes the slow EOG drifts.

The preprocessing order matters: EOG regression first (needs both EEG and EOG channels in the raw), then pick only the 22 EEG channels, then bandpass filter 0.5–40 Hz. After that I create epochs from −0.5 to +4.0 s relative to the cue onset. The −0.5 to 0 s window is the baseline period (fixation cross, no motor imagery yet).

For artifact trials — the dataset marks rejected trials with event type 1023. I find those events and check which of my cue-onset epochs fall within an 8 s window of a rejection marker, then drop those epochs. It's not perfectly precise (the 1023 event might not be at exactly the same sample as the cue) but the 8 s window is wide enough to catch it.

The actual feature extraction uses the Hilbert transform approach: bandpass filter the epochs to the target frequency band (mu: 8–13 Hz, beta: 13–30 Hz), apply `scipy.signal.hilbert` to get the analytic signal, square the absolute value for instantaneous power, average across trials per class, then express as ERD/ERS percentage relative to the baseline. I chose Hilbert over Morlet wavelets because it's faster and gives a clean time-varying power estimate that's good enough for visualisation. The full-resolution data has 1125 samples per epoch (250 Hz × 4.5 s) which I downsample to 90 time bins for the JSON — one every ~50 ms, keeps the file at ~128 KB.

**`export.py`** builds the JSON and also has the synthetic data generator. When no GDF files are in `data/eeg/`, the pipeline generates fake-but-realistic ERD/ERS patterns. The synthetic data models the known spatial properties of motor imagery: left hand imagination produces contralateral ERD over right hemisphere channels (C4, FC4, CP4), right hand over left hemisphere, feet over midline (Cz, FCz, CPz), and tongue is more distributed. The lateralisation is derived from the channel naming convention — odd-numbered electrodes are left hemisphere, even are right, and channels ending in `z` are midline. The temporal shape is a sigmoid onset with exponential decay, which matches the typical ERD time course.

The orchestrator in `__init__.py` ties it all together: it receives the electrode mappings from step 5 of the main pipeline (so it knows which channel maps to which Destrieux region) and either processes a real GDF or generates synthetic data, then exports to `frontend/public/data/eeg_data.json`.

I also added 10 new configuration fields to `config.py` for the EEG processing — data directory, subject/session selection, epoch window, baseline window, frequency bands, downsampling, and output filename. The pipeline in `main.py` is now 6 steps instead of 5, with step 6 being the EEG processing. The electrode output from step 5 is captured and passed forward so the channel-to-region mapping doesn't need to be re-read from disk.

### Frontend — new three-panel layout

The old layout was just the 3D brain viewer with a sidebar listing electrodes grouped by region. The new layout matches the PDF sketch: a left panel for dataset details and controls, the 3D viewer in the centre, and a timeline at the bottom.

**`DatasetPanel.jsx`** (left panel) shows the dataset metadata (name, subject, channel count, sample rate) in a compact grid layout. Below that are four toggle buttons for the motor imagery classes — each button has a coloured indicator dot, the class label, and the trial count showing clean/total. Clicking a class toggles it in and out of the heatmap average. Below that is the frequency band selector (mu vs beta) and a heatmap on/off toggle. Each section has a small `?` icon that opens an explanation popup.

**`Timeline.jsx`** (bottom) has two tracks stacked vertically. The top one is a thin session events bar that shows all 288 trial events as tiny coloured ticks spread across the recording duration — this gives a visual sense of the session structure. The bottom track is the epoch time scrubber, which is just a styled `<input type="range">` from −0.5 to 4.0 s. A dark overlay marks the baseline period and a vertical line marks the cue onset at t=0. There's a play/pause button that auto-advances the time at ~12 fps so you can watch the heatmap animate through the trial. For the play icon I used pure CSS (a border-based triangle for play, two bars for pause) instead of emoji since the design should stay clean.

One thing I had to handle in the timeline was the stale closure problem with `setInterval`. The play interval captures the `currentTimeIndex` from props, but since it's in a closure it would always see the same value. I fixed it with a ref (`indexRef`) that's updated on every render, so the interval callback always reads the latest index.

**`BrainViewer.jsx`** got the heatmap overlay added as a new `useEffect`. The `computeHeatmapColors` function takes the vertex region IDs (from `region_metadata.json`), the EEG data, and the current UI state (selected classes, band, time index), then builds a `Float32Array` of RGB values. For each vertex it looks up the region ID, checks if any electrode maps to that region, gets the ERD/ERS value, and computes a colour from a diverging blue-grey-red scale. Blue for desynchronisation (negative ERD), red for synchronisation (positive ERS), dark grey for neutral or unmapped regions. The scale auto-normalises to the maximum absolute value so the full colour range is always used.

The tooltip now also shows the ERD/ERS percentage when you hover in heatmap mode — it reads from a `heatmapValuesRef` that's updated by the heatmap effect. So you see something like `"L G_precentral (-23.4%)"` which is useful for understanding the spatial pattern.

**`InfoPopup.jsx`** is a tiny component — just a circular `?` button that toggles a popup with descriptive text. Clicking outside closes it via a `mousedown` listener. I use it next to every section header in the dataset panel and in the timeline for contextual help.

The old `ElectrodeSidebar.jsx` is still in the codebase but no longer imported. The hover-to-identify-region functionality still works through the tooltip on the brain itself, which was always independent of the sidebar.

**`globals.css`** was rewritten for the new layout. The main structural change is that `.content` is now a flex row with the dataset panel (fixed 260px) and the viewer (flex: 1), and the timeline sits below as a fixed-height bar. The class filter buttons, band selector, heatmap toggle, and info popup all have new styles following the same dark theme (background `#1a1a1a`, borders `#2a2a2a`, accent `#6ee7b7`). The epoch slider is custom-styled with a green thumb and dark track. Everything uses the same 0.15s transitions as before.

## EEG re-referencing fix — CAR before ERD/ERS — 23.03.2026

The dataset documentation (`Dataset_Desc_2a.md`) states that the EEG was recorded monopolarly with the left mastoid as the hardware reference. This means every electrode's voltage is actually the potential difference between that site and the left ear. The practical effect is an asymmetry: electrodes on the right hemisphere (physically far from the reference) have artificially inflated amplitudes, while left-hemisphere electrodes are attenuated. If you compute ERD/ERS on mastoid-referenced data your brain heatmap will look like the right hemisphere is systematically more active than the left, not because of any motor imagery effect but purely because of the reference geometry.

The fix is to re-reference to a **Common Average Reference (CAR)** before the Hilbert transform. CAR replaces each electrode's voltage with the difference between that electrode and the instantaneous mean across all 22 EEG channels. This removes the left-mastoid bias because the mean reference is spatially symmetric across the scalp — no single hemisphere is systematically boosted or suppressed.

In `processing.py` I added `raw.set_eeg_reference('average', projection=False, verbose=False)` to `preprocess_raw`, inserted after picking the 22 EEG channels (so the mean is computed only over EEG, not EOG) and before the bandpass filter (so the filter operates on the already-corrected signal). The `projection=False` flag applies the reference directly to the data rather than storing it as an MNE projector, which keeps the rest of the pipeline simpler.

An even stronger fix would be a Surface Laplacian (Current Source Density) transform, which not only removes the reference but also spatially sharpens the signal by suppressing volume conduction. That could be added later if the heatmap spatial resolution needs to improve, but CAR is the correct minimum step.

## Advanced Frontend Analysis and Per-Trial Processing - 24.03.2026

The next step was to provide more granular data analysis by transitioning from averaged ERD/ERS to a per-trial level. To support this, I updated the backend to output per-trial ERD/ERS data. Specifically, `compute_band_erd_ers` was changed to compute power and baseline per-trial, returning per-trial arrays. The `downsample_timecourse` function was also updated to reliably support trailing dimensions when slicing time points. For development, the synthetic ERD/ERS generator now generates 68 simulated trials per class with a higher per-trial noise level for added realism, and I fixed a bug related to `clean_counts`.

On the frontend, this new per-trial data allowed for significantly richer analysis tools:

**BrainViewer Updates:**
- **Contrast Subtraction Mode:** Added a mode to compute the difference between classes, rather than just showing their average.
- **ERD Thresholding:** Implemented a threshold logic to treat small, insignificant ERD/ERS values as visually neutral grey, highlighting the most relevant patterns. Missing data is now coloured securely as neutral grey.
- **Multi-Camera Rendering (Split View):** Enhanced the renderer to support a split 3-view showing the brain from the left, top, and right simultaneously, alongside a simple legend. 

**Dataset Panel & Controls:**
- In the `DatasetPanel`, I added new UI controls for the new features. Users can now select specific runs, toggle the contrast mode (and swap the contrast order), adjust the ERD threshold via a slider, and easily toggle the new multi-view layout.

**Timeline Redesign:**
- The timeline was significantly upgraded to better navigate the trial data. I removed the old session view to focus on the epoch bounds, adding wheel zoom functionality that creates a dynamic `visibleRange` window. This `visibleRange` is passed down to child views for synchronous updating.
- `TimelineHeatmap` now only renders the data within the `visibleRange` time window, properly adapting cell sizing and mapping to fill the view.
- `TimelineCurves` gained support for showing all 22 individual channel lines simultaneously (`all_individual`), including hover tooltips that identify specific electrodes. I also improved stacked and overlay visualisations and added support for an optional difference (contrast) curve matching the 3D brain view. The drawing logic dynamically respects the `visibleRange` and the interactive playhead.

**Run Selection & Data Aggregation:**
- Added a run selector (R1–R6 buttons) in the DatasetPanel so users can include/exclude individual runs from the analysis. The `page.js` root component computes an `activeData` object via `useMemo` that aggregates only the trials belonging to selected runs. This derived data is what all child components receive, so toggling a run instantly updates the heatmap, curves, and heatmap grid.

**Playback Speed Selector:**
- The timeline play button now supports four speed settings (0.5×, 1×, 2×, 4×) via a speed button that cycles through the options. The `setInterval` duration is adjusted accordingly.

**TimelineHeatmap Channel Ordering:**
- The heatmap grid uses a fixed `CHANNEL_ORDER` array that arranges the 22 channels from frontal to posterior (Fz → FC → C → CP → P → POz → Oz). Visual group separators at indices [6, 13, 18] divide the channels into anatomical bands (frontocentral / central / centroparietal / parietal). A vertical colour legend on the right side shows the blue–grey–red gradient with percentage labels.

**Help Modal:**
- Added a help button in the header that opens a full-screen modal dialog explaining the theory behind motor imagery, contralateral control, and ERD/ERS interpretation. The modal uses card-based sections and is styled with backdrop blur to keep the dark theme consistent.

**Legend for the 3D Viewer:**
- When the heatmap is enabled, a DOM-based legend appears in the bottom-right of the BrainViewer showing the diverging colour scale (red = ERS at top, grey = neutral, blue = ERD at bottom) with labels.

Overall, these updates tighten the connection between the backend's data extraction and the frontend's visualisations. The per-trial capabilities, along with zooming, contrast views, and electrode-specific details, transform the tool into a much more robust analytical dashboard.

## Baseline floor fix and channel naming robustness - 06.04.2026

Two small but important fixes:

**Baseline floor was too large:** In `compute_band_erd_ers`, the baseline power denominator was clamped with `np.maximum(baseline, 1e-10)` to avoid division by zero. The problem was that `1e-10` is actually quite large relative to the scale of EEG power values — a near-zero baseline would get inflated to `1e-10`, producing artificially small ERD/ERS percentages. Changed the floor to `np.finfo(float).tiny` (~2.2e-308), which is effectively the smallest representable positive float. This only prevents actual zero division without distorting the calculation.

**GDF channel naming robustness:** The `setup_channels` function in `loader.py` was updated to handle a wider range of GDF channel naming conventions. The old code assumed channel names had `'EEG-'` or `'EOG-'` prefixes and just stripped those. In practice, some GDF files store all channels as duplicate `'EEG'` labels, causing MNE to assign running numbers (`EEG-0`, `EEG-1`, …). The new code unconditionally renames the first 22 channels to the known standard 10-20 names from `STANDARD_EEG_CHANNELS`, and the last 3 to `EOG-left`, `EOG-central`, `EOG-right`. This is more robust because it doesn't depend on what names the GDF header happens to use.

## Region misplacement fix — subject↔MNI registration, production flip, electrode mapping & midline mirroring - 12.06.2026

While making the figures for the paper I noticed the parcellation was off — the big superior frontal gyrus (`g_front_sup`) looked shifted across the top of the cortex into the other hemisphere's `g_front_sup`. That is the kind of thing that's easy to spot in a figure and bad for a thesis, so I went back into the backend to find out whether it came from the gap-fill or from how the atlas is put onto the brain.

**Diagnosis.** It's the registration, not the gap-fill. `regions/atlas.py` aligns the MNI152 Destrieux atlas to the subject with `nilearn.image.resample_to_img`, which only uses the stored NIfTI affines — there is no actual registration/warp. The NFBS brain (`A00063008`) is in native scanner space, sitting ~36 mm anterior of MNI, so the atlas lands misaligned: only ~28 % of brain voxels get a label and ~51 % of the atlas labels fall *outside* the brain mask. The gap-fill then nearest-neighbour-smears those misplaced labels across the cortex, which is what drags `g_front_sup` over the midline. So gap-fill is the visible trigger but the missing registration is the root cause. I added a one-line `registration_coverage()` health print to step 2 and a stand-alone `backend/testing/diag_registration.py` that quantifies the offset (centre-of-mass distance, outside-mask %, per-region world-x), for the write-up.

**Comparison views.** To make this debuggable — and to compare in the same viewer I screenshot — the pipeline now exports a set of views: pre-gap (raw atlas, holes left grey), current/production, and a reference view (`model/template.py`) that renders Destrieux on the MNI152 template brain it was defined on (the ground truth). The Open3D viewer got a `compare_views` / `--compare` mode that shows them side by side in one window, all in the same orientation, so I can directly see whether the shift comes before or after the gap-fill and whether it tracks the registration.

**The fix.** I added `regions/registration.py`, which uses ANTs (the `antspyx` wheel — one dependency, no system install) to register the MNI152 template to the subject and warp the atlas into the subject's voxel space. This keeps the individual brain shape from Marching Cubes and only moves the labels to the right place. Affine is the default (`REGISTRATION_TRANSFORM=Affine`); switching to nonlinear is a one-flag change to `SyN`. Affine alone drops the outside-mask fraction from 50.8 % to ~1.4 % and cleanly separates the two hemispheres' `g_front_sup`.

**Production flip.** The registered atlas is now the production parcellation: the canonical `brain_mesh_destrieux_mapped.ply`, `region_metadata.json` and `eeg_data.json` the frontend loads are generated from it, so the frontend automatically shows the corrected mapping. The old affine-only output is kept as `*_unregistered` backups (a backup mesh plus `region_metadata.unregistered.json`) so I can still make before/after figures. `USE_REGISTRATION` defaults to true; if `antspyx` isn't installed it degrades to the old affine-only surface.

**Electrode mapping.** The same native-as-MNI assumption was also corrupting the electrodes — Cz (the vertex) was landing in the frontal lobe. The electrode→region question is really an atlas-space one (the montage and the atlas are both in MNI/head space; the subject brain is just the canvas), so I now map electrodes against the native Destrieux atlas and project each one radially onto the nearest cortical crown instead of ray-casting to the volume centre. The sensorimotor strip now comes out right (C3 → L postcentral, C1 → L precentral, C2 → R precentral, C4 → R postcentral), which is what matters for the motor-imagery ERD/ERS. Two honest caveats I kept in the code and the docs: the MNE `standard_1020` positions are scalp points ~10–25 mm outside the cortex (not cortical MNI), and a truly midline electrode's L-vs-R hemisphere is inherently ambiguous in a lateralised atlas — the region is meaningful, the side isn't.

**Midline mirroring (frontend).** To handle that midline ambiguity in the visualisation, I added a "Mirror" toggle in the header (next to the help button, on by default). When on, each midline electrode's value is applied to *both* the left and right mirror regions instead of an arbitrary side. The mirroring happens inside the region averaging in `BrainViewer.jsx` (the value goes into both region buckets), so there's no left/right bias and the colour normalisation stays consistent. I verified it in the browser: with only Cz active it lights both paracentral regions symmetrically with the toggle on, and only the left one with it off.

## Finishing touches for a presentable viewer — surface Laplacian, exemplar subject, nonlinear registration - 13.06.2026

With the pipeline functionally complete, this round was about bringing the output up to a finished-product standard — sharper spatial localisation, a clean default recording, and the most faithful atlas placement — and backing each choice with a small reproducible benchmark so it can be justified in the write-up rather than just asserted. All three were upgrades the codebase already anticipated.

**Surface Laplacian (CSD) reference.** Back on 23.03 I noted that a Surface Laplacian / Current Source Density transform would be the stronger successor to CAR once spatial resolution mattered. For a presentable viewer it does, so I followed through: `preprocess_raw` now takes a `reference` argument and defaults to `csd`. CSD is reference-free and spatially sharpening — it suppresses volume conduction and localises focal sensorimotor (de)synchronisation, which gives crisp contralateral hand ERD and a clean central foot ERD on the heatmap. The path is pick EEG → standard 10-05 montage → `compute_current_source_density` → bandpass; explicit EOG regression is dropped here because the Laplacian already attenuates the frontal EOG far-field. CAR stays available as `reference='car'` for comparison.

**Exemplar subject selection (A03).** The viewer loads one session by default, so it should be a clean, representative recording. I added `backend/eeg/select_subject.py`, which runs the production pipeline over every subject and scores each on motor-imagery quality — contralateral hand-ERD depth (left→C4, right→C3), correct-sign central foot ERD, and artifact load. Subject A03 comes out cleanest by a clear margin (score −118.9; textbook lateralisation with right-hand C3 ≈ −68 %) and is now the default. Its `--plot` option writes a benchmark figure and CSV (`bsc/figures/subject_selection_benchmark.*`) and a short write-up lives in `bsc/EEG_Subject_Selection.md`. I cross-checked the processing against the dataset's official MATLAB export (it reproduces it to the decimal) and confirmed A03's pattern replicates on its held-out evaluation session.

**Nonlinear registration (SyN).** The registration module always supported a one-flag switch from the default affine transform to nonlinear SyN. To get the most anatomically faithful parcellation for the finished figures I benchmarked both with `backend/regions/benchmark_registration.py`, measuring the share of atlas labels that land outside the brain mask: 50.8 % unregistered → 1.6 % Affine → **0.3 % SyN**. SyN costs a one-time ~+14 s, which is irrelevant for a viewer that serves static files, so I made it the default (`REGISTRATION_TRANSFORM=SyN`) and regenerated the production mesh and `region_metadata.json` from it. The comparison figure (`bsc/figures/registration_benchmark.png`) goes into the thesis assets.

Each of the three now has a committed benchmark figure, so the design choices are documented and reproducible rather than taken on faith.
