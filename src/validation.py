"""Basic validation of Red Pitaya recording files and acquisition logs."""

# Path makes related log names and file metadata easy to handle.
from pathlib import Path
# Regular expressions extract numeric counters from the log text.
import re


def validate_recording(
    bin_path: Path,
    csv_path: Path,
    sampling_rate_hz: float,
) -> dict:
    """
    Validate that expected files exist, CSV is non-empty, and log files
    do not report acquisition/transfer losses.

    Returns a dictionary containing warnings and summary information.
    """
    # The two log files use the binary file name with fixed suffixes.
    log_path = Path(str(bin_path) + ".log")
    lost_path = Path(str(bin_path) + ".log.lost")

    # All four files are required for a complete validation report.
    required = [bin_path, log_path, lost_path, csv_path]
    # Keep the names of every required file that is absent.
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing recording file(s): " + ", ".join(missing))

    # A zero-byte CSV cannot contain converted samples.
    if csv_path.stat().st_size == 0:
        raise ValueError("Converted CSV is empty.")

    # Read both logs as text and replace undecodable bytes instead of failing
    # before the useful portions can be checked.
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    lost_text = lost_path.read_text(encoding="utf-8", errors="replace")

    # Warnings describe suspicious data without preventing the summary from
    # being returned.
    warnings = []

    # Check explicit transfer-loss counters in the acquisition report.
    loss_patterns = [
        r"Lost data during transfer by UDP network:\s*(-?\d+)",
        r"Lost data due to file write buffer overflow:\s*(-?\d+)",
        r"Loss of data due to lack of memory:\s*(-?\d+)",
    ]

    # Preserve each counter that was successfully found for the final report.
    reported_counters = []
    for pattern in loss_patterns:
        # Search one expected field at a time, ignoring capitalization.
        match = re.search(pattern, log_text, flags=re.IGNORECASE)
        if match:
            # Convert the captured counter from text to an integer.
            reported_counters.append(int(match.group(1)))
            # Any non-zero counter means the acquisition reported data loss.
            if int(match.group(1)) != 0:
                warnings.append(f"Acquisition report shows a non-zero loss counter: {match.group(0)}")
        else:
            # Missing fields are noteworthy because the report may be from a
            # different Red Pitaya software version.
            warnings.append(f"Could not find expected acquisition-log field: {pattern}")

    # In this Red Pitaya log format, each segment line ends in (lost_samples).
    segment_losses = [
        # Convert every captured lost-sample count from text to an integer.
        int(value)
        for value in re.findall(r"Get:\s*\d+\s*\((\d+)\)", lost_text)
    ]

    # A missing list means the segment log format could not be understood.
    if not segment_losses:
        warnings.append("Could not parse segment-loss counts from the .bin.log.lost file.")
        total_segment_losses = None
    else:
        # Add all segment-level losses into one summary count.
        total_segment_losses = sum(segment_losses)
        # A non-zero total is a warning, while zero means no segment loss.
        if total_segment_losses:
            warnings.append(
                f"The segment log reports {total_segment_losses:,} lost samples."
            )

    # We deliberately do not use convert_tool -i's lost-sample total:
    # the earlier recording showed implausibly large values in that field.
    # Return file sizes, acquisition settings, parsed counters, and warnings
    # in a dictionary that both the command-line program and tests can inspect.
    return {
        "bin_bytes": bin_path.stat().st_size,
        "csv_bytes": csv_path.stat().st_size,
        "sampling_rate_hz": sampling_rate_hz,
        "reported_loss_counters": reported_counters,
        "segment_count_in_loss_log": len(segment_losses),
        "segment_lost_samples": total_segment_losses,
        "warnings": warnings,
    }
