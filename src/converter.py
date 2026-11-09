"""Wrapper around Red Pitaya's convert_tool.exe."""

from pathlib import Path
import subprocess


def convert_bin_to_csv(bin_path: Path, client_dir: Path) -> Path:
    """Convert one BIN recording to the CSV format produced by Red Pitaya."""
    bin_path = bin_path.resolve()
    converter = (client_dir / "convert_tool.exe").resolve()

    if not bin_path.is_file():
        raise FileNotFoundError(f"BIN file not found: {bin_path}")
    if not converter.is_file():
        raise FileNotFoundError(f"Converter not found: {converter}")

    command = [str(converter), str(bin_path), "-f", "CSV"]

    result = subprocess.run(
        command,
        cwd=str(client_dir.resolve()),
        capture_output=True,
        text=True,
        check=False,
    )

    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())

    if result.returncode != 0:
        raise RuntimeError(
            f"Red Pitaya converter failed with exit code {result.returncode}."
        )

    csv_path = bin_path.with_suffix(".csv")
    if not csv_path.is_file():
        raise RuntimeError(
            "The converter reported completion, but the expected CSV "
            f"was not created: {csv_path}"
        )

    print(f"CSV created: {csv_path.name}")
    return csv_path
