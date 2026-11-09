"""Basic validation of Red Pitaya recording files and acquisition logs."""

from pathlib import Path
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
    log_path = Path(str(bin_path) + ".log")
    lost_path = Path(str(bin_path) + ".log.lost")

    required = [bin_path, log_path, lost_path, csv_path]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing recording file(s): " + ", ".join(missing))

    if csv_path.stat().st_size == 0:
        raise ValueError("Converted CSV is empty.")

    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    lost_text = lost_path.read_text(encoding="utf-8", errors="replace")

    warnings = []

    # Check explicit transfer-loss counters in the acquisition report.
    loss_patterns = [
        r"Lost data during transfer by UDP network:\s*(-?\d+)",
        r"Lost data due to file write buffer overflow:\s*(-?\d+)",
        r"Loss of data due to lack of memory:\s*(-?\d+)",
    ]

    reported_counters = []
    for pattern in loss_patterns:
        match = re.search(pattern, log_text, flags=re.IGNORECASE)
        if match:
            reported_counters.append(int(match.group(1)))
            if int(match.group(1)) != 0:
                warnings.append(f"Acquisition report shows a non-zero loss counter: {match.group(0)}")
        else:
            warnings.append(f"Could not find expected acquisition-log field: {pattern}")

    # In this Red Pitaya log format, each segment line ends in (lost_samples).
    segment_losses = [
        int(value)
        for value in re.findall(r"Get:\s*\d+\s*\((\d+)\)", lost_text)
    ]

    if not segment_losses:
        warnings.append("Could not parse segment-loss counts from the .bin.log.lost file.")
        total_segment_losses = None
    else:
        total_segment_losses = sum(segment_losses)
        if total_segment_losses:
            warnings.append(
                f"The segment log reports {total_segment_losses:,} lost samples."
            )

    # We deliberately do not use convert_tool -i's lost-sample total:
    # the earlier recording showed implausibly large values in that field.
    return {
        "bin_bytes": bin_path.stat().st_size,
        "csv_bytes": csv_path.stat().st_size,
        "sampling_rate_hz": sampling_rate_hz,
        "reported_loss_counters": reported_counters,
        "segment_count_in_loss_log": len(segment_losses),
        "segment_lost_samples": total_segment_losses,
        "warnings": warnings,
    }
