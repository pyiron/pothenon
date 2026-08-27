import unittest
import warnings
from unittest.mock import MagicMock, patch

from pyiron_snippets.versions import VersionInfo

from pothenon import package_resolver


def _make_dist(name, version, installer=None):
    """Create a mock distribution object mimicking importlib.metadata.Distribution."""
    meta = {"Name": name, "Version": version}
    if installer is not None:
        meta["Installer"] = installer

    dist = MagicMock()
    dist.metadata = meta
    return dist


def _make_conda_record(name, version, channel="defaults"):
    """Create a mock conda PackageRecord."""
    record = MagicMock()
    record.name = name
    record.version = version
    record.channel = channel
    return record


class TestGetCondaPackagesWithCondaAPI(unittest.TestCase):
    """Tests for _get_conda_packages when the conda Python API is available."""

    def setUp(self):
        package_resolver._get_conda_packages.cache_clear()

    def tearDown(self):
        package_resolver._get_conda_packages.cache_clear()

    def _patch_conda(self, records):
        mock_prefix_data = MagicMock()
        mock_prefix_data.iter_records.return_value = records
        mock_prefix_data_cls = MagicMock(return_value=mock_prefix_data)
        mock_context = MagicMock()
        mock_context.active_prefix = "/opt/conda"
        return (
            patch.dict(
                "sys.modules",
                {
                    "conda": MagicMock(),
                    "conda.base": MagicMock(),
                    "conda.base.context": MagicMock(context=mock_context),
                    "conda.core": MagicMock(),
                    "conda.core.prefix_data": MagicMock(
                        PrefixData=mock_prefix_data_cls
                    ),
                },
            ),
        )

    def test_conda_api_returns_conda_packages(self):
        records = [
            _make_conda_record("numpy", "1.26.0", channel="defaults"),
            _make_conda_record("scipy", "1.11.0", channel="defaults"),
        ]
        mock_prefix_data = MagicMock()
        mock_prefix_data.iter_records.return_value = records
        mock_prefix_data_cls = MagicMock(return_value=mock_prefix_data)
        mock_context = MagicMock()
        mock_context.active_prefix = "/opt/conda"
        mock_conda_context_mod = MagicMock()
        mock_conda_context_mod.context = mock_context
        mock_conda_prefix_mod = MagicMock()
        mock_conda_prefix_mod.PrefixData = mock_prefix_data_cls

        with patch.dict(
            "sys.modules",
            {
                "conda": MagicMock(),
                "conda.base": MagicMock(),
                "conda.base.context": mock_conda_context_mod,
                "conda.core": MagicMock(),
                "conda.core.prefix_data": mock_conda_prefix_mod,
            },
        ):
            package_resolver._get_conda_packages.cache_clear()
            result = package_resolver._get_conda_packages()

        self.assertIn("numpy", result)
        self.assertEqual(result["numpy"]["version"], "1.26.0")
        self.assertEqual(result["numpy"]["source"], "conda")

    def test_conda_api_pypi_channel_mapped_to_pip(self):
        records = [_make_conda_record("mypackage", "0.1.0", channel="pypi")]
        mock_prefix_data = MagicMock()
        mock_prefix_data.iter_records.return_value = records
        mock_prefix_data_cls = MagicMock(return_value=mock_prefix_data)
        mock_context = MagicMock()
        mock_context.active_prefix = "/opt/conda"
        mock_conda_context_mod = MagicMock()
        mock_conda_context_mod.context = mock_context
        mock_conda_prefix_mod = MagicMock()
        mock_conda_prefix_mod.PrefixData = mock_prefix_data_cls

        with patch.dict(
            "sys.modules",
            {
                "conda": MagicMock(),
                "conda.base": MagicMock(),
                "conda.base.context": mock_conda_context_mod,
                "conda.core": MagicMock(),
                "conda.core.prefix_data": mock_conda_prefix_mod,
            },
        ):
            package_resolver._get_conda_packages.cache_clear()
            result = package_resolver._get_conda_packages()

        self.assertEqual(result["mypackage"]["source"], "pip")


