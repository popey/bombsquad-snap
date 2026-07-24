import tempfile
from pathlib import Path
import unittest

from scripts.check_upstream import (
    artifact_url,
    determine_update,
    parse_latest_release,
    read_recipe_version,
    update_recipe_version,
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
            recipe.write_text("name: bombsquad\nversion: '1.7.39'\nsource: $SNAPCRAFT_PROJECT_VERSION\n")

            self.assertEqual(read_recipe_version(recipe), "1.7.39")
            update_recipe_version(recipe, "1.7.63")

            self.assertEqual(
                recipe.read_text(),
                "name: bombsquad\nversion: '1.7.63'\nsource: $SNAPCRAFT_PROJECT_VERSION\n",
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


if __name__ == "__main__":
    unittest.main()
