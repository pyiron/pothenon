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
            "096075c762d143e6a6a865bc3b78d5603d767d0cbe081bcf0bf90c512211a887-e98c801afbc985d6b6995c806c5111c874ca033f21f2d31ef9ad742bad52baa4-",
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
        segments = identifier.split("-", 2)
        self.assertEqual(len(segments), 3)
        source_hash, dep_hash, version = segments
        self.assertEqual(len(source_hash), 64)
        self.assertEqual(len(dep_hash), 64)
        self.assertEqual(version, "")

    def test_identifier_segmented_format_versioned(self):
        pkg = dependency_parser.PackageInfo(
            localname="func",
            info=VersionInfo(module="mymodule", qualname="func", version="1.2.3"),
        )
        identifier = pkg.identifier
        segments = identifier.split("-", 2)
        self.assertEqual(len(segments), 3)
        source_hash, dep_hash, version = segments
        self.assertEqual(len(source_hash), 64)
        self.assertEqual(len(dep_hash), 64)
        self.assertEqual(version, "1.2.3")

    def test_identifier_segments_sensitivity(self):
        pkg1 = dependency_parser.PackageInfo(
            localname="func",
            info=VersionInfo(module="m", qualname="f", version="1.0.0"),
            source_code="def f(): return 1",
            dependency={},
        )
        s1, d1, v1 = pkg1.identifier.split("-", 2)

        # Change version -> only segment 3 changes
        pkg_diff_ver = dependency_parser.PackageInfo(
            localname="func",
            info=VersionInfo(module="m", qualname="f", version="1.0.1"),
            source_code="def f(): return 1",
            dependency={},
        )
        s2, d2, v2 = pkg_diff_ver.identifier.split("-", 2)
        self.assertEqual(s1, s2)
        self.assertEqual(d1, d2)
        self.assertNotEqual(v1, v2)
        self.assertEqual(v2, "1.0.1")

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
        s_orig, d_orig, v_orig = pkg_orig_src.identifier.split("-", 2)
        s_src, d_src, v_src = pkg_diff_src.identifier.split("-", 2)
        self.assertNotEqual(s_orig, s_src)

        # Add dependency -> segment 2 changes
        dep = _package("dep")
        pkg_diff_dep = dependency_parser.PackageInfo(
            localname="func",
            info=VersionInfo(module="m", qualname="f", version="1.0.0"),
            source_code="def f(): return 1",
            dependency={"dep": dep},
        )
        s3, d3, v3 = pkg_diff_dep.identifier.split("-", 2)
        self.assertEqual(s1, s3)
        self.assertNotEqual(d1, d3)
        self.assertEqual(v1, v3)


if __name__ == "__main__":
    unittest.main()
