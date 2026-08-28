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


if __name__ == "__main__":
    unittest.main()
