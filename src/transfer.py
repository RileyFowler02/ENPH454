"""Download Red Pitaya recordings and their associated log files."""

from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote
import re
from typing import cast

import requests
from bs4 import BeautifulSoup


def _recording_timestamp(filename: str):
    """Return a sortable timestamp from names like data_file_2026-10-29_20-43-01.bin."""
    match = re.search(r"(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})", filename)
    return match.group(1) if match else ""


def find_latest_recording(listing_url: str) -> str:
    """
    Find the newest .bin link on the Red Pitaya listing page.

    The page must expose ordinary HTML links to the recording files.
    If filenames contain timestamps, those timestamps determine which is newest.
    """
    response = requests.get(listing_url, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    candidates = []

    for anchor in soup.find_all("a", href=True):
        full_url = urljoin(listing_url, cast(str, anchor["href"]))
        filename = unquote(Path(urlparse(full_url).path).name)

        # Match only the binary file, not its .log or .log.lost companions.
        if filename.lower().endswith(".bin"):
            candidates.append((full_url, filename))

    if not candidates:
        raise RuntimeError(
            "No .bin download links were found on the listing page. "
            "Use --url with a direct .bin link, or inspect the page's HTML."
        )

    # Prefer embedded recording timestamps. Fall back to the last link in page order.
    timestamped = [
        item for item in candidates if _recording_timestamp(item[1])
    ]
    if timestamped:
        return max(timestamped, key=lambda item: _recording_timestamp(item[1]))[0]

    return candidates[-1][0]


def download_recording(bin_url: str, data_dir: Path) -> list[Path]:
    """Download the .bin, .bin.log, and .bin.log.lost files."""
    data_dir.mkdir(parents=True, exist_ok=True)

    filename = unquote(Path(urlparse(bin_url).path).name)
    if not filename.lower().endswith(".bin"):
        raise ValueError("The supplied URL must point directly to a .bin file.")

    urls = [bin_url, bin_url + ".log", bin_url + ".log.lost"]
    paths = [
        data_dir / filename,
        data_dir / (filename + ".log"),
        data_dir / (filename + ".log.lost"),
    ]

    with requests.Session() as session:
        for url, destination in zip(urls, paths):
            print(f"Downloading {destination.name}...")

            response = session.get(url, stream=True, timeout=60)
            response.raise_for_status()

            temporary = destination.with_name(destination.name + ".part")
            try:
                with temporary.open("wb") as output:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            output.write(chunk)

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

                temporary.replace(destination)
                print(
                    f"Downloaded: {destination.name} "
                    f"({destination.stat().st_size:,} bytes)"
                )
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            finally:
                response.close()

    return paths
