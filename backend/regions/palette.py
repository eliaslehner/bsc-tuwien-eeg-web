import matplotlib
import numpy as np


def build_region_palette(names_map):
    """
    Build a colour palette for all region IDs in the atlas.

    Returns
    -------
    sorted_ids : list[int]
    full_names : dict[int, str]
    palette : np.ndarray (N, 3) — RGB colours in [0, 1]
    id_to_palette_idx : dict[int, int]
    """
    full_names = {0: "Unlabelled"}
    full_names.update(names_map)

    sorted_ids = sorted(full_names.keys())
    region_names = [full_names[u] for u in sorted_ids]
    n_regions = len(sorted_ids)

    cmap = matplotlib.colormaps.get_cmap('gist_ncar').resampled(n_regions)
    palette = cmap(np.linspace(0, 1, n_regions))[:, :3]

    # Make "Unlabelled" dark grey
    if region_names[0] == "Unlabelled":
        palette[0] = [0.15, 0.15, 0.15]

    id_to_palette_idx = {uid: idx for idx, uid in enumerate(sorted_ids)}
    return sorted_ids, full_names, palette, id_to_palette_idx
