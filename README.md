# bombsquad-snap

[![bombsquad](https://github.com/popey/bombsquad-snap/actions/workflows/test-snap-can-build.yml/badge.svg)](https://github.com/popey/bombsquad-snap/actions)
[![bombsquad](https://snapcraft.io/bombsquad/badge.svg)](https://snapcraft.io/bombsquad)
[![bombsquad](https://snapcraft.io/bombsquad/trending.svg?name=0)](https://snapcraft.io/bombsquad)

![Alt](https://repobeats.axiom.co/api/embed/bacd2cfef7746109a4bb233028d70ba63b111b67.svg "Repobeats analytics image")

[![Get it from the Snap Store](https://snapcraft.io/static/images/badges/en/snap-store-black.svg)](https://snapcraft.io/bombsquad)

## Upstream updates

BombSquad 1.8.3 uses `core26` for Ubuntu's SDL3 and Python 3.14 packages. Build locally with `snapcraft --use-lxd`.

The daily `Check for stable BombSquad releases` workflow compares the recipe with Linux x86-64 builds in [Ballistica's current builds directory](https://files.ballistica.net/bombsquad/builds/). Before opening a version-bump pull request it verifies the matching current Linux x86-64 tarball exists, updates both the version and source URL, and builds the updated snap. Prereleases are rejected and the recipe is never downgraded.

Run the checker locally with:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_upstream.py
```

The checker ignores `old/`, server builds, and other architectures. If only prereleases are available, stable-only checks report no update. Pass `--include-prereleases` to follow alpha, beta, and release-candidate builds. The pinned recipe keeps its archived source until an update is selected. Version 1.7.63 remains blocked because the live service rejects it.
