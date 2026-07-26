from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

RELEASE_API = "https://api.github.com/repos/efroemling/ballistica/releases/latest"
ARTIFACT_ROOT = "https://files.ballistica.net/bombsquad/builds/old"
USER_AGENT = "popey/bombsquad-snap upstream-check"
STABLE_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
VERSION_LINE = re.compile(r"(?m)^version:\s*(['\"]?)([^'\"\s]+)\1\s*$")
# Ballistica's live service requires post-release build 22902, while v1.7.63
# contains build 22870 and is rejected as `tooold`.
BLOCKED_RELEASES = frozenset({"1.7.63"})


def parse_latest_release(payload: dict[str, Any]) -> str:
    if payload.get("draft") or payload.get("prerelease"):
        raise ValueError("Latest GitHub release is not stable")
    version = str(payload.get("tag_name") or "").removeprefix("v")
    if not STABLE_VERSION.fullmatch(version):
        raise ValueError(f"Unsupported stable release version: {version or 'missing'}")
    return version


def version_tuple(version: str) -> tuple[int, int, int]:
    if not STABLE_VERSION.fullmatch(version):
        raise ValueError(f"Unsupported recipe version: {version}")
    return tuple(int(part) for part in version.split("."))  # type: ignore[return-value]


def determine_update(current: str, payload: dict[str, Any]) -> str | None:
    latest = parse_latest_release(payload)
    if latest in BLOCKED_RELEASES:
        return None
    return latest if version_tuple(latest) > version_tuple(current) else None


def _single_version_match(text: str, path: Path) -> re.Match[str]:
    matches = list(VERSION_LINE.finditer(text))
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one top-level version in {path}, found {len(matches)}")
    return matches[0]


def read_recipe_version(path: Path) -> str:
    match = _single_version_match(path.read_text(), path)
    return match.group(2)


def update_recipe_version(path: Path, version: str) -> None:
    text = path.read_text()
    _single_version_match(text, path)
    updated = VERSION_LINE.sub(f"version: '{version}'", text, count=1)
    path.write_text(updated)


def artifact_url(version: str) -> str:
    return f"{ARTIFACT_ROOT}/BombSquad_Linux_x86_64_{version}.tar.gz"


def fetch_latest_release() -> dict[str, Any]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request(RELEASE_API, headers=headers), timeout=30) as response:
        return json.load(response)


def verify_artifact(url: str) -> None:
    request = Request(url, headers={"Range": "bytes=0-1", "User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=90) as response:
            if response.status not in {200, 206}:
                raise ValueError(f"Artifact check returned HTTP {response.status}")
            if response.read(2) != b"\x1f\x8b":
                raise ValueError("Artifact check did not return a gzip archive")
    except HTTPError as error:
        raise ValueError(f"Artifact check returned HTTP {error.code}") from error


def write_outputs(path: Path, values: dict[str, str]) -> None:
    for key, value in values.items():
        if "\n" in value or "\r" in value:
            raise ValueError(f"GitHub output {key!r} contains a line break")
    with path.open("a") as output:
        for key, value in values.items():
            output.write(f"{key}={value}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check for a stable BombSquad Linux release")
    parser.add_argument("--recipe", type=Path, default=Path("snap/snapcraft.yaml"))
    parser.add_argument("--write", action="store_true", help="Update the recipe when newer")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()

    current = read_recipe_version(args.recipe)
    payload = fetch_latest_release()
    latest = parse_latest_release(payload)
    update = determine_update(current, payload)
    url = artifact_url(latest)

    if update:
        verify_artifact(url)
        if args.write:
            update_recipe_version(args.recipe, update)

    outputs = {
        "current": current,
        "latest": latest,
        "needs_update": "true" if update else "false",
        "artifact_url": url,
        "release_url": str(payload.get("html_url") or ""),
    }
    if args.github_output:
        write_outputs(args.github_output, outputs)
    print(json.dumps(outputs, sort_keys=True))


if __name__ == "__main__":
    main()
