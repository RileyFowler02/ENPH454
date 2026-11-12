"""Run the complete Red Pitaya download, conversion, validation, and viewing workflow."""

# Path makes project-relative locations independent of the current directory.
from pathlib import Path
# argparse defines the command-line interface.
import argparse
# subprocess starts the optional Streamlit dashboard.
import subprocess
# sys supplies the current Python executable.
import sys

# Import each stage of the recording workflow.
from src.transfer import find_latest_recording, download_recording
from src.converter import convert_bin_to_csv
from src.loader import load_redpitaya_csv, add_time_axis
from src.validation import validate_recording


# Locate the project root and its two important subfolders.
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CLIENT_DIR = ROOT / "client"

# Default network location of the Red Pitaya upload listing.
LISTING_URL = "http://rp-f05437.local/streaming_manager/upload/"
# Default number of samples collected per second.
DEFAULT_SAMPLING_RATE_HZ = 20_000


def parse_arguments():
    # Create a parser that explains the command-line options to users.
    parser = argparse.ArgumentParser(
        description="Download, convert, validate, and view Red Pitaya recordings."
    )
    # Allow a user to bypass listing-page discovery with a direct file URL.
    parser.add_argument(
        "--url",
        help="Direct URL to a specific .bin file. If omitted, the listing page is searched.",
    )
    # Let users override the sampling rate used for time calculations.
    parser.add_argument(
        "--sampling-rate",
        type=float,
        default=DEFAULT_SAMPLING_RATE_HZ,
        help=f"Sampling rate in Hz (default: {DEFAULT_SAMPLING_RATE_HZ}).",
    )
    # Offer a mode for command-line processing without launching Streamlit.
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Process the recording without opening the Streamlit dashboard.",
    )
    # Parse the actual arguments supplied by the user.
    return parser.parse_args()


def main():
    # Read and validate command-line options.
    args = parse_arguments()

    print("\n=== 1. Locate recording ===")
    # Use the requested direct URL when provided.
    if args.url:
        bin_url = args.url
    else:
        # Otherwise ask the Red Pitaya listing page for its newest recording.
        print(f"Checking Red Pitaya listing: {LISTING_URL}")
        bin_url = find_latest_recording(LISTING_URL)

    print(f"Selected recording: {bin_url}")

    print("\n=== 2. Download recording files ===")
    # Download the binary and both companion logs into the data folder.
    downloaded = download_recording(bin_url, DATA_DIR)
    # The first returned path is the binary recording itself.
    bin_path = downloaded[0]

    print("\n=== 3. Convert BIN to CSV ===")
    # Use Red Pitaya's executable to produce the tabular CSV file.
    csv_path = convert_bin_to_csv(bin_path, CLIENT_DIR)

    print("\n=== 4. Load and validate data ===")
    # Load the converted samples and add human-readable time values.
    data = load_redpitaya_csv(csv_path)
    data = add_time_axis(data, args.sampling_rate)

    # Check that all expected files exist and inspect acquisition loss logs.
    report = validate_recording(
        bin_path=bin_path,
        csv_path=csv_path,
        sampling_rate_hz=args.sampling_rate,
    )

    # Print a concise summary of the loaded recording.
    print(f"Samples per channel: {len(data):,}")
    print(f"Duration: {data['time_s'].iloc[-1]:.4f} seconds")
    print(
        f"Channel 1 range: {data['channel_1'].min():.6f} V "
        f"to {data['channel_1'].max():.6f} V"
    )
    print(
        f"Channel 2 range: {data['channel_2'].min():.6f} V "
        f"to {data['channel_2'].max():.6f} V"
    )

    # Only print the segment-loss total when the log could be parsed.
    if report["segment_lost_samples"] is not None:
        print(f"Segment-log lost samples: {report['segment_lost_samples']:,}")

    # Show each warning separately so users can investigate data quality.
    if report["warnings"]:
        print("\nValidation warnings:")
        for warning in report["warnings"]:
            print(f"  WARNING: {warning}")
    else:
        print("Validation checks completed without reported loss warnings.")

    print("\n=== 5. Open dashboard ===")
    # Exit after processing when dashboard launch was explicitly disabled.
    if args.no_dashboard:
        print("Dashboard skipped (--no-dashboard).")
        return

    # Streamlit runs the dashboard script as an application.
    dashboard_path = ROOT / "src" / "dashboard.py"
    command = [
        # Reuse this same Python environment to find Streamlit.
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(dashboard_path),
    ]

    # Hand control to Streamlit; its terminal process can be stopped with
    # Ctrl+C as indicated to the user.
    print("Starting Streamlit. Use Ctrl+C in this terminal to stop it.")
    subprocess.run(command, cwd=str(ROOT), check=False)


if __name__ == "__main__":
    # Only run the workflow when this file is executed directly, not imported.
    main()
