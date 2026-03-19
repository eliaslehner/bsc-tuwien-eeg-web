import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import torch
from dotenv import load_dotenv

# Load .env from the backend directory
_ENV_PATH = Path(__file__).parent / '.env'
load_dotenv(_ENV_PATH)


def _resolve_device(requested: str) -> str:
    """Resolve device string to an available torch device."""
    if requested == 'auto':
        if torch.cuda.is_available():
            return 'cuda'
        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return 'mps'
        return 'cpu'
    return requested


@dataclass
class Config:
    # --- Input Data ---
    brain_nii_path: str = os.getenv('BRAIN_NII_PATH', './data/nfbs/A00063008_NFB3_T1w_brain.nii')
    brain_t1w_nii_path: str = os.getenv('BRAIN_T1W_NII_PATH', './data/nfbs/A00063008_NFB3_T1w.nii')
    brain_mask_nii_path: str = os.getenv('BRAIN_MASK_NII_PATH', './data/nfbs/A00063008_NFB3_T1w_brainmask.nii')

    # --- Export Directories ---
    pointcloud_export_dir: str = os.getenv('POINTCLOUD_EXPORT_DIR', './data/model/raw/pointcloud_exports')
    brainmapping_export_dir: str = os.getenv('BRAINMAPPING_EXPORT_DIR', './data/model/mapped/brainmapping_exports')
    frontend_data_dir: str = os.getenv('FRONTEND_DATA_DIR', './frontend/public/data')

    # --- Output Filenames ---
    pointcloud_ply_filename: str = os.getenv('POINTCLOUD_PLY_FILENAME', 'brain_pointcloud.ply')
    mesh_ply_filename: str = os.getenv('MESH_PLY_FILENAME', 'brain_mesh.ply')
    mapped_mesh_ply_filename: str = os.getenv('MAPPED_MESH_PLY_FILENAME', 'brain_mesh_destrieux_mapped.ply')
    output_json_filename: str = os.getenv('OUTPUT_JSON_FILENAME', 'region_metadata.json')

    # --- Point Cloud Parameters ---
    threshold: float = float(os.getenv('THRESHOLD', '0.05'))
    position_noise: float = float(os.getenv('POSITION_NOISE', '0.3'))
    alpha: float = float(os.getenv('ALPHA', '8.0'))
    normal_radius: float = float(os.getenv('NORMAL_RADIUS', '1.5'))
    normal_max_nn: int = int(os.getenv('NORMAL_MAX_NN', '50'))

    # --- Marching Cubes Parameters ---
    mc_level: float = float(os.getenv('MC_LEVEL', '0.15'))
    mc_step_size: int = int(os.getenv('MC_STEP_SIZE', '1'))
    mesh_target_faces: int = int(os.getenv('MESH_TARGET_FACES', '300000'))

    # --- Export Options ---
    copy_mapped_mesh_to_frontend: bool = os.getenv('COPY_MAPPED_MESH_TO_FRONTEND', 'false').lower() in ('true', '1', 'yes')

    # --- Device ---
    device: str = field(default_factory=lambda: _resolve_device(os.getenv('DEVICE', 'auto')))

    # --- Viewer ---
    show_viewer: bool = os.getenv('SHOW_VIEWER', 'false').lower() in ('true', '1', 'yes')

    # --- EEG Channels ---
    eeg_channels: List[str] = field(
        default_factory=lambda: os.getenv(
            'EEG_CHANNELS',
            'Fz,FC3,FC1,FCz,FC2,FC4,C5,C3,C1,Cz,C2,C4,C6,CP3,CP1,CPz,CP2,CP4,P1,Pz,P2,POz'
        ).split(',')
    )

    # --- EEG Processing ---
    eeg_data_dir: str = os.getenv('EEG_DATA_DIR', './data/eeg')
    eeg_subject: str = os.getenv('EEG_SUBJECT', 'A01')
    eeg_session: str = os.getenv('EEG_SESSION', 'T')
    eeg_epoch_tmin: float = float(os.getenv('EEG_EPOCH_TMIN', '-0.5'))
    eeg_epoch_tmax: float = float(os.getenv('EEG_EPOCH_TMAX', '4.0'))
    eeg_baseline_tmin: float = float(os.getenv('EEG_BASELINE_TMIN', '-0.5'))
    eeg_baseline_tmax: float = float(os.getenv('EEG_BASELINE_TMAX', '0.0'))
    eeg_mu_band: tuple = (8, 13)
    eeg_beta_band: tuple = (13, 30)
    eeg_downsample_bins: int = int(os.getenv('EEG_DOWNSAMPLE_BINS', '90'))
    eeg_output_filename: str = os.getenv('EEG_OUTPUT_FILENAME', 'eeg_data.json')

    # --- Derived Paths ---
    @property
    def pointcloud_ply_path(self) -> str:
        return os.path.join(self.pointcloud_export_dir, self.pointcloud_ply_filename)

    @property
    def mesh_ply_path(self) -> str:
        return os.path.join(self.pointcloud_export_dir, self.mesh_ply_filename)

    @property
    def mapped_mesh_ply_path(self) -> str:
        return os.path.join(self.brainmapping_export_dir, self.mapped_mesh_ply_filename)

    @property
    def output_json_path(self) -> str:
        return os.path.join(self.frontend_data_dir, self.output_json_filename)

    @property
    def eeg_output_path(self) -> str:
        return os.path.join(self.frontend_data_dir, self.eeg_output_filename)
