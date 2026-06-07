"""Benchmark Alpha Shapes against Marching Cubes for the EEG brain mesh.

This script adapts the benchmark brief from the older project versions into a
single runner in the latest repository. It ports the V1/V2 Alpha Shapes mesh
path, uses the latest repository's NFBS data and Marching Cubes parameters, and
writes CSV/PDF/LaTeX outputs that can be used in the thesis.

Typical use from the repository root:

    .\.venv\Scripts\python.exe benchmark_mesh.py --runs 5

Use ``--skip-atlas`` for a faster mesh-only run when region-label metrics are
not needed.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = ROOT / "graphics"
DEFAULT_BRAIN_NII = ROOT / "data" / "nfbs" / "A00063008_NFB3_T1w_brain.nii"
DEFAULT_T1W_NII = ROOT / "data" / "nfbs" / "A00063008_NFB3_T1w.nii"
DEFAULT_MASK_NII = ROOT / "data" / "nfbs" / "A00063008_NFB3_T1w_brainmask.nii"

OLD_VERSION_PROVENANCE = {
    "alpha_shapes_v1": {
        "folder": r"C:\Users\lenny\Desktop\VS Code\BSc-EEG_01\scripts",
        "mesh_file": "PointCloud.py",
        "region_file": "BrainRegions.py",
    },
    "alpha_shapes_v2": {
        "folder": r"C:\Users\lenny\Desktop\VS Code\BSc-EEG_02\scripts",
        "mesh_file": "PointCloud.py",
        "region_file": "BrainRegions.py",
    },
    "marching_cubes_v3": {
        "folder": r"C:\Users\lenny\Desktop\VS Code\BSc-EEG_03\backend",
        "mesh_file": "model/pointcloud.py",
        "config_file": "config.py",
    },
}

SUMMARY_METRICS = [
    "pointcloud_time_s",
    "normal_estimation_time_s",
    "mesh_time_s",
    "decimation_time_s",
    "region_assignment_time_s",
    "raw_vertices",
    "raw_faces",
    "decimated_vertices",
    "decimated_faces",
    "unlabelled_before_fill_pct",
    "unlabelled_after_fill_pct",
    "non_manifold_edges",
    "edge_manifold",
    "watertight",
]

CSV_FIELDS = [
    "algorithm",
    "source_version",
    "run",
    "seed",
    "threshold",
    "position_noise",
    "alpha",
    "mc_level",
    "mc_step_size",
    "mesh_target_faces",
    *SUMMARY_METRICS,
]

PIPELINE_STAGES = [
    ("pointcloud_time_s", "Point cloud + jitter"),
    ("normal_estimation_time_s", "Normal estimation"),
    ("mesh_time_s", "Mesh extraction"),
    ("decimation_time_s", "Decimation"),
    ("region_assignment_time_s", "Region assignment"),
]


@dataclass(frozen=True)
class BenchmarkConfig:
    brain_nii: Path
    t1w_nii: Path
    mask_nii: Path
    output_dir: Path
    runs: int
    threshold: float
    position_noise: float
    alpha: float
    normal_radius: float
    normal_max_nn: int
    mc_level: float
    mc_step_size: int
    mesh_target_faces: int
    seed: int
    skip_atlas: bool
    no_plots: bool
    sensitivity: bool
    alpha_values: list[float]
    noise_values: list[float]
    mc_levels: list[float]
    max_alpha_points: int


def parse_float_list(value: str) -> list[float]:
    """Parse a comma-separated float list for sensitivity sweeps."""
    values = [item.strip() for item in value.split(",") if item.strip()]
    if not values:
        raise ValueError("expected at least one float")
    return [float(item) for item in values]


def coerce_optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric):
        return None
    return numeric


def summarize_by_algorithm(
    rows: Iterable[dict[str, Any]], metric_names: Iterable[str]
) -> dict[str, dict[str, float]]:
    """Group benchmark rows by algorithm and compute mean/sample std metrics."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["algorithm"]), []).append(row)

    summary: dict[str, dict[str, float]] = {}
    for algorithm, algorithm_rows in grouped.items():
        values: dict[str, float] = {"runs": float(len(algorithm_rows))}
        for metric in metric_names:
            numeric_values = [
                value
                for value in (
                    coerce_optional_float(row.get(metric)) for row in algorithm_rows
                )
                if value is not None
            ]
            if not numeric_values:
                values[f"{metric}_mean"] = math.nan
                values[f"{metric}_std"] = math.nan
                continue
            values[f"{metric}_mean"] = statistics.fmean(numeric_values)
            values[f"{metric}_std"] = (
                statistics.stdev(numeric_values) if len(numeric_values) > 1 else 0.0
            )
        summary[algorithm] = values
    return summary


