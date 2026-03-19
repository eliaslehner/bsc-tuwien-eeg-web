# EEG Data — BCI Competition IV 2a

Place GDF files from the BCI Competition IV Dataset 2a here.

## Download

The dataset is available from the BNCI Horizon 2020 project:
http://bnci-horizon-2020.eu/database/data-sets

Look for **"Four class motor imagery (001-2014)"** (Dataset 2a).

## Expected files

| File       | Description                    |
|------------|--------------------------------|
| A01T.gdf   | Subject 1, Training session    |
| A01E.gdf   | Subject 1, Evaluation session  |
| A02T.gdf   | Subject 2, Training session    |
| ...        | ...                            |
| A09T.gdf   | Subject 9, Training session    |
| A09E.gdf   | Subject 9, Evaluation session  |

## Configuration

Set the subject and session in `backend/.env`:

```
EEG_DATA_DIR=./data/eeg
EEG_SUBJECT=A01
EEG_SESSION=T
```

If no GDF files are found, the pipeline generates synthetic demo data.
