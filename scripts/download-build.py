#!/usr/bin/env python3
"""Fetch the exact release, including after upstream moves it to the archive."""
from pathlib import Path
import re
import shutil
import sys
import tarfile
import tempfile
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = "https://files.ballistica.net/bombsquad/builds"


def download(version, destination):
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?", version):
        raise ValueError("Invalid release version")
    filename = f"BombSquad_Linux_x86_64_{version}.tar.gz"
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / filename
        for directory in ("", "old/"):
            url = f"{ROOT}/{directory}{filename}"
            try:
                request = Request(url, headers={"User-Agent": "popey/bombsquad-snap build"})
                with urlopen(request, timeout=90) as response, archive.open("wb") as output:
                    shutil.copyfileobj(response, output)
                print(f"Downloaded exact release from {url}")
                break
            except HTTPError as error:
                if error.code != 404 or directory:
                    raise
        # Extract safely before copying the archive's single top-level directory.
        # A malformed download must fail rather than selecting another version.
        extracted = Path(temporary) / "extracted"
        with tarfile.open(archive, "r:gz") as source:
            source.extractall(extracted, filter="data")
        roots = list(extracted.iterdir())
        if len(roots) != 1 or not roots[0].is_dir():
            raise ValueError("Expected one top-level build directory")
        if not (roots[0] / "bombsquad").is_file():
            raise ValueError("Build archive is missing the game executable")
        shutil.copytree(roots[0], destination, dirs_exist_ok=True, symlinks=True)


if __name__ == "__main__":
    download(sys.argv[1], Path(sys.argv[2]))