def format_latex_number(value: Any, precision: int = 2) -> str:
    numeric = coerce_optional_float(value)
    if numeric is None:
        return "--"
    if precision == 0:
        return f"{numeric:,.0f}"
    return f"{numeric:,.{precision}f}"


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_summary_csv(
    path: Path, summary: dict[str, dict[str, float]], metric_names: list[str]
) -> None:
    fieldnames = ["algorithm", "runs"]
    for metric in metric_names:
        fieldnames.extend([f"{metric}_mean", f"{metric}_std"])

    rows = []
    for algorithm, values in summary.items():
        rows.append({"algorithm": algorithm, **values})
    write_csv(path, rows, fieldnames)


def write_latex_table(path: Path, summary: dict[str, dict[str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    def metric(algorithm: str, name: str) -> float | None:
        return summary.get(algorithm, {}).get(f"{name}_mean")

    lines = [
        r"\begin{tabular}{lrr}",
        r"\toprule",
        r"Metric & Alpha Shapes & Marching Cubes \\",
        r"\midrule",
        (
            "Mesh generation time (s) & "
            f"{format_latex_number(metric('alpha_shapes', 'mesh_time_s'))} & "
            f"{format_latex_number(metric('marching_cubes', 'mesh_time_s'))} \\\\"
        ),
        (
            "Raw vertices & "
            f"{format_latex_number(metric('alpha_shapes', 'raw_vertices'), 0)} & "
            f"{format_latex_number(metric('marching_cubes', 'raw_vertices'), 0)} \\\\"
        ),
        (
            "Raw faces & "
            f"{format_latex_number(metric('alpha_shapes', 'raw_faces'), 0)} & "
            f"{format_latex_number(metric('marching_cubes', 'raw_faces'), 0)} \\\\"
        ),
        (
            "Decimated faces & "
            f"{format_latex_number(metric('alpha_shapes', 'decimated_faces'), 0)} & "
            f"{format_latex_number(metric('marching_cubes', 'decimated_faces'), 0)} \\\\"
        ),
        (
            "Unlabelled vertices after fill (\\%) & "
            f"{format_latex_number(metric('alpha_shapes', 'unlabelled_after_fill_pct'))} & "
            f"{format_latex_number(metric('marching_cubes', 'unlabelled_after_fill_pct'))} \\\\"
        ),
        (
            "Non-manifold edges & "
            f"{format_latex_number(metric('alpha_shapes', 'non_manifold_edges'), 0)} & "
            f"{format_latex_number(metric('marching_cubes', 'non_manifold_edges'), 0)} \\\\"
        ),
        r"\bottomrule",
        r"\end{tabular}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def validate_input_paths(config: BenchmarkConfig) -> None:
    for label, path in (
        ("brain NIfTI", config.brain_nii),
        ("T1w NIfTI", config.t1w_nii),
        ("brain mask NIfTI", config.mask_nii),
    ):
        if not path.exists():
            raise FileNotFoundError(f"Missing {label}: {path}")


def load_masked_t1w(t1w_path: Path, mask_path: Path) -> tuple[Any, Any, Any]:
    import nibabel as nib
    import numpy as np

    t1w_nii = nib.load(str(t1w_path))
    mask_nii = nib.load(str(mask_path))

    t1w_data = t1w_nii.get_fdata().astype("float32")
    mask = mask_nii.get_fdata() > 0

    masked = t1w_data * mask
    brain_values = masked[mask]
    vmin = float(brain_values.min())
    vmax = float(brain_values.max())
    if vmax > vmin:
        masked = (masked - vmin) / (vmax - vmin)
        masked[~mask] = 0.0
    return t1w_nii, masked.astype("float32"), mask


def load_atlas(brain_nii_path: Path, brain_mask: Any) -> tuple[Any, dict[str, Any]]:
    import nibabel as nib

    from backend.regions.atlas import fetch_and_resample_atlas, gap_fill_labels

    brain_nii = nib.load(str(brain_nii_path))
    atlas_volume, names_map = fetch_and_resample_atlas(brain_nii)
    filled_atlas, gap_stats = gap_fill_labels(atlas_volume, brain_mask)
    return filled_atlas, {"names": len(names_map), **gap_stats}


def maybe_limit_points(points: Any, max_points: int, seed: int) -> Any:
    if max_points <= 0 or len(points) <= max_points:
        return points

    import numpy as np

    rng = np.random.default_rng(seed)
    keep = rng.choice(len(points), size=max_points, replace=False)
    keep.sort()
    return points[keep]


def sample_alpha_points(
    volume: Any,
    threshold: float,
    position_noise: float,
    seed: int,
    max_points: int,
) -> tuple[Any, Any]:
    """Port V1/V2 PointCloud.py sampling, jitter, centering, and Y flip."""
    import numpy as np

    indices = np.argwhere(volume > threshold).astype("float32")
    raw_centroid = indices.mean(axis=0)
    points = maybe_limit_points(indices.copy(), max_points=max_points, seed=seed)

    if position_noise > 0:
        rng = np.random.default_rng(seed)
        points += rng.uniform(-position_noise, position_noise, size=points.shape)

    points -= points.mean(axis=0)
    points[:, 1] = -points[:, 1]
    return points, raw_centroid


def create_open3d_mesh(vertices: Any, faces: Any) -> Any:
    import open3d as o3d

    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(vertices)
    mesh.triangles = o3d.utility.Vector3iVector(faces)
    return mesh


def mesh_quality(mesh: Any) -> dict[str, Any]:
    try:
        non_manifold_edges = mesh.get_non_manifold_edges(allow_boundary_edges=False)
    except TypeError:
        non_manifold_edges = mesh.get_non_manifold_edges()

    try:
        edge_manifold = mesh.is_edge_manifold(allow_boundary_edges=False)
    except TypeError:
        edge_manifold = mesh.is_edge_manifold()

    return {
        "non_manifold_edges": int(len(non_manifold_edges)),
        "edge_manifold": int(bool(edge_manifold)),
        "watertight": int(bool(mesh.is_watertight())),
    }


def decimate_if_needed(mesh: Any, target_faces: int) -> tuple[Any, float]:
    faces = len(mesh.triangles)
    if target_faces <= 0 or faces <= target_faces:
        return mesh, 0.0
    start = time.perf_counter()
    decimated = mesh.simplify_quadric_decimation(target_faces)
    return decimated, time.perf_counter() - start


def map_alpha_regions(vertices_centered: Any, raw_centroid: Any, atlas_volume: Any) -> Any:
    import numpy as np

    points = vertices_centered.copy()
    points[:, 1] = -points[:, 1]
    points += raw_centroid

    voxel_ijk = np.round(points).astype("int64")
    for dim in range(3):
        voxel_ijk[:, dim] = np.clip(voxel_ijk[:, dim], 0, atlas_volume.shape[dim] - 1)
    return atlas_volume[voxel_ijk[:, 0], voxel_ijk[:, 1], voxel_ijk[:, 2]]


def map_marching_regions(vertices_voxel: Any, faces: Any, atlas_volume: Any) -> tuple[Any, Any]:
    from backend.model.pointcloud import (
        assign_vertex_region_ids,
        fill_unlabelled_from_neighbours,
    )

    before_fill = assign_vertex_region_ids(vertices_voxel, atlas_volume)
    after_fill = fill_unlabelled_from_neighbours(before_fill, faces)
    return before_fill, after_fill


def label_stats(before_fill: Any | None, after_fill: Any | None) -> dict[str, Any]:
    import numpy as np

    if before_fill is None or after_fill is None:
        return {
            "unlabelled_before_fill_pct": None,
            "unlabelled_after_fill_pct": None,
        }

    n_vertices = len(before_fill)
    if n_vertices == 0:
        return {
            "unlabelled_before_fill_pct": None,
            "unlabelled_after_fill_pct": None,
        }

    return {
        "unlabelled_before_fill_pct": 100.0 * float(np.sum(before_fill == 0)) / n_vertices,
        "unlabelled_after_fill_pct": 100.0 * float(np.sum(after_fill == 0)) / n_vertices,
    }


def run_alpha_once(
    volume: Any,
    atlas_volume: Any | None,
    config: BenchmarkConfig,
    run_number: int,
    seed: int,
    alpha: float | None = None,
    position_noise: float | None = None,
) -> dict[str, Any]:
    import numpy as np
    import open3d as o3d

    alpha_value = config.alpha if alpha is None else alpha
    noise_value = config.position_noise if position_noise is None else position_noise

    start = time.perf_counter()
    points, raw_centroid = sample_alpha_points(
        volume,
        threshold=config.threshold,
        position_noise=noise_value,
        seed=seed,
        max_points=config.max_alpha_points,
    )
    pointcloud_time = time.perf_counter() - start

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)

    start = time.perf_counter()
    pcd.estimate_normals(
        search_param=o3d.geometry.KDTreeSearchParamHybrid(
            radius=config.normal_radius,
            max_nn=config.normal_max_nn,
        )
    )
    normal_time = time.perf_counter() - start

    start = time.perf_counter()
    mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_alpha_shape(
        pcd,
        alpha_value,
    )
    mesh.compute_vertex_normals()
    mesh_time = time.perf_counter() - start

    raw_vertices = len(mesh.vertices)
    raw_faces = len(mesh.triangles)
    mesh, decimation_time = decimate_if_needed(mesh, config.mesh_target_faces)

    vertices = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.triangles)

    region_time = None
    before_fill = None
    after_fill = None
    if atlas_volume is not None:
        start = time.perf_counter()
        before_fill = map_alpha_regions(vertices, raw_centroid, atlas_volume)
        after_fill = before_fill
        region_time = time.perf_counter() - start

    return {
        "algorithm": "alpha_shapes",
        "source_version": "BSc-EEG_01/BSc-EEG_02 PointCloud.py port",
        "run": run_number,
        "seed": seed,
        "threshold": config.threshold,
        "position_noise": noise_value,
        "alpha": alpha_value,
        "mc_level": None,
        "mc_step_size": None,
        "mesh_target_faces": config.mesh_target_faces,
        "pointcloud_time_s": pointcloud_time,
        "normal_estimation_time_s": normal_time,
        "mesh_time_s": mesh_time,
        "decimation_time_s": decimation_time,
        "region_assignment_time_s": region_time,
        "raw_vertices": raw_vertices,
        "raw_faces": raw_faces,
        "decimated_vertices": int(len(vertices)),
        "decimated_faces": int(len(faces)),
        **label_stats(before_fill, after_fill),
        **mesh_quality(mesh),
    }


def run_marching_once(
    volume: Any,
    atlas_volume: Any | None,
    config: BenchmarkConfig,
    run_number: int,
    seed: int,
    mc_level: float | None = None,
) -> dict[str, Any]:
    import numpy as np
    from skimage.measure import marching_cubes

    level = config.mc_level if mc_level is None else mc_level

    start = time.perf_counter()
    verts, faces, _normals, _values = marching_cubes(
        volume,
        level=level,
        step_size=config.mc_step_size,
    )
    mesh_time = time.perf_counter() - start

    raw_vertices = len(verts)
    raw_faces = len(faces)
    mesh = create_open3d_mesh(verts, faces)
    mesh, decimation_time = decimate_if_needed(mesh, config.mesh_target_faces)

    verts_after = np.asarray(mesh.vertices)
    faces_after = np.asarray(mesh.triangles)

    region_time = None
    before_fill = None
    after_fill = None
    if atlas_volume is not None:
        start = time.perf_counter()
        before_fill, after_fill = map_marching_regions(
            verts_after,
            faces_after,
            atlas_volume,
        )
        region_time = time.perf_counter() - start

    mesh.compute_vertex_normals()

    return {
        "algorithm": "marching_cubes",
        "source_version": "latest backend/model/pointcloud.py",
        "run": run_number,
        "seed": seed,
        "threshold": None,
        "position_noise": None,
        "alpha": None,
        "mc_level": level,
        "mc_step_size": config.mc_step_size,
        "mesh_target_faces": config.mesh_target_faces,
        "pointcloud_time_s": 0.0,
        "normal_estimation_time_s": 0.0,
        "mesh_time_s": mesh_time,
        "decimation_time_s": decimation_time,
        "region_assignment_time_s": region_time,
        "raw_vertices": raw_vertices,
        "raw_faces": raw_faces,
        "decimated_vertices": int(len(verts_after)),
        "decimated_faces": int(len(faces_after)),
        **label_stats(before_fill, after_fill),
        **mesh_quality(mesh),
    }


def write_mesh_time_plot(path: Path, summary: dict[str, dict[str, float]]) -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    algorithms = ["alpha_shapes", "marching_cubes"]
    labels = ["Alpha Shapes", "Marching Cubes"]
    means = [summary.get(a, {}).get("mesh_time_s_mean", math.nan) for a in algorithms]
    stds = [summary.get(a, {}).get("mesh_time_s_std", 0.0) for a in algorithms]

    fig, ax = plt.subplots(figsize=(5.5, 3.6))
    colors = ["#4c78a8", "#f58518"]
    ax.bar(labels, means, yerr=stds, capsize=5, color=colors, edgecolor="#222222")
    ax.set_ylabel("Mesh generation time (s)")
    ax.set_title("Alpha Shapes vs Marching Cubes")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def write_pipeline_plot(path: Path, summary: dict[str, dict[str, float]]) -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    algorithms = ["alpha_shapes", "marching_cubes"]
    labels = ["Alpha Shapes", "Marching Cubes"]
    colors = ["#4c78a8", "#72b7b2", "#f58518", "#54a24b", "#b279a2"]

    fig, ax = plt.subplots(figsize=(7.0, 3.7))
    y_positions = np.arange(len(algorithms))
    left = np.zeros(len(algorithms))

    for idx, (metric, label) in enumerate(PIPELINE_STAGES):
        values = [
            summary.get(algorithm, {}).get(f"{metric}_mean", 0.0)
            for algorithm in algorithms
        ]
        values = [0.0 if math.isnan(value) else value for value in values]
        ax.barh(
            y_positions,
            values,
            left=left,
            label=label,
            color=colors[idx % len(colors)],
            edgecolor="#222222",
            linewidth=0.4,
        )
        left += np.array(values)

    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Mean stage time (s)")
    ax.set_title("Pipeline stage timing")
    ax.grid(axis="x", alpha=0.25)
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.45), ncol=2, frameon=False)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def run_sensitivity(
    volume: Any,
    atlas_volume: Any | None,
    config: BenchmarkConfig,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    run_number = 1

    for alpha in config.alpha_values:
        for noise in config.noise_values:
            seed = config.seed + run_number
            row = run_alpha_once(
                volume,
                atlas_volume,
                config,
                run_number=run_number,
                seed=seed,
                alpha=alpha,
                position_noise=noise,
            )
            row["sweep"] = "alpha_noise"
            rows.append(row)
            run_number += 1

    for level in config.mc_levels:
        row = run_marching_once(
            volume,
            atlas_volume,
            config,
            run_number=run_number,
            seed=config.seed,
            mc_level=level,
        )
        row["sweep"] = "mc_level"
        rows.append(row)
        run_number += 1

    return rows


def run_benchmark(config: BenchmarkConfig) -> dict[str, Path]:
    validate_input_paths(config)
    config.output_dir.mkdir(parents=True, exist_ok=True)

    setup: dict[str, Any] = {
        "old_version_provenance": OLD_VERSION_PROVENANCE,
        "config": {
            "brain_nii": str(config.brain_nii),
            "t1w_nii": str(config.t1w_nii),
            "mask_nii": str(config.mask_nii),
            "runs": config.runs,
            "threshold": config.threshold,
            "position_noise": config.position_noise,
            "alpha": config.alpha,
            "normal_radius": config.normal_radius,
            "normal_max_nn": config.normal_max_nn,
            "mc_level": config.mc_level,
            "mc_step_size": config.mc_step_size,
            "mesh_target_faces": config.mesh_target_faces,
            "seed": config.seed,
            "skip_atlas": config.skip_atlas,
            "max_alpha_points": config.max_alpha_points,
        },
    }

    start = time.perf_counter()
    _t1w_nii, volume, brain_mask = load_masked_t1w(config.t1w_nii, config.mask_nii)
    setup["nifti_load_time_s"] = time.perf_counter() - start
    setup["volume_shape"] = list(volume.shape)
    setup["brain_voxels"] = int(brain_mask.sum())

    atlas_volume = None
    if not config.skip_atlas:
        start = time.perf_counter()
        atlas_volume, atlas_stats = load_atlas(config.brain_nii, brain_mask)
        setup["atlas_setup_time_s"] = time.perf_counter() - start
        setup["atlas_stats"] = atlas_stats

    rows: list[dict[str, Any]] = []
    for run_number in range(1, config.runs + 1):
        seed = config.seed + run_number - 1
        print(f"[{run_number}/{config.runs}] Alpha Shapes")
        rows.append(run_alpha_once(volume, atlas_volume, config, run_number, seed))

        print(f"[{run_number}/{config.runs}] Marching Cubes")
        rows.append(run_marching_once(volume, atlas_volume, config, run_number, seed))

    summary = summarize_by_algorithm(rows, SUMMARY_METRICS)

    paths = {
        "results_csv": config.output_dir / "benchmark_mesh_results.csv",
        "summary_csv": config.output_dir / "benchmark_mesh_summary.csv",
        "metadata_json": config.output_dir / "benchmark_mesh_metadata.json",
        "latex_table": config.output_dir / "table-bench-mesh.tex",
    }

    write_csv(paths["results_csv"], rows, CSV_FIELDS)
    write_summary_csv(paths["summary_csv"], summary, SUMMARY_METRICS)
    write_latex_table(paths["latex_table"], summary)
    paths["metadata_json"].write_text(
        json.dumps(setup, indent=2),
        encoding="utf-8",
    )

    if not config.no_plots:
        paths["mesh_plot"] = config.output_dir / "figure-bench-mesh.pdf"
        paths["pipeline_plot"] = config.output_dir / "figure-bench-pipeline.pdf"
        write_mesh_time_plot(paths["mesh_plot"], summary)
        write_pipeline_plot(paths["pipeline_plot"], summary)

    if config.sensitivity:
        sensitivity_rows = run_sensitivity(volume, atlas_volume, config)
        paths["sensitivity_csv"] = config.output_dir / "benchmark_mesh_sensitivity.csv"
        write_csv(paths["sensitivity_csv"], sensitivity_rows, ["sweep", *CSV_FIELDS])

    return paths


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark old V1/V2 Alpha Shapes against the latest Marching Cubes "
            "mesh path using this repository's A00063008 NFBS data."
        )
    )
    parser.add_argument("--runs", type=int, default=5, help="Repeated runs per algorithm.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for CSV, PDF, and LaTeX outputs.",
    )
    parser.add_argument("--brain-nii", type=Path, default=DEFAULT_BRAIN_NII)
    parser.add_argument("--t1w-nii", type=Path, default=DEFAULT_T1W_NII)
    parser.add_argument("--mask-nii", type=Path, default=DEFAULT_MASK_NII)
    parser.add_argument("--threshold", type=float, default=0.05)
    parser.add_argument("--position-noise", type=float, default=0.3)
    parser.add_argument("--alpha", type=float, default=8.0)
    parser.add_argument("--normal-radius", type=float, default=1.5)
    parser.add_argument("--normal-max-nn", type=int, default=50)
    parser.add_argument("--mc-level", type=float, default=0.15)
    parser.add_argument("--mc-step-size", type=int, default=1)
    parser.add_argument("--mesh-target-faces", type=int, default=300000)
    parser.add_argument(
        "--seed",
        type=int,
        default=20260607,
        help="Base seed; Alpha Shapes uses seed + run index for jitter.",
    )
    parser.add_argument(
        "--skip-atlas",
        action="store_true",
        help="Skip atlas fetch/resample and omit unlabelled-region metrics.",
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Write CSV/LaTeX only, without matplotlib PDF figures.",
    )
    parser.add_argument(
        "--sensitivity",
        action="store_true",
        help="Also sweep alpha/noise and MC level values into a separate CSV.",
    )
    parser.add_argument("--alpha-values", default="4,8,16")
    parser.add_argument("--noise-values", default="0.0,0.3,0.6")
    parser.add_argument("--mc-levels", default="0.10,0.15,0.20")
    parser.add_argument(
        "--max-alpha-points",
        type=int,
        default=0,
        help=(
            "Optional smoke-test downsample for Alpha Shapes. Keep 0 for thesis "
            "benchmarks because downsampling changes the result."
        ),
    )
    return parser


def config_from_args(args: argparse.Namespace) -> BenchmarkConfig:
    if args.runs < 1:
        raise ValueError("--runs must be at least 1")
    return BenchmarkConfig(
        brain_nii=args.brain_nii,
        t1w_nii=args.t1w_nii,
        mask_nii=args.mask_nii,
        output_dir=args.output_dir,
        runs=args.runs,
        threshold=args.threshold,
        position_noise=args.position_noise,
        alpha=args.alpha,
        normal_radius=args.normal_radius,
        normal_max_nn=args.normal_max_nn,
        mc_level=args.mc_level,
        mc_step_size=args.mc_step_size,
        mesh_target_faces=args.mesh_target_faces,
        seed=args.seed,
        skip_atlas=args.skip_atlas,
        no_plots=args.no_plots,
        sensitivity=args.sensitivity,
        alpha_values=parse_float_list(args.alpha_values),
        noise_values=parse_float_list(args.noise_values),
        mc_levels=parse_float_list(args.mc_levels),
        max_alpha_points=args.max_alpha_points,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    config = config_from_args(args)
    paths = run_benchmark(config)

    print("\nBenchmark outputs:")
    for label, path in paths.items():
        print(f"  {label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
