from email.message import Message
import tempfile
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from scripts.check_upstream import (
    ARTIFACT_ROOT,
    artifact_url,
    determine_update,
    parse_latest_release,
    read_recipe_version,
    update_recipe_version,
    verify_artifact,
    write_outputs,
)


def listing(*versions):
    return "".join(
        f'<a href="BombSquad_Linux_x86_64_{version}.tar.gz">build</a>'
        for version in versions
    )


class ReleaseParsingTest(unittest.TestCase):
    def test_selects_latest_stable_numerically(self):
        self.assertEqual(parse_latest_release(listing("1.7.9", "1.7.64", "1.8.0b24")), "1.7.64")

    def test_prerelease_only_directory_has_no_stable_update(self):
        self.assertIsNone(parse_latest_release(listing("1.8.0b24")))
        self.assertIsNone(determine_update("1.7.39", None))

    def test_orders_prereleases_and_final_releases(self):
        versions = ["1.8.0a55", "1.8.0b9", "1.8.0b24", "1.8.0rc1", "1.8.0"]
        for end in range(1, len(versions) + 1):
            with self.subTest(end=end):
                self.assertEqual(parse_latest_release(listing(*versions[:end]), True), versions[end - 1])

    def test_ignores_archived_server_and_other_architecture_links(self):
        html = listing("1.8.0b24") + (
            '<a href="old/BombSquad_Linux_x86_64_9.0.0.tar.gz">old</a>'
            '<a href="BombSquad_Server_Linux_x86_64_9.0.0.tar.gz">server</a>'
            '<a href="BombSquad_Linux_Arm64_9.0.0.tar.gz">arm</a>'
            '<a href="https://example.com/BombSquad_Linux_x86_64_9.0.0.tar.gz">external</a>'
        )
        self.assertEqual(parse_latest_release(html, True), "1.8.0b24")

    def test_rejects_missing_or_invalid_builds(self):
        for html in ("<html>unavailable</html>", listing("bogus")):
            with self.assertRaisesRegex(ValueError, "No BombSquad"):
                parse_latest_release(html)

    def test_only_updates_to_a_newer_version(self):
        self.assertEqual(determine_update("1.7.39", "1.7.64"), "1.7.64")
        self.assertEqual(determine_update("1.8.0b9", "1.8.0b24"), "1.8.0b24")
        self.assertIsNone(determine_update("1.8.0b24", "1.8.0b24"))
        self.assertIsNone(determine_update("1.8.0", "1.8.0b24"))

    def test_skips_a_release_blocked_by_the_live_service(self):
        self.assertIsNone(determine_update("1.7.39", "1.7.63"))


class RecipeTest(unittest.TestCase):
    def test_updates_only_the_top_level_recipe_version(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe = Path(directory) / "snapcraft.yaml"
            recipe.write_text(
                "name: bombsquad\n"
                "version: '1.7.39'\n"
                "    source: https://files.ballistica.net/bombsquad/builds/old/BombSquad_Linux_x86_64_$SNAPCRAFT_PROJECT_VERSION.tar.gz\n"
                "parts:\n"
                "  nested:\n"
                "    version: 'must-not-change'\n"
            )

            self.assertEqual(read_recipe_version(recipe), "1.7.39")
            update_recipe_version(recipe, "1.7.63")

            self.assertEqual(
                recipe.read_text(),
                "name: bombsquad\n"
                "version: '1.7.63'\n"
                "    source: https://files.ballistica.net/bombsquad/builds/BombSquad_Linux_x86_64_$SNAPCRAFT_PROJECT_VERSION.tar.gz\n"
                "parts:\n"
                "  nested:\n"
                "    version: 'must-not-change'\n",
            )

    def test_rejects_duplicate_top_level_recipe_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe = Path(directory) / "snapcraft.yaml"
            recipe.write_text("name: bombsquad\nversion: '1.7.39'\nversion: '1.7.40'\n")

            with self.assertRaises(ValueError):
                read_recipe_version(recipe)
            with self.assertRaises(ValueError):
                update_recipe_version(recipe, "1.7.63")

    def test_builds_the_current_linux_artifact_url(self):
        self.assertEqual(
            artifact_url("1.7.63"),
            "https://files.ballistica.net/bombsquad/builds/BombSquad_Linux_x86_64_1.7.63.tar.gz",
        )


class ArtifactVerificationTest(unittest.TestCase):
    @patch("scripts.check_upstream.urlopen")
    def test_accepts_a_gzip_artifact(self, mocked_urlopen):
        response = MagicMock()
        response.status = 206
        response.read.return_value = b"\x1f\x8b"
        mocked_urlopen.return_value.__enter__.return_value = response

        verify_artifact(artifact_url("1.7.63"))

        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(request.headers["Range"], "bytes=0-1")
        response.read.assert_called_once_with(2)

    @patch("scripts.check_upstream.urlopen")
    def test_rejects_a_non_gzip_response(self, mocked_urlopen):
        response = MagicMock()
        response.status = 200
        response.read.return_value = b"<!"
        mocked_urlopen.return_value.__enter__.return_value = response

        with self.assertRaisesRegex(ValueError, "gzip"):
            verify_artifact(artifact_url("1.7.63"))

    @patch("scripts.check_upstream.urlopen")
    def test_rejects_an_unsuccessful_status(self, mocked_urlopen):
        mocked_urlopen.side_effect = HTTPError(
            artifact_url("1.7.63"),
            500,
            "Internal Server Error",
            Message(),
            None,
        )

        with self.assertRaisesRegex(ValueError, "HTTP 500"):
            verify_artifact(artifact_url("1.7.63"))


class GitHubOutputTest(unittest.TestCase):
    def test_rejects_values_that_could_inject_an_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "github-output"

            with self.assertRaisesRegex(ValueError, "line break"):
                write_outputs(output, {"release_url": "https://example.com\ninjected=true"})

            self.assertFalse(output.exists())


class RecipeSourceTest(unittest.TestCase):
    def test_updated_recipe_downloads_from_the_verified_current_directory(self):
        recipe = Path(__file__).parents[1] / "snap" / "snapcraft.yaml"
        expected = (
            f"source: {ARTIFACT_ROOT}/"
            "BombSquad_Linux_x86_64_$SNAPCRAFT_PROJECT_VERSION.tar.gz"
        )
        with tempfile.TemporaryDirectory() as directory:
            updated = Path(directory) / "snapcraft.yaml"
            updated.write_text(recipe.read_text())
            update_recipe_version(updated, "1.8.0b24")
            lines = updated.read_text().splitlines()
        parts_start = lines.index("parts:")
        part_start = lines.index("  bombsquad:", parts_start + 1)
        part_lines = []
        for line in lines[part_start + 1 :]:
            if line and not line.startswith("    "):
                break
            part_lines.append(line)
        sources = [line.strip() for line in part_lines if line.startswith("    source:")]

        self.assertEqual(sources, [expected])


if __name__ == "__main__":
    unittest.main()
