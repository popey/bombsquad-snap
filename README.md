# bombsquad-snap

[![bombsquad](https://github.com/popey/bombsquad-snap/actions/workflows/test-snap-can-build.yml/badge.svg)](https://github.com/popey/bombsquad-snap/actions)
[![bombsquad](https://snapcraft.io/bombsquad/badge.svg)](https://snapcraft.io/bombsquad)
[![bombsquad](https://snapcraft.io/bombsquad/trending.svg?name=0)](https://snapcraft.io/bombsquad)

![Alt](https://repobeats.axiom.co/api/embed/bacd2cfef7746109a4bb233028d70ba63b111b67.svg "Repobeats analytics image")

[![Get it from the Snap Store](https://snapcraft.io/static/images/badges/en/snap-store-black.svg)](https://snapcraft.io/bombsquad)

## Upstream updates

The daily `Check for stable BombSquad releases` workflow compares the recipe with Ballistica's latest non-prerelease GitHub release. Before opening a version-bump pull request it verifies the matching archived Linux x86-64 tarball exists and builds the updated snap. Prereleases are rejected and the recipe is never downgraded.

Run the checker locally with:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_upstream.py
```
