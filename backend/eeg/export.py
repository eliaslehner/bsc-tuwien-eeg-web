"""
backend/eeg/export.py — Build and export EEG data as JSON for the frontend.
"""

import json
import os

import numpy as np

from .loader import CLASS_INFO, STANDARD_EEG_CHANNELS


def build_channel_regions(electrode_mappings):
    """Build channel -> region mapping from electrode pipeline output."""
    if not electrode_mappings:
        return {}
    return {
        em['name']: {'region_id': em['region_id'], 'region_name': em['region_name']}
        for em in electrode_mappings
    }


def build_eeg_json(dataset_info, session_events, erd_ers_data, channel_regions):
    """
    Build the complete EEG JSON structure for the frontend.

    erd_ers_data: { band: { 'range': [lo,hi], 'times': array, 'classes': { class: array(ch,t) } } }
    """
    classes = []
    for class_id, info in CLASS_INFO.items():
        classes.append({
            'id': class_id,
            'label': info['label'],
            'event_code': info['event_code'],
            'color': info['color'],
            'n_trials': int(dataset_info.get('trial_counts', {}).get(class_id, 0)),
            'n_clean': int(dataset_info.get('clean_counts', {}).get(class_id, 0)),
        })

    erd_json = {}
    for band_name, bd in erd_ers_data.items():
        entry = {'range': bd['range']}
        entry['times'] = [round(float(t), 4) for t in bd['times']]
        for cn in CLASS_INFO:
            arr = bd['classes'].get(cn)
            if arr is not None:
                arr = np.asarray(arr)
                entry[cn] = np.round(arr, 2).tolist()
        erd_json[band_name] = entry

    return {
        'dataset': {
            'name': dataset_info.get('name', 'BCI Competition IV 2a'),
            'description': dataset_info.get('description', ''),
            'subject': dataset_info.get('subject', ''),
            'session': dataset_info.get('session', ''),
            'sfreq': float(dataset_info.get('sfreq', 250.0)),
            'duration': round(float(dataset_info.get('duration', 0)), 2),
            'channels': list(dataset_info.get('channels', STANDARD_EEG_CHANNELS)),
            'n_channels': len(dataset_info.get('channels', STANDARD_EEG_CHANNELS)),
            'n_runs': int(dataset_info.get('n_runs', 6)),
            'classes': classes,
        },
        'trial_timeline': {
            'tmin': float(dataset_info.get('tmin', -0.5)),
            'tmax': float(dataset_info.get('tmax', 4.0)),
            'baseline': [
                float(dataset_info.get('baseline_tmin', -0.5)),
                float(dataset_info.get('baseline_tmax', 0.0)),
            ],
        },
        'events': session_events,
        'trial_run_ids': {
            cn: [int(run_id) for run_id in run_ids]
            for cn, run_ids in dataset_info.get('trial_run_ids', {}).items()
        },
        'erd_ers': erd_json,
        'channel_regions': channel_regions,
    }


def generate_synthetic_data(channels=None, channel_regions=None):
    """
    Generate synthetic EEG data with realistic motor imagery ERD/ERS patterns.
    Used when no GDF files are available.
    """
    if channels is None:
        channels = list(STANDARD_EEG_CHANNELS)
    if channel_regions is None:
        channel_regions = {}

    n_ch = len(channels)
    n_bins = 90
    tmin, tmax = -0.5, 4.0
    times = np.linspace(tmin, tmax, n_bins)
    rng = np.random.default_rng(42)

    # Spatial weights: lateralisation and centrality
    central = {'Cz', 'C1', 'C2', 'FCz', 'CPz'}
    near_central = {'C3', 'C4', 'FC1', 'FC2', 'CP1', 'CP2'}
    n_runs = 6

    hw = {}  # hemisphere weight: -1 = left, +1 = right, 0 = midline
    cw = {}  # central weight: 1.0 = near Cz, 0.3 = peripheral

    for ch in channels:
        digits = ''.join(c for c in ch if c.isdigit())
        if digits:
            hw[ch] = -1.0 if int(digits) % 2 == 1 else 1.0
        else:
            hw[ch] = 0.0
        cw[ch] = 1.0 if ch in central else (0.7 if ch in near_central else 0.3)

    def erd_curve(t, onset=0.3, peak=-40, decay=0.25):
        c = np.zeros_like(t)
        active = t >= onset
        tr = t[active] - onset
        c[active] = peak * (1 - np.exp(-tr * 3)) * np.exp(-tr * decay)
        return c

    erd_ers_data = {}
    trial_run_ids = {}
    for band, (lo, hi) in [('mu', (8, 13)), ('beta', (13, 30))]:
        scale = 1.0 if band == 'mu' else 0.6
        classes = {}

        for cn in CLASS_INFO:
            n_sim_trials = 68  # roughly clean trials
            trials_per_run = int(np.ceil(n_sim_trials / n_runs))
            trial_run_ids[cn] = [
                min(i // trials_per_run, n_runs - 1)
                for i in range(n_sim_trials)
            ]
            data = np.zeros((n_sim_trials, n_ch, n_bins))
            for t_idx in range(n_sim_trials):
                for i, ch in enumerate(channels):
                    h, c = hw.get(ch, 0), cw.get(ch, 0.3)
                    if cn == 'left_hand':
                        s = (0.5 + 0.5 * h) * c * scale
                    elif cn == 'right_hand':
                        s = (0.5 - 0.5 * h) * c * scale
                    elif cn == 'feet':
                        s = c * scale * 0.8
                    else:  # tongue
                        s = 0.3 * scale
                    data[t_idx, i] = erd_curve(times, peak=-45 * s + rng.normal(0, 3)) \
                        + rng.normal(0, 5, n_bins)
            classes[cn] = data

        erd_ers_data[band] = {'range': [lo, hi], 'times': times, 'classes': classes}

    # Synthetic session events (~288 trials across 6 runs)
    sfreq = 250.0
    events = []
    class_names = list(CLASS_INFO.keys())
    t = 5.0
    for _run in range(6):
        for trial in range(48):
            cn = class_names[trial % 4]
            events.append({'sample': int(t * sfreq), 'time': round(t, 4), 'class': cn})
            t += 7.5 + rng.uniform(0, 1)
        t += 30

    dataset_info = {
        'name': 'BCI Competition IV 2a',
        'description': (
            'Synthetic demo data (no GDF files found). '
            '4-class motor imagery: left hand, right hand, feet, tongue. '
            '22 EEG channels at 250 Hz.'
        ),
        'subject': 'Demo',
        'session': 'S',
        'sfreq': sfreq,
        'duration': round(t + 10, 2),
        'channels': channels,
        'tmin': tmin,
        'tmax': tmax,
        'baseline_tmin': -0.5,
        'baseline_tmax': 0.0,
        'trial_counts': {cn: 72 for cn in CLASS_INFO},
        'clean_counts': {cn: 68 for cn in CLASS_INFO},
        'trial_run_ids': trial_run_ids,
        'n_runs': n_runs,
    }

    return build_eeg_json(dataset_info, events, erd_ers_data, channel_regions)


def export_eeg_json(output_path, data):
    """Write EEG data JSON to disk."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    size_kb = os.path.getsize(output_path) / 1024
    print(f"    {size_kb:.0f} KB written")
