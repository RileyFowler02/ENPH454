"""Download Red Pitaya recordings and their associated log files."""

# Path handles local file names and destinations.
from pathlib import Path
# These helpers turn relative links into complete URLs and decode file names.
from urllib.parse import urljoin, urlparse, unquote
# Regular expressions locate timestamps embedded in recording names.
import re
# cast tells the type checker that BeautifulSoup's href value is text.
from typing import cast

# requests performs the HTTP downloads.
import requests
# BeautifulSoup parses the HTML listing page.
from bs4 import BeautifulSoup


def _recording_timestamp(filename: str):
    """Return a sortable timestamp from names like data_file_2026-10-29_20-43-01.bin."""
    # Look for the timestamp format used by the Red Pitaya recording names.
    match = re.search(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})", filename)
    # An empty string sorts before a real timestamp when no timestamp exists.
    return match.group(1) if match else ""


def find_latest_recording(listing_url: str) -> str:
    """
    Find the newest .bin link on the Red Pitaya listing page.

    The page must expose ordinary HTML links to the recording files.
    If filenames contain timestamps, those timestamps determine which is newest.
    """
    # Request the page containing links to recordings.
    response = requests.get(listing_url, timeout=30)
    # Convert HTTP errors into an exception instead of silently continuing.
    response.raise_for_status()

    # Parse the returned HTML so its links can be inspected.
    soup = BeautifulSoup(response.text, "html.parser")
    # Each item will contain the complete URL and the decoded file name.
    candidates = []

    # Examine every anchor that has an href attribute.
    for anchor in soup.find_all("a", href=True):
        # Resolve links relative to the listing page and decode escaped names.
        full_url = urljoin(listing_url, cast(str, anchor["href"]))
        filename = unquote(Path(urlparse(full_url).path).name)

        # Match only the binary file, not its .log or .log.lost companions.
        if filename.lower().endswith(".bin"):
            candidates.append((full_url, filename))

    # Without a binary link there is no recording to download.
    if not candidates:
        raise RuntimeError(
            "No .bin download links were found on the listing page. "
            "Use --url with a direct .bin link, or inspect the page's HTML."
        )

    # Prefer embedded recording timestamps. Fall back to the last link in page order.
    timestamped = [
        item for item in candidates if _recording_timestamp(item[1])
    ]
    # Select the candidate with the greatest timestamp when timestamps exist.
    if timestamped:
        return max(timestamped, key=lambda item: _recording_timestamp(item[1]))[0]

    # If timestamps are absent, assume the page lists newest recordings last.
    return candidates[-1][0]


def download_recording(bin_url: str, data_dir: Path) -> list[Path]:
    """Download the .bin, .bin.log, and .bin.log.lost files."""
    # Create the destination folder if this is the first download.
    data_dir.mkdir(parents=True, exist_ok=True)

    # Extract the file name from the URL and decode URL-escaped characters.
    filename = unquote(Path(urlparse(bin_url).path).name)
    # The three related files are based on one binary recording name.
    if not filename.lower().endswith(".bin"):
        raise ValueError("The supplied URL must point directly to a .bin file.")

    # Download the binary plus the two logs generated alongside it.
    urls = [bin_url, bin_url + ".log", bin_url + ".log.lost"]
    # Give each downloaded URL its expected local destination.
    paths = [
        data_dir / filename,
        data_dir / (filename + ".log"),
        data_dir / (filename + ".log.lost"),
    ]

    # Reuse one HTTP session for all three related requests.
    with requests.Session() as session:
        # Download each URL and write it to the matching destination.
        for url, destination in zip(urls, paths):
            print(f"Downloading {destination.name}...")

            # Stream large binary files rather than loading them all into RAM.
            response = session.get(url, stream=True, timeout=60)
            response.raise_for_status()

            # A partial file prevents an interrupted download from looking
            # like a completed recording.
            temporary = destination.with_name(destination.name + ".part")
            try:
                # Write chunks incrementally to the temporary path.
                with temporary.open("wb") as output:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            output.write(chunk)

                # An empty response is not a usable recording or log.
                if temporary.stat().st_size == 0:
                    raise RuntimeError(f"Downloaded an empty file: {url}")

                # Avoid mistaking an HTML error/login page for a data file.
                with temporary.open("rb") as source:
                    beginning = source.read(512).lstrip().lower()

                if (
                    beginning.startswith(b"<!doctype html")
                    or beginning.startswith(b"<html")
                ):
                    raise RuntimeError(
                        f"The server returned an HTML page instead of a file: {url}"
                    )

                # Rename atomically so the final name only appears after a
                # complete, validated download.
                temporary.replace(destination)
                print(
                    f"Downloaded: {destination.name} "
                    f"({destination.stat().st_size:,} bytes)"
                )
            except Exception:
                # Remove an incomplete file before passing the original error
                # to the caller.
                temporary.unlink(missing_ok=True)
                raise
            finally:
                # Release the HTTP response even when a write or validation
                # error occurs.
                response.close()

    # Return all three local paths in the same order as the URL list.
    return paths
