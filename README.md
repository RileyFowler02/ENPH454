# Red Pitaya offline acquisition workflow

## Project layout

```
ENPH454/
├── client/
│   └── convert_tool.exe
├── data/
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
and filtered correlation. Wave speed, sensor spacing, Welch segmentation,
overlap, and coherence threshold can be adjusted before running the analysis.
The dashboard also provides an optional 60 Hz harmonic notch filter. Its total
bandwidth can be set from 0.00 to 15.00 Hz in 0.01 Hz increments; the filter
is applied to in-memory copies only, so the CSV and raw-signal display remain
unchanged.

## Other notes
The Red Pitaya wipes local samples after turning it off




