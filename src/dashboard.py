"""Interactive Streamlit dashboard for Red Pitaya recordings and leak analysis."""

# Path provides reliable project-relative file paths.
from pathlib import Path
import sys
# math is used to calculate a display downsampling interval.
import math

# Resolve the project folder before importing project modules.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# pandas stores and summarizes the recording samples.
import numpy as np
import pandas as pd
# Plotly builds interactive charts in the browser.
import plotly.graph_objects as go
# Streamlit supplies the dashboard controls and page layout.
import streamlit as st

# Import the analysis result type and processing function.
from src.leak_detection import (
    DEFAULT_COHERENCE_THRESHOLD,
    DEFAULT_WAVE_SPEED_M_PER_S,
    WELCH_OVERLAP,
    WELCH_SEGMENT_LENGTH,
    LeakAnalysis,
    analyze_leak,
)
# Import the CSV loader and time-axis helper.
from src.loader import add_time_axis, load_redpitaya_csv
from src.test_logging import (
    append_test_run,
    create_session,
    end_session,
    find_all_sessions,
    find_sessions_for_day,
    resume_session,
)

# CSV recordings are kept in the project's data folder.
DATA_DIR = ROOT / "data"
# Use the same default rate as the command-line workflow.
DEFAULT_FS = 20_000
DEMO_RECORDING_NAME = "Synthetic demo (not logged)"
# Avoid sending too many points to the browser chart at once.
MAX_DISPLAY_POINTS = 600_000

# Configure the browser tab and use the full available page width.
st.set_page_config(page_title="Red Pitaya Data Viewer", layout="wide")
# Display the dashboard's main heading and purpose.
st.title("Red Pitaya Data Viewer")
st.caption("View converted STEMlab recordings and estimate pipe-leak location")


@st.cache_data
def load_recording(csv_path: str, sampling_rate_hz: float) -> pd.DataFrame:
    """Cache CSV parsing while allowing the sampling rate to change."""
    # Load the samples, then add a time column calculated from the selected rate.
    return add_time_axis(
        load_redpitaya_csv(Path(csv_path)),
        sampling_rate_hz=sampling_rate_hz,
    )


@st.cache_data
def create_demo_recording(sampling_rate_hz: float) -> pd.DataFrame:
    """Create deterministic two-channel data for previewing the dashboard."""
    sample_count = min(max(int(sampling_rate_hz * 2), 4096), 100_000)
    time_s = np.arange(sample_count) / sampling_rate_hz
    frequency_1_hz = min(180.0, sampling_rate_hz * 0.15)
    frequency_2_hz = min(360.0, sampling_rate_hz * 0.35)
    source = (
        np.sin(2 * np.pi * frequency_1_hz * time_s)
        + 0.4 * np.sin(2 * np.pi * frequency_2_hz * time_s)
    )
    delay_samples = max(1, int(round(sampling_rate_hz * 0.0004)))
    noise = np.random.default_rng(42).normal(0, 0.08, (2, sample_count))

    return pd.DataFrame(
        {
            "time_s": time_s,
            "channel_1": source + noise[0],
            "channel_2": np.roll(source, delay_samples) + noise[1],
        }
    )


@st.cache_data
def run_leak_analysis(
    channel_1: tuple[float, ...],
    channel_2: tuple[float, ...],
    sampling_rate_hz: float,
    sensor_spacing_m: float,
    harmonic_bandwidth_hz: float,
    frequency_threshold_hz: float,
) -> LeakAnalysis:
    # Streamlit caching requires immutable, hashable inputs, so the caller
    # passes channel samples as tuples and they are converted back to arrays.
    return analyze_leak(
        channel_1=pd.Series(channel_1).to_numpy(),
        channel_2=pd.Series(channel_2).to_numpy(),
        sampling_rate_hz=sampling_rate_hz,
        sensor_spacing_m=sensor_spacing_m,
        harmonic_bandwidth_hz=harmonic_bandwidth_hz,
        frequency_threshold_hz=frequency_threshold_hz,
    )


