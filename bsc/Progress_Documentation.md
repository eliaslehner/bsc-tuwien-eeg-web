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
