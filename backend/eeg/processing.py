"""
backend/eeg/processing.py — EEG preprocessing and ERD/ERS computation.

Handles EOG artifact removal, filtering, epoching, and band-power
analysis for BCI Competition IV 2a motor imagery data.
"""

import numpy as np
import mne
from scipy.signal import hilbert

from .loader import CLASS_INFO, class_for_annotation_key, find_event_code


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


def preprocess_raw(raw, eeg_channels, eog_channels, l_freq=0.5, h_freq=40.0,
                   reference='csd'):
    """
    Full preprocessing, parameterised by spatial reference.

    reference='csd' (default): surface Laplacian / Current Source Density.
        pick EEG -> set 10-05 montage -> CSD -> bandpass. CSD is reference-free
        and spatially sharpening, so it localises focal sensorimotor
        (de)synchronisation -- it recovers feet's central (vertex) ERD and gives
        crisp contralateral hand ERD. Being a spatial derivative it also
        attenuates the broad frontal EOG far-field, so explicit EOG regression is
        omitted on this path.

    reference='car': legacy Common Average Reference (kept for comparison only).
        CAR -> EOG removal -> pick EEG -> bandpass. EOG regression runs first
        because EOGRegression.fit() requires the average reference to be set.

        Why CAR is NOT the default: averaging over only these 22
        fronto-centro-parietal electrodes (no occipital/temporal coverage) is a
        spatially biased reference. When a class (de)synchronises montage-wide it
        shifts the common average and leaks that common-mode power into every
        channel -- which inverts feet's true central ERD into a spurious,
        all-channel ERS (verified across subjects). CSD does not have this flaw.
    """
    if reference == 'csd':
        raw.pick(eeg_channels)
        raw.set_montage('standard_1005', match_case=False, on_missing='raise')
        raw = mne.preprocessing.compute_current_source_density(raw)
    else:  # 'car'
        raw.set_eeg_reference('average', projection=False, verbose=False)
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
        if class_for_annotation_key(key):
            mi_event_id[key] = val

    if not mi_event_id:
        print(f"    No motor imagery annotations found. Available keys: {list(event_id.keys())}")
        return None

    epochs = mne.Epochs(
        raw, events, event_id=mi_event_id,
        tmin=tmin, tmax=tmax,
        baseline=None, preload=True, verbose=False,
    )

    # Drop artifact-marked trials (event type 1023)
    reject_code = find_event_code(event_id, 1023)
    if reject_code is not None:
        reject_samples = {int(e[0]) for e in events if int(e[2]) == reject_code}
        if reject_samples:
            sfreq = raw.info['sfreq']
            # Drop any trial whose cue is within one epoch-length of a 1023
            # marker. This radius is coupled to the epoch length; it is safe for
            # this dataset only because the min inter-cue gap (~5.6 s) exceeds it.
            # Widening tmax past ~5.15 s would start catching adjacent clean
            # trials -- switch to a per-cue match if the epoch is lengthened.
            window = int(sfreq * (tmax - tmin))
            drop_idx = [
                i for i, ep in enumerate(epochs.events)
                if any(abs(int(ep[0]) - rs) < window for rs in reject_samples)
            ]
            if drop_idx:
                epochs.drop(drop_idx, reason='artifact')
                print(f"    Dropped {len(drop_idx)} artifact trials")

    return epochs