# Find every CSV and show newest files first based on modification time.
csv_files = sorted(
    DATA_DIR.glob("*.csv"),
    key=lambda path: path.stat().st_mtime,
    reverse=True,
)

# Offer synthetic data so the dashboard can be previewed without a recording.
if not csv_files:
    st.info("No converted CSV files found. Synthetic demo data is available.")

recording_options = [path.name for path in csv_files] + [DEMO_RECORDING_NAME]
selected_name = st.sidebar.selectbox("Recording", recording_options)
is_demo = selected_name == DEMO_RECORDING_NAME

# Let the user provide the rate used when the recording was captured.
sampling_rate = st.sidebar.number_input(
    "Sampling rate (samples/second)",
    min_value=1,
    max_value=10_000_000,
    value=DEFAULT_FS,
    step=1000,
)


@st.dialog("Start testing session", width="large")
def open_test_session_dialog() -> None:
    """Set up session metadata once when the dashboard is opened."""
    st.write("Document this testing session before collecting samples.")

    existing_sessions = find_sessions_for_day(ROOT)
    if existing_sessions:
        session_choice = st.radio(
            "Session",
            ["Start a new session", "Resume today's latest session"],
        )
    else:
        session_choice = "Start a new session"

    if session_choice == "Resume today's latest session":
        existing_path = existing_sessions[0]
        existing = resume_session(ROOT, existing_path)
        default_objective = existing.get("session_objective", "")
        default_notes = existing.get("session_notes", "")
    else:
        existing_path = None
        default_objective = ""
        default_notes = ""

    st.text_input("Recording", value=selected_name, disabled=True)
    st.text_input(
        "Sampling rate",
        value=f"{sampling_rate:,.0f} Hz",
        disabled=True,
    )
    objective = st.text_area(
        "Session objective",
        value=default_objective,
        height=100,
    )
    session_notes = st.text_area(
        "Known setup notes",
        value=default_notes,
        height=130,
    )

    if st.button("Start session", type="primary"):
        if session_choice == "Resume today's latest session" and existing_path:
            session_id = existing.get("session_id", existing_path.stem)
            log_path = existing_path
        else:
            session_id, log_path = create_session(
                ROOT,
                {
                    "session_objective": objective,
                    "session_notes": session_notes,
                },
            )

        st.session_state["test_session_started"] = True
        st.session_state["test_session_id"] = session_id
        st.session_state["test_log_path"] = str(log_path)
        st.session_state["test_session_objective"] = objective
        st.session_state["test_session_notes"] = session_notes
        if session_choice == "Resume today's latest session" and existing_path:
            st.session_state["test_run_id"] = int(existing.get("run_id", "0"))
        else:
            st.session_state["test_run_id"] = 0
        st.rerun()


if is_demo:
    st.warning(
        "Preview mode uses synthetic signals. Analysis results are not saved "
        "to testing-session logs."
    )
else:
    if not st.session_state.get("test_session_started", False):
        open_test_session_dialog()
        st.stop()

    with st.sidebar:
        st.subheader("Test session")
        st.caption(st.session_state["test_session_id"])
        log_path = Path(st.session_state["test_log_path"])
        st.caption(str(log_path.relative_to(ROOT)))
        if st.button("End session"):
            end_session(log_path)
            st.session_state["test_session_started"] = False
            st.rerun()

try:
    if is_demo:
        data = create_demo_recording(float(sampling_rate))
    else:
        # Loading is cached, so repeated dashboard interactions avoid rereading
        # the same file unless the path or rate changes.
        data = load_recording(str(DATA_DIR / selected_name), float(sampling_rate))
except (FileNotFoundError, ValueError, OSError) as error:
    st.error(f"Could not load this recording: {error}")
    st.stop()