class TestGetCondaPackagesFallback(unittest.TestCase):
    """Tests for _get_conda_packages fallback when conda is not available."""

    def setUp(self):
        package_resolver._get_conda_packages.cache_clear()

    def tearDown(self):
        package_resolver._get_conda_packages.cache_clear()

    def test_falls_back_to_importlib_when_conda_unavailable(self):
        mock_dists = [
            _make_dist("numpy", "1.26.0", installer="conda"),
            _make_dist("scipy", "1.11.0", installer="conda"),
        ]
        with (
            patch.dict("sys.modules", {"conda": None}),
            patch("pothenon.package_resolver.distributions", return_value=mock_dists),
        ):
            result = package_resolver._get_conda_packages()
        self.assertIn("numpy", result)
        self.assertEqual(result["numpy"]["version"], "1.26.0")
        self.assertEqual(result["numpy"]["source"], "conda")

    def test_fallback_pip_installer_mapped_to_pip_source(self):
        mock_dists = [_make_dist("mypackage", "0.1.0", installer="pip")]
        with (
            patch.dict("sys.modules", {"conda": None}),
            patch("pothenon.package_resolver.distributions", return_value=mock_dists),
        ):
            result = package_resolver._get_conda_packages()
        self.assertEqual(result["mypackage"]["source"], "pip")

    def test_fallback_no_installer_defaults_to_conda(self):
        mock_dists = [_make_dist("somepackage", "2.0.0")]
        with (
            patch.dict("sys.modules", {"conda": None}),
            patch("pothenon.package_resolver.distributions", return_value=mock_dists),
        ):
            result = package_resolver._get_conda_packages()
        self.assertEqual(result["somepackage"]["source"], "conda")

    def test_fallback_packages_missing_name_or_version_skipped(self):
        meta_no_name = {"Name": None, "Version": "1.0.0"}
        dist_no_name = MagicMock()
        dist_no_name.metadata = meta_no_name
        meta_no_ver = {"Name": "broken"}
        dist_no_ver = MagicMock()
        dist_no_ver.metadata = meta_no_ver
        mock_dists = [
            _make_dist("numpy", "1.26.0", installer="conda"),
            dist_no_name,
            dist_no_ver,
        ]
        with (
            patch.dict("sys.modules", {"conda": None}),
            patch("pothenon.package_resolver.distributions", return_value=mock_dists),
        ):
            result = package_resolver._get_conda_packages()
        self.assertIn("numpy", result)
        self.assertNotIn("broken", result)


