"""Interactive Streamlit dashboard for Red Pitaya recordings and leak analysis."""

from pathlib import Path
import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.leak_detection import LeakAnalysis, analyze_leak
from src.loader import add_time_axis, load_redpitaya_csv

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DEFAULT_FS = 20_000
MAX_DISPLAY_POINTS = 25_000

st.set_page_config(page_title="Red Pitaya Data Viewer", layout="wide")
st.title("Red Pitaya Data Viewer")
st.caption("View converted STEMlab recordings and estimate pipe-leak location")


@st.cache_data
def load_recording(csv_path: str, sampling_rate_hz: float) -> pd.DataFrame:
    """Cache CSV parsing while allowing the sampling rate to change."""
    return add_time_axis(
        load_redpitaya_csv(Path(csv_path)),
        sampling_rate_hz=sampling_rate_hz,
    )


@st.cache_data
def run_leak_analysis(
    channel_1: tuple[int, ...],
    channel_2: tuple[int, ...],
    sampling_rate_hz: float,
    wave_speed_m_per_s: float,
    sensor_spacing_m: float,
    segments: int,
    overlap: float,
    coherence_threshold: float,
) -> LeakAnalysis:
    return analyze_leak(
        channel_1=pd.Series(channel_1).to_numpy(),
        channel_2=pd.Series(channel_2).to_numpy(),
        sampling_rate_hz=sampling_rate_hz,
        wave_speed_m_per_s=wave_speed_m_per_s,
        sensor_spacing_m=sensor_spacing_m,
        segments=segments,
        overlap=overlap,
        coherence_threshold=coherence_threshold,
    )


csv_files = sorted(
    DATA_DIR.glob("*.csv"),
    key=lambda path: path.stat().st_mtime,
    reverse=True,
)

if not csv_files:
    st.warning(
        "No converted CSV files were found in the data folder. "
        "Run python main.py first."
    )
    st.stop()

selected_name = st.sidebar.selectbox("Recording", [path.name for path in csv_files])
selected_path = DATA_DIR / selected_name

sampling_rate = st.sidebar.number_input(
    "Sampling rate (samples/second)",
    min_value=1,
    max_value=10_000_000,
    value=DEFAULT_FS,
    step=1000,
)

try:
    data = load_recording(str(selected_path), float(sampling_rate))
except (FileNotFoundError, ValueError, OSError) as error:
    st.error(f"Could not load this recording: {error}")
    st.stop()

duration = float(data["time_s"].iloc[-1]) if len(data) > 1 else 0.0
channels = st.sidebar.multiselect(
    "Channels to display",
    ["channel_1", "channel_2"],
    default=["channel_1", "channel_2"],
)

if not channels:
    st.info("Select at least one channel in the sidebar.")
    st.stop()

if duration > 0:
    start_time, end_time = st.sidebar.slider(
        "Time window (seconds)",
        min_value=0.0,
        max_value=duration,
        value=(0.0, duration),
    )
else:
    start_time, end_time = 0.0, 0.0

visible = data[
    (data["time_s"] >= start_time) & (data["time_s"] <= end_time)
]
if visible.empty:
    st.warning("There are no samples in the selected time window.")
    st.stop()

col1, col2, col3 = st.columns(3)
col1.metric("Samples per channel", f"{len(data):,}")
col2.metric("Sampling rate", f"{sampling_rate:,.0f} Hz")
col3.metric("Duration", f"{duration:.3f} s")

raw_tab, processed_tab = st.tabs(["Raw signal", "Leak analysis"])

with raw_tab:
    st.subheader("Unprocessed signal")
    stride = max(1, math.ceil(len(visible) / MAX_DISPLAY_POINTS))
    plot_data = visible.iloc[::stride]

    figure = go.Figure()
    for channel in channels:
        figure.add_trace(
            go.Scattergl(
                x=plot_data["time_s"],
                y=plot_data[channel],
                mode="lines",
                name=channel.replace("_", " ").title(),
            )
        )
    figure.update_layout(
        xaxis_title="Time (seconds)",
        yaxis_title="Recorded value (converter output units)",
        hovermode="x unified",
        height=600,
    )
    st.plotly_chart(figure, use_container_width=True)
    st.caption(
        f"Displaying {len(plot_data):,} of {len(visible):,} samples. "
        "Downsampling is for display only."
    )

    st.subheader("Signal statistics")
    statistics = visible[channels].agg(["min", "max", "mean", "std"]).T
    statistics.index = [
        name.replace("_", " ").title() for name in statistics.index
    ]
    st.dataframe(statistics, use_container_width=True)

    with st.expander("Preview first 20 rows"):
        st.dataframe(data.head(20), use_container_width=True)