# The final sample's time is the recording duration shown to the user.
duration = float(data["time_s"].iloc[-1]) if len(data) > 1 else 0.0
# Choose which channels should appear in the raw-signal chart.
channels = st.sidebar.multiselect(
    "Channels to display",
    ["channel_1", "channel_2"],
    default=["channel_1", "channel_2"],
)

# A chart with no selected series would be meaningless.
if not channels:
    st.info("Select at least one channel in the sidebar.")
    st.stop()

# Provide a time-range slider when the recording has measurable duration.
if duration > 0:
    start_time, end_time = st.sidebar.slider(
        "Time window (seconds)",
        min_value=0.0,
        max_value=duration,
        value=(0.0, duration),
    )
else:
    # A one-sample recording has no non-zero time range to select.
    start_time, end_time = 0.0, 0.0

# Keep only rows whose calculated time falls inside the selected window.
visible = data[
    (data["time_s"] >= start_time) & (data["time_s"] <= end_time)
]
# Stop if unusual input or slider values produce no visible rows.
if visible.empty:
    st.warning("There are no samples in the selected time window.")
    st.stop()

# Show three high-level facts above the detailed tabs.
col1, col2, col3 = st.columns(3)
col1.metric("Samples per channel", f"{len(data):,}")
col2.metric("Sampling rate", f"{sampling_rate:,.0f} Hz")
col3.metric("Duration", f"{duration:.3f} s")

# Separate the raw data view from the processed leak-analysis view.
raw_tab, processed_tab, history_tab = st.tabs(
    ["Raw signal", "Leak analysis", "Run history"]
)

with raw_tab:
    # The raw tab shows the recorded channels without signal processing.
    st.subheader("Unprocessed signal")
    # Calculate a stride that limits chart points while retaining the full
    # recording for calculations and statistics.
    stride = max(1, math.ceil(len(visible) / MAX_DISPLAY_POINTS))
    plot_data = visible.iloc[::stride]

    # Create one interactive figure containing every selected channel.
    figure = go.Figure()
    for channel in channels:
        # Add each channel as a separate line using the shared time axis.
        figure.add_trace(
            go.Scattergl(
                x=plot_data["time_s"],
                y=plot_data[channel],
                mode="lines",
                name=channel.replace("_", " ").title(),
            )
        )
    # Label the axes and make the chart large enough to inspect.
    figure.update_layout(
        xaxis_title="Time (seconds)",
        yaxis_title="Voltage (V)",
        hovermode="x unified",
        height=600,
    )
    # Render the interactive raw-signal chart.
    st.plotly_chart(figure, use_container_width=True)
    # Make clear that downsampling changes display density, not the source data.
    st.caption(
        f"Displaying {len(plot_data):,} of {len(visible):,} samples. "
        "Downsampling is for display only."
    )

    # Calculate common descriptive statistics for each visible channel.
    st.subheader("Signal statistics")
    statistics = visible[channels].agg(["min", "max", "mean", "std"]).T
    statistics.index = [
        name.replace("_", " ").title() for name in statistics.index
    ]
    # Render the statistics as a table.
    st.dataframe(statistics, use_container_width=True)

    # Keep the first rows available for inspecting the input format.
    with st.expander("Preview first 20 rows"):
        st.dataframe(data.head(20), use_container_width=True)

