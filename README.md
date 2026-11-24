# Red Pitaya offline acquisition workflow

## Project layout

```
ENPH454/
├── client/
│   └── convert_tool.exe
├── data/
├── test logs/
├── src/
│   ├── __init__.py
│   ├── transfer.py
│   ├── converter.py
│   ├── loader.py
│   ├── leak_detection.py
│   ├── validation.py
│   └── dashboard.py
├── main.py
└── requirements.txt
```

## Setup (Windows PowerShell)

From the project root:

```
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Make sure `client\convert_tool.exe` exists.

## Run the complete workflow

```
python main.py
```

The program attempts to find the newest timestamped `.bin` link on:

`http://rp-f05437.local/streaming_manager/upload/`

It then downloads the `.bin`, `.bin.log`, and `.bin.log.lost` files,
converts the binary file to CSV, validates the converted data, and opens
the Streamlit dashboard.

## Run a specific recording

If automatic listing-page discovery does not work, provide a direct link:

```
python main.py --url "http://rp-f05437.local/streaming_manager/upload/data_file_2026-10-29_20-43-01.bin"
```

## Run without opening the dashboard

```
python main.py --no-dashboard
```

## Preview the dashboard without recordings

Run the dashboard directly with `streamlit run src/dashboard.py`. Choose
**Synthetic demo (not logged)** from the recording list to preview the charts
and run the analysis without a CSV. Demo analyses are not added to testing
session logs.

## Important measurement note

The loader multiplies both channel values by `40 / 2^16` and the dashboard
displays the resulting values as volts. Although the Red Pitaya acquisition was
configured for VOLT mode, verify this scaling experimentally or against
documentation for the exact installed Red Pitaya software version.

The time axis assumes a constant sampling rate of 20 kHz by default. Change it
with `--sampling-rate` if the acquisition setting changes.

## Leak-location analysis

The dashboard uses `channel_1` and `channel_2` from the converted Red Pitaya
CSV directly. The **Raw signal** tab shows the unprocessed recording. The
**Leak analysis** tab optionally runs the coherence-filtered cross-correlation
algorithm and displays the estimated leak distance, cross-spectrum, coherence,
and filtered correlation. Wave speed is fixed at 1,780 m/s.
Welch analysis uses a fixed 2,048-sample segment and 50% overlap (or the full
recording length for shorter inputs). Sensor spacing, minimum analysis
frequency, coherence threshold, and harmonic notch bandwidth can be adjusted
before running the analysis.
The dashboard also provides an optional 60 Hz harmonic notch filter. Its total
bandwidth can be set from 0.00 to 15.00 Hz in 0.01 Hz increments; the filter
is applied to in-memory copies only, so the CSV and raw-signal display remain
unchanged.

## Testing-session logs

The dashboard opens a testing-session setup dialog the first time it starts.
The dialog can create a new session or resume today's latest session, and
captures the objective and known setup notes.

Every successful leak-analysis run is appended to a CSV in `test logs/`. Files
are grouped by day and session:

```
test logs/test_log_2026-11-17_session-1.csv
```

Use **End session** in the dashboard sidebar when testing is complete. A
session will remain resumable until its CSV is edited or removed.

## Other notes
The Red Pitaya wipes local samples after turning it off