with processed_tab:
    st.subheader("Leak-location algorithm")
    st.caption(
        "The algorithm uses both complete channels, not only the selected raw "
        "signal display window."
    )
    wave_speed = st.number_input(
        "Wave speed (m/s)", min_value=0.001, value=1400.0, step=10.0
    )
    sensor_spacing = st.number_input(
        "Sensor spacing (m)", min_value=0.001, value=4.0, step=0.1
    )
    segments = st.number_input(
        "Welch segments", min_value=1, max_value=128, value=16, step=1
    )
    overlap = st.slider("Welch overlap", 0.0, 0.95, 0.75)
    coherence_threshold = st.slider("Coherence threshold", 0.0, 1.0, 0.4)

    if st.button("Run leak-location algorithm", type="primary"):
        try:
            result = run_leak_analysis(
                tuple(data["channel_1"].tolist()),
                tuple(data["channel_2"].tolist()),
                float(sampling_rate),
                float(wave_speed),
                float(sensor_spacing),
                int(segments),
                float(overlap),
                float(coherence_threshold),
            )
            st.session_state["leak_analysis"] = result
            st.session_state["leak_analysis_recording"] = selected_name
        except ValueError as error:
            st.error(f"Could not run leak analysis: {error}")

    result = st.session_state.get("leak_analysis")
    result_recording = st.session_state.get("leak_analysis_recording")
    if not isinstance(result, LeakAnalysis) or result_recording != selected_name:
        st.info("Set the parameters and run the algorithm to view processed output.")
    else:
        st.metric(
            "Estimated leak distance from channel 1",
            f"{result.leak_distance_m:.3f} m",
        )
        st.caption(
            f"Peak time delay: {result.peak_lag_s * 1000:.3f} ms; "
            f"segment length: {result.segment_length:,} samples"
        )

        spectrum = go.Figure()
        magnitude = abs(result.cross_spectrum)
        spectrum.add_trace(
            go.Scatter(
                x=result.frequency_hz,
                y=magnitude,
                mode="lines",
                name="Cross-spectrum",
            )
        )
        spectrum.add_trace(
            go.Scatter(
                x=result.frequency_hz[result.leak_band],
                y=magnitude[result.leak_band],
                mode="markers",
                name="Coherence-selected",
            )
        )
        spectrum.update_layout(
            title="Coherence-filtered cross-spectrum",
            xaxis_title="Frequency (Hz)",
            yaxis_title="Magnitude",
            height=400,
        )
        st.plotly_chart(spectrum, use_container_width=True)

        coherence_plot = go.Figure()
        coherence_plot.add_trace(
            go.Scatter(
                x=result.frequency_hz,
                y=result.coherence,
                mode="lines",
                name="MSC",
            )
        )
        coherence_plot.update_layout(
            title="Magnitude-squared coherence",
            xaxis_title="Frequency (Hz)",
            yaxis_title="Coherence",
            yaxis_range=[0, 1],
            height=400,
        )
        st.plotly_chart(coherence_plot, use_container_width=True)

        correlation_plot = go.Figure()
        correlation_plot.add_trace(
            go.Scatter(
                x=result.lag_s * 1000,
                y=result.correlation,
                mode="lines",
                name="Correlation",
            )
        )
        correlation_plot.add_trace(
            go.Scatter(
                x=result.lag_s * 1000,
                y=result.envelope,
                mode="lines",
                name="Envelope",
            )
        )
        correlation_plot.add_trace(
            go.Scatter(
                x=[result.peak_lag_s * 1000],
                y=[result.envelope.max()],
                mode="markers",
                name="Selected peak",
            )
        )
        correlation_plot.update_layout(
            title="Filtered cross-correlation",
            xaxis_title="Lag (ms)",
            yaxis_title="Correlation",
            height=500,
        )
        st.plotly_chart(correlation_plot, use_container_width=True)
