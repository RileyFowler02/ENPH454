"""Create and update CSV logs for dashboard testing sessions."""

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd


LOG_DIRECTORY_NAME = "test logs"

COLUMNS = [
    "session_id",
    "session_status",
    "run_id",
    "timestamp",
    "session_objective",
    "session_notes",
    "recording",
    "sampling_rate_hz",
    "channels",
    "time_window_start_s",
    "time_window_end_s",
    "wave_speed_m_per_s",
    "sensor_spacing_m",
    "welch_segments",
    "welch_overlap",
    "coherence_threshold",
    "frequency_threshold_hz",
    "harmonic_bandwidth_hz",
    "estimated_distance_m",
    "peak_lag_s",
    "segment_length",
    "run_notes",
]


def get_log_directory(project_root: Path) -> Path:
    """Return the test-log directory, creating it when needed."""
    log_directory = project_root / LOG_DIRECTORY_NAME
    log_directory.mkdir(parents=True, exist_ok=True)
    return log_directory


def find_sessions_for_day(project_root: Path, session_date: date | None = None) -> list[Path]:
    """Find session CSV files for a day, newest session number first."""
    selected_date = session_date or date.today()
    log_directory = get_log_directory(project_root)
    prefix = f"test_log_{selected_date.isoformat()}_session-"
    files = list(log_directory.glob(prefix + "*.csv"))
    return sorted(
        files,
        key=lambda path: int(path.stem.rsplit("-session-", maxsplit=1)[-1])
        if "-session-" in path.stem
        else -1,
        reverse=True,
    )


def find_all_sessions(project_root: Path) -> list[Path]:
    """Find all session CSV files, with the most recently updated first."""
    log_directory = get_log_directory(project_root)
    files = log_directory.glob("test_log_*_session-*.csv")
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)


def _next_session_number(project_root: Path, session_date: date) -> int:
    existing = find_sessions_for_day(project_root, session_date)
    if not existing:
        return 1

    numbers = []
    for path in existing:
        suffix = path.stem.rsplit("-session-", maxsplit=1)[-1]
        try:
            numbers.append(int(suffix))
        except ValueError:
            continue
    return max(numbers, default=0) + 1


def create_session(project_root: Path, session_data: dict[str, Any]) -> tuple[str, Path]:
    """Create an empty CSV for a new testing session."""
    session_date = date.today()
    session_number = _next_session_number(project_root, session_date)
    session_id = f"{session_date.isoformat()}-{session_number}"
    log_directory = get_log_directory(project_root)
    log_path = log_directory / f"test_log_{session_date.isoformat()}_session-{session_number}.csv"
    pd.DataFrame(columns=COLUMNS).to_csv(log_path, index=False)
    return session_id, log_path


def resume_session(project_root: Path, log_path: Path) -> dict[str, str]:
    """Load the setup fields saved on the first row of an existing session."""
    if not log_path.is_file():
        return {}

    rows = pd.read_csv(log_path)
    if rows.empty:
        return {}

    first = rows.iloc[0]
    run_ids = pd.to_numeric(rows["run_id"], errors="coerce").dropna()
    next_run_id = int(run_ids.max()) if not run_ids.empty else 0
    return {
        "session_id": str(first.get("session_id", "")),
        "run_id": str(next_run_id),
        "session_objective": str(first.get("session_objective", ""))
        if pd.notna(first.get("session_objective"))
        else "",
        "session_notes": str(first.get("session_notes", ""))
        if pd.notna(first.get("session_notes"))
        else "",
    }


def append_test_run(
    log_path: Path,
    session_id: str,
    run_id: int,
    run_data: dict[str, Any],
) -> None:
    """Append one successful analysis run to the session CSV."""
    row = {
        "session_id": session_id,
        "session_status": "active",
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        **run_data,
    }
    complete_row = {column: row.get(column, "") for column in COLUMNS}
    frame = pd.DataFrame([complete_row])

    if log_path.exists() and log_path.stat().st_size > 0:
        existing_columns = pd.read_csv(log_path, nrows=0).columns.tolist()
        extra_columns = [
            column for column in existing_columns if column not in COLUMNS
        ]
        file_columns = [*COLUMNS, *extra_columns]
        if existing_columns != file_columns:
            existing = pd.read_csv(log_path).reindex(columns=file_columns)
            existing.to_csv(log_path, index=False)
        frame = pd.DataFrame(
            [{column: row.get(column, "") for column in file_columns}]
        )
        frame.to_csv(log_path, mode="a", header=False, index=False)
    else:
        frame.to_csv(log_path, index=False)


def end_session(log_path: Path) -> None:
    """Mark every run in an existing session as complete."""
    if not log_path.is_file():
        return

    rows = pd.read_csv(log_path)
    if rows.empty:
        return

    rows["session_status"] = "complete"
    rows.to_csv(log_path, index=False)
