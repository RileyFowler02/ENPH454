"""Load Red Pitaya CSV data and construct a time axis."""

# Path represents the input file location.
from pathlib import Path
# NumPy supplies numeric arrays and the expected sample-number sequence.
import numpy as np
# pandas supplies the table used by the rest of the application.
import pandas as pd

# Convert the converter's signed 16-bit channel values to volts.
CONVERSION_FACTOR = 40 / (2**16)

def load_redpitaya_csv(csv_path: Path) -> pd.DataFrame:
    """
    Load the converter's whitespace/tab-delimited three-column output:
    sample index, channel 1, channel 2.
    """
    # A missing file cannot be loaded, so report it before pandas tries.
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    # Red Pitaya writes whitespace-separated rows without a header row.
    data = pd.read_csv(
        csv_path,
        # Treat one or more spaces or tabs as the separator.
        sep=r"\s+",
        # Tell pandas that the file itself does not contain column names.
        header=None,
        # Assign meaningful names to the three values in each row.
        names=["sample_index", "channel_1", "channel_2"],
        # The converter output is expected to contain integer values.
        dtype=np.int64,
        # The Python parser supports the regular-expression separator above.
        engine="python",
    )

    # An empty table gives the analysis no samples to work with.
    if data.empty:
        raise ValueError("The CSV contains no samples.")

    # Missing values would make later calculations unreliable.
    if data.isna().any().any():
        raise ValueError("The CSV contains missing values.")

    # A valid recording starts at sample 1 and increases by exactly one.
    expected = np.arange(1, len(data) + 1, dtype=np.int64)
    # Convert the actual index column to an array for an exact comparison.
    actual = data["sample_index"].to_numpy()

    # This catches skipped, repeated, or incorrectly numbered samples.
    if not np.array_equal(actual, expected):
        raise ValueError(
            "Sample indices are missing, duplicated, or out of sequence."
        )

    # Keep the sample index unchanged, but convert both recorded channels
    # from converter units to volts.
    data[["channel_1", "channel_2"]] = (
        data[["channel_1", "channel_2"]] * CONVERSION_FACTOR
    )

    return data


def add_time_axis(
    data: pd.DataFrame,
    sampling_rate_hz: float = 20_000,
) -> pd.DataFrame:
    """Add time in seconds, with the first sample at t = 0."""
    # Division by zero or a negative rate cannot describe physical time.
    if sampling_rate_hz <= 0:
        raise ValueError("Sampling rate must be greater than zero.")

    # Copy the input so callers keep their original table unchanged.
    result = data.copy()
    # Sample 1 occurs at zero seconds; each later sample is one period later.
    result["time_s"] = (result["sample_index"] - 1) / sampling_rate_hz
    return result