class TestClassifyPackage(unittest.TestCase):
    def test_stdlib_module_classified_as_stdlib(self):
        pkg = VersionInfo(module="os", qualname="path", version=None)
        result = package_resolver.classify_package(pkg)
        self.assertEqual(result, ("os", "stdlib"))

    def test_dotted_stdlib_module_classified_as_stdlib(self):
        pkg = VersionInfo(module="os.path", qualname="join", version=None)
        result = package_resolver.classify_package(pkg)
        self.assertEqual(result, ("os", "stdlib"))

    def test_conda_package_classified_as_conda(self):
        conda_data = {"numpy": {"version": "1.26.0", "source": "conda"}}
        pkg = VersionInfo(module="numpy", qualname="array", version="1.26.0")
        with patch.object(
            package_resolver, "_get_conda_packages", return_value=conda_data
        ):
            result = package_resolver.classify_package(pkg)
        self.assertEqual(result, ("numpy", "conda"))

    def test_pip_package_classified_as_pip(self):
        conda_data = {"mypackage": {"version": "0.1.0", "source": "pip"}}
        pkg = VersionInfo(module="mypackage", qualname="func", version="0.1.0")
        with patch.object(
            package_resolver, "_get_conda_packages", return_value=conda_data
        ):
            result = package_resolver.classify_package(pkg)
        self.assertEqual(result, ("mypackage", "pip"))

    def test_dotted_module_path_uses_top_level_for_lookup(self):
        conda_data = {"numpy": {"version": "1.26.0", "source": "conda"}}
        pkg = VersionInfo(module="numpy.linalg", qualname="norm", version="1.26.0")
        with patch.object(
            package_resolver, "_get_conda_packages", return_value=conda_data
        ):
            result = package_resolver.classify_package(pkg)
        self.assertEqual(result, ("numpy", "conda"))

    def test_distribution_name_is_resolved_from_import_name(self):
        conda_data = {"scikit-learn": {"version": "1.5.0", "source": "conda"}}
        pkg = VersionInfo(module="sklearn", qualname="linear_model", version="1.5.0")
        with (
            patch.object(
                package_resolver, "_get_conda_packages", return_value=conda_data
            ),
            patch.object(
                package_resolver,
                "_get_distribution_map",
                return_value={"sklearn": ["scikit-learn"]},
            ),
        ):
            result = package_resolver.classify_package(pkg)
        self.assertEqual(result, ("scikit-learn", "conda"))

    def test_unknown_package_returns_unknown_and_warns(self):
        conda_data = {}
        pkg = VersionInfo(module="unknownpkg", qualname="func", version="9.9.9")
        with (
            patch.object(
                package_resolver, "_get_conda_packages", return_value=conda_data
            ),
            warnings.catch_warnings(record=True) as w,
        ):
            warnings.simplefilter("always")
            result = package_resolver.classify_package(pkg)
        self.assertEqual(result, ("unknown", "unknown"))
        self.assertTrue(len(w) > 0)

    def test_version_mismatch_returns_unknown_and_warns(self):
        conda_data = {"numpy": {"version": "1.24.0", "source": "conda"}}
        pkg = VersionInfo(module="numpy", qualname="array", version="1.26.0")
        with (
            patch.object(
                package_resolver, "_get_conda_packages", return_value=conda_data
            ),
            warnings.catch_warnings(record=True) as w,
        ):
            warnings.simplefilter("always")
            result = package_resolver.classify_package(pkg)
        self.assertEqual(result, ("unknown", "unknown"))
        self.assertTrue(len(w) > 0)


class TestGetCondaEnvironment(unittest.TestCase):
    def _package(self, module, version):
        return VersionInfo(module=module, qualname="item", version=version)

    def test_renders_conda_and_pip_dependencies_with_name(self):
        packages = [
            self._package("requests", "2.32.0"),
            self._package("numpy", "1.26.0"),
        ]
        classifications = {
            "requests": ("requests", "pip"),
            "numpy": ("numpy", "conda"),
        }

        with patch.object(
            package_resolver,
            "classify_package",
            side_effect=lambda package: classifications[package.module],
        ):
            result = package_resolver.get_conda_environment(packages, name="test-env")

        self.assertEqual(
            result,
            "\n".join(
                [
                    "name: test-env",
                    "dependencies:",
                    "  - numpy=1.26.0",
                    "  - pip",
                    "  - pip:",
                    "      - requests==2.32.0",
                ]
            ),
        )

    def test_omits_stdlib_and_unknown_packages_with_warning(self):
        packages = [
            self._package("os", None),
            self._package("unknown", "9.9.9"),
        ]

        with (
            patch.object(
                package_resolver,
                "classify_package",
                side_effect=[
                    ("os", "stdlib"),
                    ("unknown", "unknown"),
                ],
            ),
            warnings.catch_warnings(record=True) as caught_warnings,
        ):
            warnings.simplefilter("always")
            result = package_resolver.get_conda_environment(packages)

        self.assertEqual(result, "dependencies:")
        self.assertEqual(len(caught_warnings), 1)
        self.assertIn(
            "Skipping unknown package unknown==9.9.9", str(caught_warnings[0].message)
        )

    def test_sorts_and_deduplicates_dependencies(self):
        packages = [
            self._package("zpackage", "1.0.0"),
            self._package("apackage", "2.0.0"),
            self._package("zpackage", "1.0.0"),
        ]

        with patch.object(
            package_resolver,
            "classify_package",
            side_effect=[
                ("zpackage", "conda"),
                ("apackage", "conda"),
                ("zpackage", "conda"),
            ],
        ):
            result = package_resolver.get_conda_environment(packages)

        self.assertEqual(
            result,
            "\n".join(
                [
                    "dependencies:",
                    "  - apackage=2.0.0",
                    "  - zpackage=1.0.0",
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
