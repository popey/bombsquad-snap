import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

spec = importlib.util.spec_from_file_location("download_build", Path(__file__).resolve().parents[1] / "scripts/download-build.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def archive(name="BombSquad/bombsquad"):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as tar:
        entry = tarfile.TarInfo(name)
        entry.size = 4
        tar.addfile(entry, io.BytesIO(b"game"))
    return io.BytesIO(output.getvalue())


class DownloadTests(unittest.TestCase):
    def test_current_and_moved_release_extract_the_same_version(self):
        for moved in (False, True):
            replies = [archive()]
            if moved:
                replies.insert(0, HTTPError("url", 404, "missing", {}, None))
            with self.subTest(moved=moved), tempfile.TemporaryDirectory() as tmp, patch.object(module, "urlopen", side_effect=replies) as fetch:
                module.download("1.8.8", Path(tmp))
                self.assertEqual((Path(tmp) / "bombsquad").read_bytes(), b"game")
                urls = [call.args[0].full_url for call in fetch.call_args_list]
                expected = [f"{module.ROOT}/BombSquad_Linux_x86_64_1.8.8.tar.gz"]
                if moved:
                    expected.append(f"{module.ROOT}/old/BombSquad_Linux_x86_64_1.8.8.tar.gz")
                self.assertEqual(urls, expected)

    def test_server_and_permission_failures_do_not_fall_back(self):
        for status in (403, 429, 500):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp, patch.object(module, "urlopen", side_effect=HTTPError("url", status, "error", {}, None)) as fetch:
                with self.assertRaises(HTTPError):
                    module.download("1.8.8", Path(tmp))
                self.assertEqual(fetch.call_count, 1)

    def test_missing_archive_fails_after_two_locations(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(module, "urlopen", side_effect=HTTPError("url", 404, "missing", {}, None)) as fetch:
            with self.assertRaises(HTTPError):
                module.download("1.8.8", Path(tmp))
            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_bad_payload_and_unsafe_archive_fail_without_fallback(self):
        for response in (io.BytesIO(b"<html>error</html>"), archive("../../escape"), archive("BombSquad/other")):
            with tempfile.TemporaryDirectory() as tmp, patch.object(module, "urlopen", return_value=response) as fetch:
                with self.assertRaises((tarfile.TarError, ValueError)):
                    module.download("1.8.8", Path(tmp))
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_invalid_versions_never_make_requests(self):
        with patch.object(module, "urlopen") as fetch:
            for version in ("../1.8.8", "1.8.8/evil", "latest", "1.8.8\n"):
                with self.assertRaises(ValueError):
                    module.download(version, Path("unused"))
            fetch.assert_not_called()
