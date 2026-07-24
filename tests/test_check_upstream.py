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


class ReleaseParsingTest(unittest.TestCase):
    def test_accepts_a_stable_semantic_release(self):
        self.assertEqual(
            parse_latest_release({"tag_name": "v1.7.63", "draft": False, "prerelease": False}),
            "1.7.63",
        )

    def test_rejects_prereleases_and_alpha_versions(self):
        with self.assertRaises(ValueError):
            parse_latest_release({"tag_name": "v1.8.0a55", "draft": False, "prerelease": True})
        with self.assertRaises(ValueError):
            parse_latest_release({"tag_name": "v1.8.0a55", "draft": False, "prerelease": False})

    def test_only_updates_to_a_newer_version(self):
        payload = {"tag_name": "v1.7.63", "draft": False, "prerelease": False}
        self.assertEqual(determine_update("1.7.39", payload), "1.7.63")
        self.assertIsNone(determine_update("1.7.63", payload))
        self.assertIsNone(determine_update("1.8.0", payload))


class RecipeTest(unittest.TestCase):
    def test_updates_only_the_top_level_recipe_version(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe = Path(directory) / "snapcraft.yaml"
            recipe.write_text(
                "name: bombsquad\n"
                "version: '1.7.39'\n"
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

    def test_builds_the_archived_linux_artifact_url(self):
        self.assertEqual(
            artifact_url("1.7.63"),
            "https://files.ballistica.net/bombsquad/builds/old/BombSquad_Linux_x86_64_1.7.63.tar.gz",
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
    def test_recipe_downloads_from_the_verified_archive(self):
        recipe = Path(__file__).parents[1] / "snap" / "snapcraft.yaml"
        expected = (
            f"source: {ARTIFACT_ROOT}/"
            "BombSquad_Linux_x86_64_$SNAPCRAFT_PROJECT_VERSION.tar.gz"
        )
        lines = recipe.read_text().splitlines()
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
