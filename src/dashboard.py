"""Interactive Streamlit dashboard for Red Pitaya recordings and leak analysis."""

# Path provides reliable project-relative file paths.
from pathlib import Path
# math is used to calculate a display downsampling interval.
import math

# pandas stores and summarizes the recording samples.
import pandas as pd
# Plotly builds interactive charts in the browser.
import plotly.graph_objects as go
# Streamlit supplies the dashboard controls and page layout.
import streamlit as st

# Import the analysis result type and processing function.
from src.leak_detection import LeakAnalysis, analyze_leak
# Import the CSV loader and time-axis helper.
from src.loader import add_time_axis, load_redpitaya_csv

# Resolve the project folder from this source file's location.
ROOT = Path(__file__).resolve().parents[1]
# CSV recordings are kept in the project's data folder.
DATA_DIR = ROOT / "data"
# Use the same default rate as the command-line workflow.
DEFAULT_FS = 20_000
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
def run_leak_analysis(
    channel_1: tuple[float, ...],
    channel_2: tuple[float, ...],
    sampling_rate_hz: float,
    wave_speed_m_per_s: float,
    sensor_spacing_m: float,
    segments: int,
    overlap: float,
    coherence_threshold: float,
    harmonic_bandwidth_hz: float,
) -> LeakAnalysis:
    # Streamlit caching requires immutable, hashable inputs, so the caller
    # passes channel samples as tuples and they are converted back to arrays.
    return analyze_leak(
        channel_1=pd.Series(channel_1).to_numpy(),
        channel_2=pd.Series(channel_2).to_numpy(),
        sampling_rate_hz=sampling_rate_hz,
        wave_speed_m_per_s=wave_speed_m_per_s,
        sensor_spacing_m=sensor_spacing_m,
        segments=segments,
        overlap=overlap,
        coherence_threshold=coherence_threshold,
        harmonic_bandwidth_hz=harmonic_bandwidth_hz,
    )


# Find every CSV and show newest files first based on modification time.
csv_files = sorted(
    DATA_DIR.glob("*.csv"),
    key=lambda path: path.stat().st_mtime,
    reverse=True,
)

# Explain the setup problem and stop rendering if there are no recordings.
if not csv_files:
    st.warning(
        "No converted CSV files were found in the data folder. "
        "Run python main.py first."
    )
    st.stop()

# Let the user choose which recording to inspect.
selected_name = st.sidebar.selectbox("Recording", [path.name for path in csv_files])
# Rebuild the selected file's full path inside the known data folder.
selected_path = DATA_DIR / selected_name

# Let the user provide the rate used when the recording was captured.
sampling_rate = st.sidebar.number_input(
    "Sampling rate (samples/second)",
    min_value=1,
    max_value=10_000_000,
    value=DEFAULT_FS,
    step=1000,
)

try:
    # Loading is cached, so repeated dashboard interactions avoid rereading
    # the same file unless the path or rate changes.
    data = load_recording(str(selected_path), float(sampling_rate))
except (FileNotFoundError, ValueError, OSError) as error:
    # Turn expected input-file problems into a visible dashboard message.
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
raw_tab, processed_tab = st.tabs(["Raw signal", "Leak analysis"])

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
    # Wave speed and sensor spacing describe the physical pipe setup.
    wave_speed = st.number_input(
        "Wave speed (m/s)", min_value=0.001, value=1400.0, step=10.0
    )
    sensor_spacing = st.number_input(
        "Sensor spacing (m)", min_value=0.001, value=4.0, step=0.1
    )
    # These settings control the Welch frequency estimates.
    segments = st.number_input(
        "Welch segments", min_value=1, max_value=128, value=16, step=1
    )
    overlap = st.slider("Welch overlap", 0.0, 0.95, 0.75)
    # This cutoff decides which frequency bins are considered coherent.
    coherence_threshold = st.slider("Coherence threshold", 0.0, 1.0, 0.4)
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

    # Do expensive processing only after the user requests it.
    if st.button("Run leak-location algorithm", type="primary"):
        try:
            # Use both complete channels, not only the raw chart's visible
            # time window, to preserve the analysis input.
            result = run_leak_analysis(
                tuple(data["channel_1"].tolist()),
                tuple(data["channel_2"].tolist()),
                float(sampling_rate),
                float(wave_speed),
                float(sensor_spacing),
                int(segments),
                float(overlap),
                float(coherence_threshold),
                float(harmonic_bandwidth),
            )
            # Save the result so it remains visible across Streamlit reruns.
            st.session_state["leak_analysis"] = result
            st.session_state["leak_analysis_recording"] = selected_name
        except ValueError as error:
            # Show invalid parameter errors without crashing the dashboard.
            st.error(f"Could not run leak analysis: {error}")

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
