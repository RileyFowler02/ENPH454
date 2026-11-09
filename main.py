"""Run the complete Red Pitaya download, conversion, validation, and viewing workflow."""

from pathlib import Path
import argparse
import subprocess
import sys

from src.transfer import find_latest_recording, download_recording
from src.converter import convert_bin_to_csv
from src.loader import load_redpitaya_csv, add_time_axis
from src.validation import validate_recording


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CLIENT_DIR = ROOT / "client"

LISTING_URL = "http://rp-f05437.local/streaming_manager/upload/"
DEFAULT_SAMPLING_RATE_HZ = 20_000


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Download, convert, validate, and view Red Pitaya recordings."
    )
    parser.add_argument(
        "--url",
        help="Direct URL to a specific .bin file. If omitted, the listing page is searched.",
    )
    parser.add_argument(
        "--sampling-rate",
        type=float,
        default=DEFAULT_SAMPLING_RATE_HZ,
        help=f"Sampling rate in Hz (default: {DEFAULT_SAMPLING_RATE_HZ}).",
    )
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Process the recording without opening the Streamlit dashboard.",
    )
    return parser.parse_args()


def main():
    args = parse_arguments()

    print("\n=== 1. Locate recording ===")
    if args.url:
        bin_url = args.url
    else:
        print(f"Checking Red Pitaya listing: {LISTING_URL}")
        bin_url = find_latest_recording(LISTING_URL)

    print(f"Selected recording: {bin_url}")

    print("\n=== 2. Download recording files ===")
    downloaded = download_recording(bin_url, DATA_DIR)
    bin_path = downloaded[0]

    print("\n=== 3. Convert BIN to CSV ===")
    csv_path = convert_bin_to_csv(bin_path, CLIENT_DIR)

    print("\n=== 4. Load and validate data ===")
    data = load_redpitaya_csv(csv_path)
    data = add_time_axis(data, args.sampling_rate)

    report = validate_recording(
        bin_path=bin_path,
        csv_path=csv_path,
        sampling_rate_hz=args.sampling_rate,
    )

    print(f"Samples per channel: {len(data):,}")
    print(f"Duration: {data['time_s'].iloc[-1]:.4f} seconds")
    print(f"Channel 1 range: {data['channel_1'].min()} to {data['channel_1'].max()}")
    print(f"Channel 2 range: {data['channel_2'].min()} to {data['channel_2'].max()}")

    if report["segment_lost_samples"] is not None:
        print(f"Segment-log lost samples: {report['segment_lost_samples']:,}")

    if report["warnings"]:
        print("\nValidation warnings:")
        for warning in report["warnings"]:
            print(f"  WARNING: {warning}")
    else:
        print("Validation checks completed without reported loss warnings.")

    print("\n=== 5. Open dashboard ===")
    if args.no_dashboard:
        print("Dashboard skipped (--no-dashboard).")
        return

    dashboard_path = ROOT / "src" / "dashboard.py"
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(dashboard_path),
    ]

    print("Starting Streamlit. Use Ctrl+C in this terminal to stop it.")
    subprocess.run(command, cwd=str(ROOT), check=False)


if __name__ == "__main__":
    main()