with processed_tab:
    # The processed tab exposes the leak-location algorithm's controls/results.
    st.subheader("Leak-location algorithm")
    st.caption(
        "The algorithm uses both complete channels, not only the selected raw "
        "signal display window."
    )
    st.caption(
        f"Fixed settings: wave speed {DEFAULT_WAVE_SPEED_M_PER_S:,.0f} m/s, "
        f"MSC threshold {DEFAULT_COHERENCE_THRESHOLD:.2f}, "
        f"Welch segment length {WELCH_SEGMENT_LENGTH:,} samples, and "
        f"{WELCH_OVERLAP:.0%} overlap. Recordings shorter than the segment "
        "use their full length."
    )
    sensor_spacing = st.slider(
        "Sensor spacing (m)",
        min_value=0.001,
        max_value=100.0,
        value=4.0,
        step=0.1,
    )
    max_frequency_threshold_hz = min(500.0, float(sampling_rate) / 2)
    frequency_threshold_hz = st.slider(
        "Minimum analysis frequency (Hz)",
        min_value=0.0,
        max_value=max_frequency_threshold_hz,
        value=min(75.0, max_frequency_threshold_hz),
        step=min(1.0, max_frequency_threshold_hz),
        help=(
            "Frequency bins below this value are excluded before the "
            "coherence threshold is applied."
        ),
    )
    harmonic_bandwidth = st.number_input(
        "60 Hz harmonic notch bandwidth (Hz)",
        min_value=0.0,
        max_value=15.0,
        value=0.0,
        step=0.01,
        format="%.2f",
        help=(
            "Removes the 60 Hz component and every harmonic using this total "
            "bandwidth around each frequency. Set to 0.00 to disable it."
        ),
    )
    st.caption(
        "The notch filter is applied only to in-memory copies for analysis; "
        "the CSV and raw-signal view are not modified."
    )
    if is_demo:
        run_notes = ""
    else:
        if st.session_state.pop("_clear_test_run_notes", False):
            st.session_state["test_run_notes"] = ""

        run_notes = st.text_area(
            "Notes for this test",
            key="test_run_notes",
            placeholder="Observed behavior, setup changes, anomalies, or next steps...",
        )

    # Do expensive processing only after the user requests it.
    if st.button("Run leak-location algorithm", type="primary"):
        try:
            # Use both complete channels, not only the raw chart's visible
            # time window, to preserve the analysis input.
            result = run_leak_analysis(
                tuple(data["channel_1"].tolist()),
                tuple(data["channel_2"].tolist()),
                float(sampling_rate),
                float(sensor_spacing),
                float(harmonic_bandwidth),
                float(frequency_threshold_hz),
            )
            # Save the result so it remains visible across Streamlit reruns.
            st.session_state["leak_analysis"] = result
            st.session_state["leak_analysis_recording"] = selected_name

            if is_demo:
                st.success("Demo analysis complete. This run was not saved.")
            else:
                # Each completed analysis becomes one row in the current test log.
                next_run_id = int(st.session_state.get("test_run_id", 0)) + 1
                append_test_run(
                    log_path,
                    st.session_state["test_session_id"],
                    next_run_id,
                    {
                        "session_objective": st.session_state["test_session_objective"],
                        "session_notes": st.session_state["test_session_notes"],
                        "recording": selected_name,
                        "sampling_rate_hz": float(sampling_rate),
                        "channels": ",".join(channels),
                        "time_window_start_s": float(start_time),
                        "time_window_end_s": float(end_time),
                        "wave_speed_m_per_s": DEFAULT_WAVE_SPEED_M_PER_S,
                        "sensor_spacing_m": float(sensor_spacing),
                        "welch_overlap": WELCH_OVERLAP,
                        "coherence_threshold": DEFAULT_COHERENCE_THRESHOLD,
                        "frequency_threshold_hz": float(frequency_threshold_hz),
                        "harmonic_bandwidth_hz": float(harmonic_bandwidth),
                        "estimated_distance_m": float(result.leak_distance_m),
                        "peak_lag_s": float(result.peak_lag_s),
                        "segment_length": int(result.segment_length),
                        "run_notes": run_notes,
                    },
                )
                st.session_state["test_run_id"] = next_run_id
                st.success(
                    f"Test run {next_run_id} saved to "
                    f"{log_path.relative_to(ROOT)}"
                )
                st.session_state["_clear_test_run_notes"] = True
            st.rerun()
        except ValueError as error:
            # Show invalid parameter errors without crashing the dashboard.
            st.error(f"Could not run leak analysis: {error}")
        except OSError as error:
            st.error(f"Could not save this test run: {error}")

    # Retrieve the most recent result and the recording it belongs to.
    result = st.session_state.get("leak_analysis")
    result_recording = st.session_state.get("leak_analysis_recording")
    # Do not display a result from a different selected recording.
    if not isinstance(result, LeakAnalysis) or result_recording != selected_name:
        st.info("Set the parameters and run the algorithm to view processed output.")
    else:
        # Report the estimated position and delay in easy-to-read units.
        st.metric(
            "Estimated leak distance from channel 1",
            f"{result.leak_distance_m:.3f} m",
        )
        st.caption(
            f"Peak time delay: {result.peak_lag_s * 1000:.3f} ms; "
            f"segment length: {result.segment_length:,} samples"
        )

        # Plot the magnitude of the original cross-spectrum.
        spectrum = go.Figure()
        magnitude = abs(result.cross_spectrum)
        # Show all frequencies as a line.
        spectrum.add_trace(
            go.Scatter(
                x=result.frequency_hz,
                y=magnitude,
                mode="lines",
                name="Cross-spectrum",
            )
        )
        # Highlight the frequencies that passed the coherence filter.
        spectrum.add_trace(
            go.Scatter(
                x=result.frequency_hz[result.leak_band],
                y=magnitude[result.leak_band],
                mode="markers",
                name="Coherence-selected",
            )
        )
        # Add labels and a fixed height for consistent dashboard layout.
        spectrum.update_layout(
            title="Coherence-filtered cross-spectrum",
            xaxis_title="Frequency (Hz)",
            yaxis_title="Magnitude",
            height=400,
        )
        # Render the frequency-domain chart.
        st.plotly_chart(spectrum, use_container_width=True)

        # Plot the cross-spectral density magnitude from the two channels.
        csd_plot = go.Figure()
        csd_magnitude = abs(result.cross_spectrum)
        csd_plot.add_trace(
            go.Scatter(
                x=result.frequency_hz,
                y=csd_magnitude,
                mode="lines",
                name="Cross spectral density",
            )
        )
        csd_plot.add_trace(
            go.Scatter(
                x=result.frequency_hz[result.leak_band],
                y=csd_magnitude[result.leak_band],
                mode="markers",
                name="Coherence-selected",
            )
        )
        csd_plot.update_layout(
            title="Cross-spectral density magnitude",
            xaxis_title="Frequency (Hz)",
            yaxis_title="Magnitude (V²/Hz)",
            yaxis_type="log",
            height=400,
        )
        st.plotly_chart(csd_plot, use_container_width=True)

        # Plot the coherence value used by the filter.
        coherence_plot = go.Figure()
        coherence_plot.add_trace(
            go.Scatter(
                x=result.frequency_hz,
                y=result.coherence,
                mode="lines",
                name="MSC",
            )
        )
        # Keep the coherence axis in its natural 0-to-1 range.
        coherence_plot.update_layout(
            title="Magnitude-squared coherence",
            xaxis_title="Frequency (Hz)",
            yaxis_title="Coherence",
            yaxis_range=[0, 1],
            height=400,
        )
        # Render the coherence chart.
        st.plotly_chart(coherence_plot, use_container_width=True)

        # Plot correlation against lag so the selected timing peak is visible.
        correlation_plot = go.Figure()
        correlation_plot.add_trace(
            go.Scatter(
                x=result.lag_s * 1000,
                y=result.correlation,
                mode="lines",
                name="Correlation",
            )
        )
        # Draw the correlation envelope over the raw correlation.
        correlation_plot.add_trace(
            go.Scatter(
                x=result.lag_s * 1000,
                y=result.envelope,
                mode="lines",
                name="Envelope",
            )
        )
        # Mark the peak that produced the estimated leak distance.
        correlation_plot.add_trace(
            go.Scatter(
                x=[result.peak_lag_s * 1000],
                y=[result.envelope.max()],
                mode="markers",
                name="Selected peak",
            )
        )
        # Label the final chart in milliseconds and correlation units.
        correlation_plot.update_layout(
            title="Filtered cross-correlation",
            xaxis_title="Lag (ms)",
            yaxis_title="Correlation",
            height=500,
        )
        # Render the filtered cross-correlation chart.
        st.plotly_chart(correlation_plot, use_container_width=True)

