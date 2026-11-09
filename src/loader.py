"""Load Red Pitaya CSV data and construct a time axis."""

from pathlib import Path
import numpy as np
import pandas as pd


def load_redpitaya_csv(csv_path: Path) -> pd.DataFrame:
    """
    Load the converter's whitespace/tab-delimited three-column output:
    sample index, channel 1, channel 2.
    """
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    data = pd.read_csv(
        csv_path,
        sep=r"\s+",
        header=None,
        names=["sample_index", "channel_1", "channel_2"],
        dtype=np.int64,
        engine="python",
    )

    if data.empty:
        raise ValueError("The CSV contains no samples.")

    if data.isna().any().any():
        raise ValueError("The CSV contains missing values.")

    expected = np.arange(1, len(data) + 1, dtype=np.int64)
    actual = data["sample_index"].to_numpy()

    if not np.array_equal(actual, expected):
        raise ValueError(
            "Sample indices are missing, duplicated, or out of sequence."
        )

    return data


def add_time_axis(
    data: pd.DataFrame,
    sampling_rate_hz: float = 20_000,
) -> pd.DataFrame:
    """Add time in seconds, with the first sample at t = 0."""
    if sampling_rate_hz <= 0:
        raise ValueError("Sampling rate must be greater than zero.")

    result = data.copy()
    result["time_s"] = (result["sample_index"] - 1) / sampling_rate_hz
    return result
