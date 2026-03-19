"""
backend/eeg/loader.py — Load BCI Competition IV 2a GDF files using MNE.
"""

import os

import mne
import numpy as np

# Motor imagery class definitions from the dataset documentation
CLASS_INFO = {
    'left_hand':  {'event_code': 769, 'label': 'Left Hand',  'color': '#e74c3c'},
    'right_hand': {'event_code': 770, 'label': 'Right Hand', 'color': '#3498db'},
    'feet':       {'event_code': 771, 'label': 'Feet',       'color': '#2ecc71'},
    'tongue':     {'event_code': 772, 'label': 'Tongue',     'color': '#9b59b6'},
}

# Standard 22-channel EEG names for BCI Competition IV 2a
STANDARD_EEG_CHANNELS = [
    'Fz', 'FC3', 'FC1', 'FCz', 'FC2', 'FC4',
    'C5', 'C3', 'C1', 'Cz', 'C2', 'C4', 'C6',
    'CP3', 'CP1', 'CPz', 'CP2', 'CP4',
    'P1', 'Pz', 'P2', 'POz',
]


def find_gdf_file(data_dir, subject, session):
    """Find the GDF file path for a given subject and session."""
    filename = f'{subject}{session}.gdf'
    filepath = os.path.join(data_dir, filename)
    if os.path.isfile(filepath):
        return filepath
    return None


def load_gdf(filepath):
    """
    Load a GDF file using MNE.

    Returns
    -------
    raw : mne.io.Raw
    events : np.ndarray (n_events, 3)
    event_id : dict — annotation description (str) -> MNE integer code
    """
    mne.set_log_level('WARNING')
    raw = mne.io.read_raw_gdf(filepath, preload=True, verbose=False)
    events, event_id = mne.events_from_annotations(raw, verbose=False)
    return raw, events, event_id


def setup_channels(raw):
    """
    Set proper channel types and strip name prefixes.

    The BCI Competition IV 2a GDF files have 25 channels:
    22 EEG + 3 EOG.  Channel names may have 'EEG-' or 'EOG-' prefixes.
    """
    ch_names = raw.ch_names

    rename_map = {}
    for name in ch_names:
        clean = name.replace('EEG-', '').replace('EOG-', 'EOG')
        if clean != name:
            rename_map[name] = clean
    if rename_map:
        raw.rename_channels(rename_map)

    n = len(raw.ch_names)
    eeg_channels = list(raw.ch_names[:min(22, n)])
    eog_channels = list(raw.ch_names[22:25]) if n >= 25 else []

    if eog_channels:
        raw.set_channel_types({ch: 'eog' for ch in eog_channels})

    return eeg_channels, eog_channels


def extract_session_events(events, event_id, sfreq):
    """
    Extract motor imagery cue events with timestamps for the session timeline.
    """
    id_to_key = {v: k for k, v in event_id.items()}
    gdf_to_class = {str(info['event_code']): cn for cn, info in CLASS_INFO.items()}

    cue_events = []
    for evt in events:
        mne_code = int(evt[2])
        gdf_key = id_to_key.get(mne_code, '')
        class_name = gdf_to_class.get(gdf_key)
        if class_name:
            sample = int(evt[0])
            cue_events.append({
                'sample': sample,
                'time': round(sample / sfreq, 4),
                'class': class_name,
            })

    return cue_events


def get_trial_counts(events, event_id):
    """Count total trials per motor imagery class."""
    id_to_key = {v: k for k, v in event_id.items()}
    gdf_to_class = {str(info['event_code']): cn for cn, info in CLASS_INFO.items()}

    counts = {cn: 0 for cn in CLASS_INFO}
    for evt in events:
        gdf_key = id_to_key.get(int(evt[2]), '')
        cn = gdf_to_class.get(gdf_key)
        if cn:
            counts[cn] += 1

    return counts
