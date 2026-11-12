"""Wrapper around Red Pitaya's convert_tool.exe."""

# Path gives us safe, platform-independent file and folder operations.
from pathlib import Path
# subprocess lets Python run the external Red Pitaya conversion program.
import subprocess


def convert_bin_to_csv(bin_path: Path, client_dir: Path) -> Path:
    """Convert one BIN recording to the CSV format produced by Red Pitaya."""
    # Turn both paths into absolute paths so later checks do not depend on
    # whichever folder the user happened to run the program from.
    bin_path = bin_path.resolve()
    converter = (client_dir / "convert_tool.exe").resolve()

    # Stop early with a useful message if the input recording is unavailable.
    if not bin_path.is_file():
        raise FileNotFoundError(f"BIN file not found: {bin_path}")
    # The converter executable is required in order to create the CSV file.
    if not converter.is_file():
        raise FileNotFoundError(f"Converter not found: {converter}")

    # Build the same command a user would type: executable, input file, and
    # the option requesting CSV output.
    command = [str(converter), str(bin_path), "-f", "CSV"]

    # Run the external program and collect its text output for the user.
    result = subprocess.run(
        command,
        # The converter expects to run from the client folder.
        cwd=str(client_dir.resolve()),
        # Capture messages so they can be printed in a controlled way below.
        capture_output=True,
        text=True,
        # We inspect the return code ourselves to provide a project-specific
        # error message.
        check=False,
    )

    # Print normal progress information when the converter provides it.
    if result.stdout:
        print(result.stdout.strip())
    # Print diagnostic information as well, if any was produced.
    if result.stderr:
        print(result.stderr.strip())

    # A non-zero exit code means the external conversion did not succeed.
    if result.returncode != 0:
        raise RuntimeError(
            f"Red Pitaya converter failed with exit code {result.returncode}."
        )

    # Red Pitaya uses the input name with a .csv suffix for the output file.
    csv_path = bin_path.with_suffix(".csv")
    # Do not claim success unless the expected output really exists.
    if not csv_path.is_file():
        raise RuntimeError(
            "The converter reported completion, but the expected CSV "
            f"was not created: {csv_path}"
        )

    # Tell the user which file is now ready for loading.
    print(f"CSV created: {csv_path.name}")
    return csv_path