with history_tab:
    st.subheader("Test run history")
    session_paths = find_all_sessions(ROOT)

    if not session_paths:
        st.info("No testing-session logs were found.")
    else:
        session_index = st.selectbox(
            "Session",
            range(len(session_paths)),
            format_func=lambda index: session_paths[index].stem.replace(
                "test_log_", ""
            ).replace("_session-", " · Session "),
        )
        history_path = session_paths[session_index]

        try:
            history = pd.read_csv(history_path)
        except (OSError, pd.errors.EmptyDataError, pd.errors.ParserError) as error:
            st.error(f"Could not read this session log: {error}")
        else:
            required_columns = {"run_id", "timestamp"}
            missing_columns = required_columns.difference(history.columns)
            if missing_columns:
                st.error(
                    "This session log is missing required columns: "
                    f"{', '.join(sorted(missing_columns))}."
                )
            elif history.empty:
                st.info("This session does not have any saved analysis runs yet.")
            else:
                history = history.sort_values(
                    "timestamp", ascending=False, kind="stable"
                ).reset_index(drop=True)
                display_columns = [
                    ("timestamp", "Time"),
                    ("run_id", "Run"),
                    ("recording", "Recording"),
                    ("estimated_distance_m", "Leak distance (m)"),
                    ("peak_lag_s", "Peak delay (s)"),
                    ("wave_speed_m_per_s", "Wave speed (m/s)"),
                    ("sensor_spacing_m", "Sensor spacing (m)"),
                    ("frequency_threshold_hz", "Minimum frequency (Hz)"),
                    ("run_notes", "Notes"),
                ]
                available_columns = [
                    (column, label)
                    for column, label in display_columns
                    if column in history.columns
                ]
                st.dataframe(
                    history[[column for column, _ in available_columns]].rename(
                        columns=dict(available_columns)
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

                selected_run_index = st.selectbox(
                    "Run details",
                    range(len(history)),
                    format_func=lambda index: (
                        f"Run {history.iloc[index]['run_id']} · "
                        f"{history.iloc[index]['timestamp']} · "
                        f"{history.iloc[index].get('recording', 'Unknown recording')}"
                    ),
                )
                selected_run = history.iloc[selected_run_index]
                metric_col, delay_col = st.columns(2)
                distance_value = pd.to_numeric(
                    pd.Series([selected_run.get("estimated_distance_m")]),
                    errors="coerce",
                ).iloc[0]
                distance = (
                    float(distance_value) if pd.notna(distance_value) else None
                )
                peak_lag_value = pd.to_numeric(
                    pd.Series([selected_run.get("peak_lag_s")]),
                    errors="coerce",
                ).iloc[0]
                peak_lag = (
                    float(peak_lag_value) if pd.notna(peak_lag_value) else None
                )
                metric_col.metric(
                    "Estimated leak distance",
                    f"{distance:.3f} m" if distance is not None else "Unavailable",
                )
                delay_col.metric(
                    "Peak time delay",
                    f"{peak_lag * 1000:.3f} ms"
                    if peak_lag is not None
                    else "Unavailable",
                )
                with st.expander("Selected run settings and notes"):
                    details = selected_run.dropna().to_frame("Value")
                    st.dataframe(details, use_container_width=True)

                st.download_button(
                    "Download this session's run history",
                    data=history.to_csv(index=False).encode("utf-8"),
                    file_name=history_path.name,
                    mime="text/csv",
                )
