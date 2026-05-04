"""
backend/eeg — EEG processing pipeline for BCI Competition IV 2a data.
"""

from .loader import (
    find_gdf_file, load_gdf, setup_channels,
    extract_session_events, get_trial_counts,
    CLASS_INFO, STANDARD_EEG_CHANNELS,
)
from .processing import (
    preprocess_raw, create_epochs,
    compute_band_erd_ers, downsample_timecourse,
    get_class_epoch_counts, get_class_epoch_run_ids,
)
from .export import (
    build_channel_regions, build_eeg_json,
    generate_synthetic_data, export_eeg_json,
)


def run_eeg_pipeline(config, electrode_mappings=None):
    """
    Run the full EEG processing pipeline.

    Tries to load a GDF file for the configured subject.
    Falls back to synthetic demo data if no file is found.
    """
    channel_regions = build_channel_regions(electrode_mappings)
    gdf_path = find_gdf_file(config.eeg_data_dir, config.eeg_subject, config.eeg_session)

    if gdf_path:
        data = _process_gdf(config, gdf_path, channel_regions)
    else:
        print(f"  No GDF file found in {config.eeg_data_dir}")
        print("  Generating synthetic demo data...")
        data = generate_synthetic_data(config.eeg_channels, channel_regions)

    export_eeg_json(config.eeg_output_path, data)
    print(f"  Exported -> {config.eeg_output_path}")
    return data


def _process_gdf(config, gdf_path, channel_regions):
    """Load, preprocess, and extract features from a real GDF file."""
    print(f"  Loading GDF: {gdf_path}")
    raw, events, event_id = load_gdf(gdf_path)
    eeg_channels, eog_channels = setup_channels(raw)

    trial_counts = get_trial_counts(events, event_id)
    session_events = extract_session_events(events, event_id, raw.info['sfreq'])
    print(f"  Trials per class: {trial_counts}")

    print("  Preprocessing (EOG removal, filtering)...")
    raw = preprocess_raw(raw, eeg_channels, eog_channels)

    print("  Creating broadband epochs for trial counts...")
    broadband_epochs = create_epochs(
        raw, events, event_id,
        tmin=config.eeg_epoch_tmin, tmax=config.eeg_epoch_tmax,
    )

    if broadband_epochs is None:
        print("  No epochs created, falling back to synthetic data")
        return generate_synthetic_data(config.eeg_channels, channel_regions)

    clean_counts = get_class_epoch_counts(broadband_epochs)
    trial_run_ids = get_class_epoch_run_ids(broadband_epochs, events, event_id)
    n_runs = (
        max(1, max((run_id for ids in trial_run_ids.values() for run_id in ids), default=-1) + 1)
        if trial_run_ids else 6
    )
    print(f"  Clean trials: {clean_counts}")

    erd_ers_data = {}
    for band_name, (lo, hi) in [('mu', config.eeg_mu_band), ('beta', config.eeg_beta_band)]:
        print(f"  Computing {band_name} ({lo}-{hi} Hz) ERD/ERS...")
        band_raw = raw.copy().filter(lo, hi, verbose=False)
        band_epochs = create_epochs(
            band_raw, events, event_id,
            tmin=config.eeg_epoch_tmin, tmax=config.eeg_epoch_tmax,
        )
        if band_epochs is None:
            continue

        erd, times = compute_band_erd_ers(
            band_epochs, config.eeg_baseline_tmin, config.eeg_baseline_tmax,
        )
        ds_classes = {}
        ds_times = None
        for cn, arr in erd.items():
            ds_arr, ds_t = downsample_timecourse(arr, times, config.eeg_downsample_bins)
            ds_classes[cn] = ds_arr
            ds_times = ds_t
        if ds_times is not None:
            erd_ers_data[band_name] = {
                'range': [lo, hi], 'times': ds_times, 'classes': ds_classes,
            }

    dataset_info = {
        'name': 'BCI Competition IV 2a',
        'description': (
            f'Motor imagery EEG, subject {config.eeg_subject}, '
            f'session {config.eeg_session}. 4 classes: left hand, right hand, '
            f'feet, tongue. 22 channels at {raw.info["sfreq"]} Hz.'
        ),
        'subject': config.eeg_subject,
        'session': config.eeg_session,
        'sfreq': raw.info['sfreq'],
        'duration': round(float(raw.times[-1]), 2),
        'channels': eeg_channels,
        'tmin': config.eeg_epoch_tmin,
        'tmax': config.eeg_epoch_tmax,
        'baseline_tmin': config.eeg_baseline_tmin,
        'baseline_tmax': config.eeg_baseline_tmax,
        'trial_counts': trial_counts,
        'clean_counts': clean_counts,
        'trial_run_ids': trial_run_ids,
        'n_runs': n_runs,
    }

    return build_eeg_json(dataset_info, session_events, erd_ers_data, channel_regions)
