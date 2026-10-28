from __future__ import annotations

import argparse
import json
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ARTIFACT_ROOT = "https://files.ballistica.net/bombsquad/builds"
USER_AGENT = "popey/bombsquad-snap upstream-check"
STABLE_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
BUILD_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?$")
ARTIFACT_NAME = re.compile(r"^BombSquad_Linux_x86_64_(.+)\.tar\.gz$")
VERSION_LINE = re.compile(r"(?m)^version:\s*(['\"]?)([^'\"\s]+)\1\s*$")
# Ballistica's live service requires post-release build 22902, while v1.7.63
# contains build 22870 and is rejected as `tooold`.
BLOCKED_RELEASES = frozenset({"1.7.63"})


class BuildListing(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.versions: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href") or ""
        match = ARTIFACT_NAME.fullmatch(href)
        if match and BUILD_VERSION.fullmatch(match[1]):
            self.versions.add(match[1])


def parse_latest_release(listing: str, include_prereleases: bool = False) -> str | None:
    parser = BuildListing()
    parser.feed(listing)
    if not parser.versions:
        raise ValueError("No BombSquad Linux x86-64 builds found in current directory")
    versions = [
        version for version in parser.versions
        if include_prereleases or STABLE_VERSION.fullmatch(version)
    ]
    return max(versions, key=version_tuple, default=None)


def version_tuple(version: str) -> tuple[int, int, int, int, int]:
    match = BUILD_VERSION.fullmatch(version)
    if not match:
        raise ValueError(f"Unsupported recipe version: {version}")
    major, minor, patch, phase, number = match.groups()
    return (int(major), int(minor), int(patch),
            {"a": 0, "b": 1, "rc": 2, None: 3}[phase], int(number or 0))


def determine_update(current: str, latest: str | None) -> str | None:
    if latest is None or latest in BLOCKED_RELEASES:
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
    # Migrate the pinned archive source only when updating its version.
    updated, count = re.subn(
        r"(?m)^    source: https://files\.ballistica\.net/bombsquad/builds/(?:old/)?"
        r"BombSquad_Linux_x86_64_\$SNAPCRAFT_PROJECT_VERSION\.tar\.gz$",
        f"    source: {ARTIFACT_ROOT}/BombSquad_Linux_x86_64_$SNAPCRAFT_PROJECT_VERSION.tar.gz",
        updated,
    )
    if count != 1:
        raise ValueError(f"Expected exactly one BombSquad artifact source in {path}, found {count}")
    path.write_text(updated)


def artifact_url(version: str) -> str:
    return f"{ARTIFACT_ROOT}/BombSquad_Linux_x86_64_{version}.tar.gz"


def fetch_latest_release() -> str:
    request = Request(f"{ARTIFACT_ROOT}/", headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


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
    parser.add_argument("--include-prereleases", action="store_true",
                        help="Also follow alpha, beta, and release-candidate builds")
    args = parser.parse_args()

    current = read_recipe_version(args.recipe)
    listing = fetch_latest_release()
    latest = parse_latest_release(listing, args.include_prereleases)
    update = determine_update(current, latest)
    url = artifact_url(latest) if latest else ""

    if update:
        verify_artifact(url)
        if args.write:
            update_recipe_version(args.recipe, update)

    outputs = {
        "current": current,
        "latest": latest or "",
        "needs_update": "true" if update else "false",
        "artifact_url": url,
        "release_url": f"{ARTIFACT_ROOT}/",
    }
    if args.github_output:
        write_outputs(args.github_output, outputs)
    print(json.dumps(outputs, sort_keys=True))


if __name__ == "__main__":
    main()