def compute_band_normalized_power(band_raw, events, event_id,
                                  tmin, tmax, baseline_tmin, baseline_tmax):
    """
    Compute per-trial band power, normalised to the per-class grand baseline.

    The Hilbert envelope power is taken from the CONTINUOUS band-filtered signal
    and only then epoched. Computing power on the continuous signal avoids the
    transform/edge artefacts that arise when the Hilbert transform is applied to
    each short epoch independently.

    Each trial's power is divided by its class grand baseline — the mean
    baseline-window power across *all* of that class's trials, per channel. The
    grand baseline is a stable, strictly-positive scalar (a per-trial baseline,
    by contrast, can be tiny and make a ratio explode). Dividing by a constant
    keeps the exported values O(1) while letting the frontend recover the exact
    ratio-of-means ERD/ERS over any subset of trials:

        ERD/ERS(t) = (mean_power(t) - baseline) / baseline * 100

    The constant grand-baseline divisor cancels in that ratio, so this is the
    standard Pfurtscheller method (average power across trials, one baseline
    ratio) — just deferred to the frontend so run selection stays exact.

    Returns
    -------
    norm_power : dict — class_name -> np.ndarray (n_trials, n_channels, n_times)
    times : np.ndarray
    """
    # Continuous Hilbert power, then epoch (no per-epoch transform edges).
    power_data = np.abs(hilbert(band_raw.get_data(), axis=-1)) ** 2
    power_raw = mne.io.RawArray(power_data, band_raw.info, verbose=False)

    power_epochs = create_epochs(power_raw, events, event_id, tmin=tmin, tmax=tmax)
    if power_epochs is None:
        return None, None

    times = power_epochs.times
    bl_mask = (times >= baseline_tmin) & (times < baseline_tmax)

    norm_power = {}

    for gdf_key in power_epochs.event_id:
        class_name = class_for_annotation_key(gdf_key)
        if not class_name:
            continue

        class_ep = power_epochs[gdf_key]
        if len(class_ep) == 0:
            continue

        power = class_ep.get_data()  # (n_trials, n_channels, n_times)

        # Grand baseline per channel: mean over all trials and baseline samples.
        grand_baseline = power[:, :, bl_mask].mean(axis=(0, 2))  # (n_channels,)
        grand_baseline = np.maximum(grand_baseline, np.finfo(float).tiny)

        norm_power[class_name] = power / grand_baseline[np.newaxis, :, np.newaxis]

    return norm_power, times


def _nice_step(raw_step):
    """Snap a raw time step to the nearest 'nice' value (1/2/2.5/5 x 10^k seconds)."""
    if raw_step <= 0:
        return raw_step
    base = 10.0 ** np.floor(np.log10(raw_step))
    candidates = np.array([1, 2, 2.5, 5, 10]) * base
    return float(candidates[np.argmin(np.abs(candidates - raw_step))])


def downsample_timecourse(data, times, n_bins):
    """
    Downsample onto a clean, evenly-spaced time grid (~n_bins points).

    A plain index linspace over the 250 Hz samples gives a drifting step
    (e.g. 0.0506 s for 90 bins) so the playhead never lands on round times nor
    exactly on t=0. Instead we build a target grid on a 'nice' step
    (1/2/2.5/5 x 10^k s) spanning [t0, t1] and snap each target time to its
    nearest available sample (<= ~2 ms error, invisible for ERD/ERS). For the
    default [-0.5, 4.0] s / 90-bin config this yields a clean 0.05 s grid that
    crosses t=0 exactly. Returns (downsampled_data, clean_times).
    """
    times = np.asarray(times)
    if n_bins is None or n_bins >= len(times):
        return data, times
    t0, t1 = float(times[0]), float(times[-1])
    step = _nice_step((t1 - t0) / (n_bins - 1))
    grid = np.round(t0 + step * np.arange(int(round((t1 - t0) / step)) + 1), 6)
    idx = np.abs(times[:, np.newaxis] - grid[np.newaxis, :]).argmin(axis=0)
    return data[..., idx], grid


def get_class_epoch_counts(epochs):
    """Get per-class trial counts from epochs (after artifact rejection)."""
    counts = {}
    for key in epochs.event_id:
        cn = class_for_annotation_key(key)
        if cn:
            counts[cn] = len(epochs[key])
    return counts


def get_class_epoch_run_ids(epochs, events, event_id):
    """Get per-class run IDs aligned with retained epochs."""
    run_start_code = find_event_code(event_id, 32766)
    if run_start_code is None:
        return {}

    id_to_key = {int(v): k for k, v in event_id.items()}

    sample_to_raw_run = {}
    current_run = -1
    for evt in events:
        sample = int(evt[0])
        mne_code = int(evt[2])
        if mne_code == run_start_code:
            current_run += 1
            continue

        class_name = class_for_annotation_key(id_to_key.get(mne_code, ''))
        if class_name:
            sample_to_raw_run[sample] = max(current_run, 0)

    retained = []
    retained_raw_runs = []
    for evt in epochs.events:
        sample = int(evt[0])
        gdf_key = id_to_key.get(int(evt[2]), '')
        class_name = class_for_annotation_key(gdf_key)
        if class_name:
            raw_run = int(sample_to_raw_run.get(sample, 0))
            retained.append((class_name, raw_run))
            retained_raw_runs.append(raw_run)

    run_id_map = {
        raw_run: compact_run
        for compact_run, raw_run in enumerate(sorted(set(retained_raw_runs)))
    }
    run_ids = {cn: [] for cn in CLASS_INFO}
    for class_name, raw_run in retained:
        run_ids[class_name].append(run_id_map[raw_run])

    return run_ids
