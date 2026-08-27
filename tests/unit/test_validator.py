import unittest
import warnings
from unittest.mock import MagicMock, patch

from pyiron_snippets.versions import VersionInfo

from pothenon import validator


def _make_dist(name, version, installer=None):
    """Create a mock distribution object mimicking importlib.metadata.Distribution."""
    meta = {"Name": name, "Version": version}
    if installer is not None:
        meta["Installer"] = installer

    dist = MagicMock()
    dist.metadata = meta
    return dist


class TestGetCondaPackages(unittest.TestCase):
    def setUp(self):
        validator._get_conda_packages.cache_clear()

    def tearDown(self):
        validator._get_conda_packages.cache_clear()

    def test_returns_dict_of_packages(self):
        mock_dists = [
            _make_dist("numpy", "1.26.0", installer="conda"),
            _make_dist("scipy", "1.11.0", installer="conda"),
        ]
        with patch("pothenon.validator.distributions", return_value=mock_dists):
            result = validator._get_conda_packages()
        self.assertIn("numpy", result)
        self.assertEqual(result["numpy"]["version"], "1.26.0")
        self.assertEqual(result["numpy"]["source"], "conda")

    def test_pip_installer_mapped_to_pip_source(self):
        mock_dists = [_make_dist("mypackage", "0.1.0", installer="pip")]
        with patch("pothenon.validator.distributions", return_value=mock_dists):
            result = validator._get_conda_packages()
        self.assertEqual(result["mypackage"]["source"], "pip")

    def test_no_installer_defaults_to_conda(self):
        mock_dists = [_make_dist("somepackage", "2.0.0")]
        with patch("pothenon.validator.distributions", return_value=mock_dists):
            result = validator._get_conda_packages()
        self.assertEqual(result["somepackage"]["source"], "conda")

    def test_packages_missing_name_are_skipped(self):
        meta_no_name = {"Name": None, "Version": "1.0.0"}
        dist_no_name = MagicMock()
        dist_no_name.metadata = meta_no_name
        mock_dists = [
            _make_dist("numpy", "1.26.0", installer="conda"),
            dist_no_name,
        ]
        with patch("pothenon.validator.distributions", return_value=mock_dists):
            result = validator._get_conda_packages()
        self.assertIn("numpy", result)
        self.assertEqual(len(result), 1)

    def test_packages_missing_version_are_skipped(self):
        meta_no_ver = {"Name": "broken"}
        dist_no_ver = MagicMock()
        dist_no_ver.metadata = meta_no_ver
        mock_dists = [
            _make_dist("numpy", "1.26.0", installer="conda"),
            dist_no_ver,
        ]
        with patch("pothenon.validator.distributions", return_value=mock_dists):
            result = validator._get_conda_packages()
        self.assertIn("numpy", result)
        self.assertNotIn("broken", result)


class TestClassifyPackage(unittest.TestCase):
    def test_stdlib_module_classified_as_stdlib(self):
        pkg = VersionInfo(module="os", qualname="path", version=None)
        result = validator.classify_package(pkg)
        self.assertEqual(result, ("os", "stdlib"))

    def test_dotted_stdlib_module_classified_as_stdlib(self):
        # e.g. os.path — top-level is "os", which is stdlib
        pkg = VersionInfo(module="os.path", qualname="join", version=None)
        result = validator.classify_package(pkg)
        self.assertEqual(result, ("os", "stdlib"))

    def test_conda_package_classified_as_conda(self):
        conda_data = {"numpy": {"version": "1.26.0", "source": "conda"}}
        pkg = VersionInfo(module="numpy", qualname="array", version="1.26.0")
        with patch.object(validator, "_get_conda_packages", return_value=conda_data):
            result = validator.classify_package(pkg)
        self.assertEqual(result, ("numpy", "conda"))

    def test_pip_package_classified_as_pip(self):
        conda_data = {"mypackage": {"version": "0.1.0", "source": "pip"}}
        pkg = VersionInfo(module="mypackage", qualname="func", version="0.1.0")
        with patch.object(validator, "_get_conda_packages", return_value=conda_data):
            result = validator.classify_package(pkg)
        self.assertEqual(result, ("mypackage", "pip"))

    def test_dotted_module_path_uses_top_level_for_lookup(self):
        conda_data = {"numpy": {"version": "1.26.0", "source": "conda"}}
        pkg = VersionInfo(module="numpy.linalg", qualname="norm", version="1.26.0")
        with patch.object(validator, "_get_conda_packages", return_value=conda_data):
            result = validator.classify_package(pkg)
        self.assertEqual(result, ("numpy", "conda"))

    def test_distribution_name_is_resolved_from_import_name(self):
        conda_data = {"scikit-learn": {"version": "1.5.0", "source": "conda"}}
        pkg = VersionInfo(module="sklearn", qualname="linear_model", version="1.5.0")
        with (
            patch.object(validator, "_get_conda_packages", return_value=conda_data),
            patch.object(
                validator,
                "_get_distribution_map",
                return_value={"sklearn": ["scikit-learn"]},
            ),
        ):
            result = validator.classify_package(pkg)
        self.assertEqual(result, ("scikit-learn", "conda"))

    def test_unknown_package_returns_unknown_and_warns(self):
        conda_data = {}
        pkg = VersionInfo(module="unknownpkg", qualname="func", version="9.9.9")
        with (
            patch.object(validator, "_get_conda_packages", return_value=conda_data),
            warnings.catch_warnings(record=True) as w,
        ):
            warnings.simplefilter("always")
            result = validator.classify_package(pkg)
        self.assertEqual(result, ("unknown", "unknown"))
        self.assertTrue(len(w) > 0)

    def test_version_mismatch_returns_unknown_and_warns(self):
        conda_data = {"numpy": {"version": "1.24.0", "source": "conda"}}
        pkg = VersionInfo(module="numpy", qualname="array", version="1.26.0")
        with (
            patch.object(validator, "_get_conda_packages", return_value=conda_data),
            warnings.catch_warnings(record=True) as w,
        ):
            warnings.simplefilter("always")
            result = validator.classify_package(pkg)
        self.assertEqual(result, ("unknown", "unknown"))
        self.assertTrue(len(w) > 0)


if __name__ == "__main__":
    unittest.main()
