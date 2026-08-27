import sys
import unittest
import warnings
from unittest.mock import patch

from pyiron_snippets.versions import VersionInfo

from pothenon import validator


class TestGetCondaPackages(unittest.TestCase):
    def _make_conda_output(self, packages):
        import json

        return json.dumps(packages)

    def test_returns_dict_of_packages(self):
        conda_output = self._make_conda_output(
            [
                {"name": "numpy", "version": "1.26.0", "channel": "defaults"},
                {"name": "scipy", "version": "1.11.0", "channel": "defaults"},
            ]
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = conda_output
            validator._get_conda_packages.cache_clear()
            result = validator._get_conda_packages()
        self.assertIn("numpy", result)
        self.assertEqual(result["numpy"]["version"], "1.26.0")
        self.assertEqual(result["numpy"]["source"], "conda")

    def test_pip_channel_mapped_to_pip_source(self):
        conda_output = self._make_conda_output(
            [{"name": "mypackage", "version": "0.1.0", "channel": "pypi"}]
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = conda_output
            validator._get_conda_packages.cache_clear()
            result = validator._get_conda_packages()
        self.assertEqual(result["mypackage"]["source"], "pip")

    def test_file_not_found_returns_empty_dict(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            validator._get_conda_packages.cache_clear()
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                result = validator._get_conda_packages()
            self.assertEqual(result, {})
            self.assertTrue(
                any("conda list" in str(warning.message) for warning in w)
            )

    def test_called_process_error_returns_empty_dict(self):
        import subprocess

        with patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "conda"),
        ):
            validator._get_conda_packages.cache_clear()
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                result = validator._get_conda_packages()
            self.assertEqual(result, {})
            self.assertTrue(len(w) > 0)

    def test_invalid_json_returns_empty_dict(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "not valid json"
            validator._get_conda_packages.cache_clear()
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                result = validator._get_conda_packages()
            self.assertEqual(result, {})
            self.assertTrue(len(w) > 0)

    def test_packages_missing_name_or_version_are_skipped(self):
        import json

        conda_output = json.dumps(
            [
                {"name": "numpy", "version": "1.26.0", "channel": "defaults"},
                {"version": "1.0.0", "channel": "defaults"},  # no name
                {"name": "broken", "channel": "defaults"},  # no version
            ]
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = conda_output
            validator._get_conda_packages.cache_clear()
            result = validator._get_conda_packages()
        self.assertIn("numpy", result)
        self.assertNotIn("broken", result)

    def tearDown(self):
        validator._get_conda_packages.cache_clear()


class TestClassifyPackage(unittest.TestCase):
    def _stdlib_package(self):
        return VersionInfo(module="os", qualname="path", version=None)

    def test_stdlib_module_classified_as_stdlib(self):
        pkg = VersionInfo(module="os", qualname="path", version=None)
        result = validator.classify_package(pkg)
        self.assertEqual(result, "stdlib")

    def test_dotted_stdlib_module_classified_as_stdlib(self):
        # e.g. os.path — top-level is "os", which is stdlib
        pkg = VersionInfo(module="os.path", qualname="join", version=None)
        result = validator.classify_package(pkg)
        self.assertEqual(result, "stdlib")

    def test_conda_package_classified_as_conda(self):
        conda_data = {"numpy": {"version": "1.26.0", "source": "conda"}}
        pkg = VersionInfo(module="numpy", qualname="array", version="1.26.0")
        with patch.object(validator, "_get_conda_packages", return_value=conda_data):
            result = validator.classify_package(pkg)
        self.assertEqual(result, "conda")

    def test_pip_package_classified_as_pip(self):
        conda_data = {"mypackage": {"version": "0.1.0", "source": "pip"}}
        pkg = VersionInfo(module="mypackage", qualname="func", version="0.1.0")
        with patch.object(validator, "_get_conda_packages", return_value=conda_data):
            result = validator.classify_package(pkg)
        self.assertEqual(result, "pip")

    def test_dotted_module_path_uses_top_level_for_lookup(self):
        conda_data = {"numpy": {"version": "1.26.0", "source": "conda"}}
        pkg = VersionInfo(
            module="numpy.linalg", qualname="norm", version="1.26.0"
        )
        with patch.object(validator, "_get_conda_packages", return_value=conda_data):
            result = validator.classify_package(pkg)
        self.assertEqual(result, "conda")

    def test_unknown_package_returns_unknown_and_warns(self):
        conda_data = {}
        pkg = VersionInfo(module="unknownpkg", qualname="func", version="9.9.9")
        with patch.object(validator, "_get_conda_packages", return_value=conda_data):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                result = validator.classify_package(pkg)
        self.assertEqual(result, "unknown")
        self.assertTrue(len(w) > 0)

    def test_version_mismatch_returns_unknown_and_warns(self):
        conda_data = {"numpy": {"version": "1.24.0", "source": "conda"}}
        pkg = VersionInfo(module="numpy", qualname="array", version="1.26.0")
        with patch.object(validator, "_get_conda_packages", return_value=conda_data):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                result = validator.classify_package(pkg)
        self.assertEqual(result, "unknown")
        self.assertTrue(len(w) > 0)


if __name__ == "__main__":
    unittest.main()
