import unittest

from pyiron_snippets.versions import VersionInfo

from pothenon import dependency_parser, hashing


def _package(name: str) -> dependency_parser.PackageInfo:
    return dependency_parser.PackageInfo(
        localname=name,
        info=VersionInfo(module="recursive", qualname=name, version=None),
        source_code=f"def {name}():\n    pass\n",
        dependency={},
    )


class TestHashPackageInfo(unittest.TestCase):
    def test_self_recursive_dependency_has_a_stable_identifier(self):
        function = _package("function")
        function.dependency["function"] = function

        identifier = hashing.hash_package_info(function)

        self.assertEqual(identifier, hashing.hash_package_info(function))
        self.assertEqual(
            identifier,
            "096075c762d143e6-e98c801afbc985d6",
        )
        self.assertIsInstance(identifier, str)

    def test_mutually_recursive_dependencies_are_supported(self):
        first = _package("first")
        second = _package("second")
        first.dependency["second"] = second
        second.dependency["first"] = first

        first_identifier = hashing.hash_package_info(first)
        second_identifier = hashing.hash_package_info(second)

        self.assertEqual(first_identifier, hashing.hash_package_info(first))
        self.assertEqual(second_identifier, hashing.hash_package_info(second))
        self.assertNotEqual(first_identifier, second_identifier)

    def test_identifier_segmented_format_unversioned(self):
        pkg = _package("func")
        identifier = pkg.identifier
        segments = identifier.split("-")
        self.assertEqual(len(segments), 2)
        versionless_hash, full_hash = segments
        self.assertEqual(len(versionless_hash), 16)
        self.assertEqual(len(full_hash), 16)
        self.assertNotEqual(versionless_hash, full_hash)

    def test_identifier_segmented_format_versioned(self):
        pkg = dependency_parser.PackageInfo(
            localname="func",
            info=VersionInfo(module="mymodule", qualname="func", version="1.2.3"),
        )
        identifier = pkg.identifier
        segments = identifier.split("-")
        self.assertEqual(len(segments), 2)
        versionless_hash, full_hash = segments
        self.assertEqual(len(versionless_hash), 16)
        self.assertEqual(len(full_hash), 16)
        self.assertNotEqual(versionless_hash, full_hash)

    def test_identifier_segments_sensitivity(self):
        pkg1 = dependency_parser.PackageInfo(
            localname="func",
            info=VersionInfo(module="m", qualname="f", version="1.0.0"),
            source_code="def f(): return 1",
            dependency={},
        )
        versionless1, full1 = pkg1.identifier.split("-")

        # Change version -> only the full hash changes.
        pkg_diff_ver = dependency_parser.PackageInfo(
            localname="func",
            info=VersionInfo(module="m", qualname="f", version="1.0.1"),
            source_code="def f(): return 1",
            dependency={},
        )
        versionless2, full2 = pkg_diff_ver.identifier.split("-")
        self.assertEqual(versionless1, versionless2)
        self.assertNotEqual(full1, full2)

        # Change source code -> segment 1 changes
        pkg_diff_src = dependency_parser.PackageInfo(
            localname="func",
            info=VersionInfo(module="recursive", qualname="f", version=None),
            source_code="def f(): return 2",
            dependency={},
        )
        pkg_orig_src = dependency_parser.PackageInfo(
            localname="func",
            info=VersionInfo(module="recursive", qualname="f", version=None),
            source_code="def f(): return 1",
            dependency={},
        )
        versionless_orig, full_orig = pkg_orig_src.identifier.split("-")
        versionless_src, full_src = pkg_diff_src.identifier.split("-")
        self.assertNotEqual(versionless_orig, versionless_src)
        self.assertNotEqual(full_orig, full_src)

        # Add dependency -> segment 2 changes
        dep = _package("dep")
        pkg_diff_dep = dependency_parser.PackageInfo(
            localname="func",
            info=VersionInfo(module="m", qualname="f", version="1.0.0"),
            source_code="def f(): return 1",
            dependency={"dep": dep},
        )
        versionless3, full3 = pkg_diff_dep.identifier.split("-")
        self.assertEqual(versionless1, versionless3)
        self.assertNotEqual(full1, full3)

    def test_dependency_version_only_changes_the_full_hash(self):
        dependency = dependency_parser.PackageInfo(
            localname="dep",
            info=VersionInfo(module="dependency", qualname="dep", version="1.0.0"),
        )
        pkg = dependency_parser.PackageInfo(
            localname="func",
            info=VersionInfo(module="m", qualname="f", version="1.0.0"),
            dependency={"dep": dependency},
        )
        changed_dependency = dependency._replace(
            info=VersionInfo(module="dependency", qualname="dep", version="1.0.1")
        )
        changed_pkg = pkg._replace(dependency={"dep": changed_dependency})

        versionless, full = pkg.identifier.split("-")
        changed_versionless, changed_full = changed_pkg.identifier.split("-")

        self.assertEqual(versionless, changed_versionless)
        self.assertNotEqual(full, changed_full)


if __name__ == "__main__":
    unittest.main()
