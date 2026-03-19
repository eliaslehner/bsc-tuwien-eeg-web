"""
backend/eeg/processing.py — EEG preprocessing and ERD/ERS computation.

Handles EOG artifact removal, filtering, epoching, and band-power
analysis for BCI Competition IV 2a motor imagery data.
"""

import numpy as np
import mne
from scipy.signal import hilbert

from .loader import CLASS_INFO


def remove_eog_artifacts(raw, eeg_channels, eog_channels):
    """
    Remove EOG artifacts via linear regression.
    Falls back to highpass filter if regression fails.
    """
    if not eog_channels:
        return raw

    try:
        model = mne.preprocessing.EOGRegression(
            picks=eeg_channels, picks_artifact=eog_channels,
        )
        model.fit(raw)
        return model.apply(raw)
    except Exception as e:
        print(f"    EOG regression failed ({e}), applying highpass filter")
        raw.filter(l_freq=2.0, h_freq=None, picks=eeg_channels, verbose=False)
        return raw


def preprocess_raw(raw, eeg_channels, eog_channels, l_freq=0.5, h_freq=40.0):
    """
    Full preprocessing: EOG removal -> pick EEG channels -> bandpass filter.
    """
    raw = remove_eog_artifacts(raw, eeg_channels, eog_channels)
    raw.pick(eeg_channels)
    raw.filter(l_freq, h_freq, verbose=False)
    return raw


def create_epochs(raw, events, event_id, tmin=-0.5, tmax=4.0):
    """
    Create epochs around motor imagery cue events.
    Drops trials marked as rejected (event type 1023).
    """
    mi_event_id = {}
    for key, val in event_id.items():
        if key in ('769', '770', '771', '772'):
            mi_event_id[key] = val

    if not mi_event_id:
        return None

    epochs = mne.Epochs(
        raw, events, event_id=mi_event_id,
        tmin=tmin, tmax=tmax,
        baseline=None, preload=True, verbose=False,
    )

    # Drop artifact-marked trials (event type 1023)
    reject_code = event_id.get('1023')
    if reject_code is not None:
        reject_samples = {int(e[0]) for e in events if int(e[2]) == reject_code}
        if reject_samples:
            sfreq = raw.info['sfreq']
            window = int(sfreq * 8)  # trial window ~8 s
            drop_idx = [
                i for i, ep in enumerate(epochs.events)
                if any(abs(int(ep[0]) - rs) < window for rs in reject_samples)
            ]
            if drop_idx:
                epochs.drop(drop_idx, reason='artifact')
                print(f"    Dropped {len(drop_idx)} artifact trials")

    return epochs


def compute_band_erd_ers(epochs, l_freq, h_freq, baseline_tmin, baseline_tmax):
    """
    Compute ERD/ERS (%) for a frequency band via Hilbert transform.

    Returns
    -------
    erd_ers : dict — class_name -> np.ndarray (n_channels, n_times)
    times : np.ndarray
    """
    times = epochs.times
    bl_mask = (times >= baseline_tmin) & (times < baseline_tmax)

    gdf_to_class = {str(info['event_code']): cn for cn, info in CLASS_INFO.items()}
    erd_ers = {}

    for gdf_key in epochs.event_id:
        class_name = gdf_to_class.get(gdf_key)
        if not class_name:
            continue

        class_ep = epochs[gdf_key]
        if len(class_ep) == 0:
            continue

        filtered = class_ep.copy().filter(l_freq, h_freq, verbose=False)
        data = filtered.get_data()  # (n_trials, n_channels, n_times)

        power = np.abs(hilbert(data, axis=-1)) ** 2
        mean_power = power.mean(axis=0)  # (n_channels, n_times)

        baseline = mean_power[:, bl_mask].mean(axis=1, keepdims=True)
        baseline = np.maximum(baseline, 1e-10)

        erd_ers[class_name] = (mean_power - baseline) / baseline * 100.0

    return erd_ers, times


def downsample_timecourse(data, times, n_bins):
    """Downsample to n_bins evenly spaced time points."""
    if n_bins >= len(times):
        return data, times
    indices = np.linspace(0, len(times) - 1, n_bins, dtype=int)
    return data[:, indices], times[indices]


def get_class_epoch_counts(epochs):
    """Get per-class trial counts from epochs (after artifact rejection)."""
    gdf_to_class = {str(info['event_code']): cn for cn, info in CLASS_INFO.items()}
    counts = {}
    for key in epochs.event_id:
        cn = gdf_to_class.get(key)
        if cn:
            counts[cn] = len(epochs[key])
    return counts
