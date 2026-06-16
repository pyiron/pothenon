import ast
import json
import textwrap
import unittest
from unittest.mock import patch

from pyiron_snippets import versions
from pyiron_snippets.versions import VersionInfo

from pothenon import dependency_parser


class TestSplitByVersionAvailability(unittest.TestCase):
    def test_split_by_version_availability(self):
        pkg_with_version = dependency_parser.PackageInfo(
            localname="a",
            info=VersionInfo(module="pkg_a", qualname="A", version="1.0.0"),
        )
        pkg_no_version = dependency_parser.PackageInfo(
            localname="b",
            info=VersionInfo(module="pkg_b", qualname="B", version=None),
        )

        call_dependencies = {
            "a": pkg_with_version,
            "b": pkg_no_version,
        }

        has_version, no_version = dependency_parser.split_by_version_availability(
            call_dependencies
        )

        self.assertIn("a", has_version)
        self.assertIn("b", no_version)
        self.assertNotIn("a", no_version)
        self.assertNotIn("b", has_version)


class TestUndefinedVariableVisitor(unittest.TestCase):
    def test_undefined_variable_visitor(self):
        source_code = """
        def test_function(a: int, b):
            c = a + b
            return d
        """
        tree = ast.parse(textwrap.dedent(source_code))
        visitor = dependency_parser.UndefinedVariableVisitor()
        visitor.visit(tree)

        self.assertIn("d", visitor.used_vars)
        self.assertIn("int", visitor.used_vars)
        self.assertIn("a", visitor.defined_vars)
        self.assertIn("b", visitor.defined_vars)
        self.assertIn("c", visitor.defined_vars)
        self.assertNotIn("d", visitor.defined_vars)

    def test_all_argument_kinds_are_defined(self):
        source_code = """
        def test_function(posonly, /, regular, *args, kw_only, **kwargs):
            return posonly + regular + kw_only
        """
        tree = ast.parse(textwrap.dedent(source_code))
        visitor = dependency_parser.UndefinedVariableVisitor()
        visitor.visit(tree)

        for name in ("posonly", "regular", "args", "kw_only", "kwargs"):
            self.assertIn(name, visitor.defined_vars)

    def test_local_function_definition_raises(self):
        source_code = """
        def outer(x):
            def helper(y):
                return y
            return helper(x)
        """
        tree = ast.parse(textwrap.dedent(source_code))
        visitor = dependency_parser.UndefinedVariableVisitor()
        with self.assertRaises(NotImplementedError):
            visitor.visit(tree)

    def test_local_async_function_definition_raises(self):
        source_code = """
        def outer(x):
            async def helper(y):
                return y
            return helper(x)
        """
        tree = ast.parse(textwrap.dedent(source_code))
        visitor = dependency_parser.UndefinedVariableVisitor()
        with self.assertRaises(NotImplementedError):
            visitor.visit(tree)

    def test_function_name_in_defined_vars(self):
        """The function name itself is added to defined_vars (supports recursive calls)."""
        source_code = """
        def my_func(x):
            return my_func(x - 1)
        """
        tree = ast.parse(textwrap.dedent(source_code))
        visitor = dependency_parser.UndefinedVariableVisitor()
        visitor.visit(tree)
        self.assertIn("my_func", visitor.defined_vars)

    def test_class_definition_tracked_in_defined_vars(self):
        """Class definitions are recorded so their names are not reported as undefined."""
        source_code = """
        class MyHelper:
            pass

        def use_class():
            return MyHelper()
        """
        tree = ast.parse(textwrap.dedent(source_code))
        visitor = dependency_parser.UndefinedVariableVisitor()
        visitor.visit(tree)
        self.assertIn("MyHelper", visitor.defined_vars)

    def test_import_inside_function_collected(self):
        """``import`` statements inside a function body are stored in ``.imports``."""
        source_code = """
        def func():
            import os
            return os.getcwd()
        """
        tree = ast.parse(textwrap.dedent(source_code))
        visitor = dependency_parser.UndefinedVariableVisitor()
        visitor.visit(tree)
        self.assertEqual(len(visitor.imports), 1)
        self.assertEqual(visitor.imports[0].names[0].name, "os")

    def test_import_from_inside_function_collected(self):
        """``from X import Y`` statements inside a function body are stored in ``.import_froms``."""
        source_code = """
        def func():
            from os import path
            return path.join("a", "b")
        """
        tree = ast.parse(textwrap.dedent(source_code))
        visitor = dependency_parser.UndefinedVariableVisitor()
        visitor.visit(tree)
        self.assertEqual(len(visitor.import_froms), 1)
        self.assertEqual(visitor.import_froms[0].module, "os")

    def test_top_level_async_function_does_not_raise(self):
        """An ``async def`` at the top level (nesting depth 0) is accepted without error."""
        source_code = """
        async def async_func(x):
            return x + 1
        """
        tree = ast.parse(textwrap.dedent(source_code))
        visitor = dependency_parser.UndefinedVariableVisitor()
        visitor.visit(tree)  # must not raise
        self.assertIn("async_func", visitor.defined_vars)
        self.assertIn("x", visitor.defined_vars)


x = 1


def test_function(a, b):
    c = a + b + x
    return c


class TestFindUndefinedVariables(unittest.TestCase):
    def test_find_undefined_variables(self):
        undefined_vars = dependency_parser.find_undefined_variables(test_function)
        self.assertIn("x", undefined_vars)
        self.assertNotIn("a", undefined_vars)
        self.assertNotIn("b", undefined_vars)
        self.assertNotIn("c", undefined_vars)

    def test_builtin_names_not_reported_as_undefined(self):
        """Built-in names such as ``len`` and ``int`` must not appear in the result."""

        def use_builtins(items):
            return len(items) + int(items[0])

        undefined = dependency_parser.find_undefined_variables(use_builtins)
        for name in ("len", "int"):
            self.assertNotIn(name, undefined)

    def test_builtin_callable_returns_empty_dict(self):
        """Built-in callables like ``len`` have no retrievable source; result must be ``{}``."""
        result = dependency_parser.find_undefined_variables(len)
        self.assertIsInstance(result, dict)
        self.assertEqual(result, {})

    def test_function_arguments_not_in_undefined(self):
        """All argument kinds must not appear in the result as undefined."""

        def parametrised(a, b=0, *args, kw=None, **kwargs):
            return a + b + kw

        undefined = dependency_parser.find_undefined_variables(parametrised)
        for name in ("a", "b", "args", "kw", "kwargs"):
            self.assertNotIn(name, undefined)

    def test_syntax_error_in_source_returns_empty_dict(self):
        """When ``ast.parse`` raises ``SyntaxError``, the result must be ``{}``."""
        with patch("pothenon.dependency_parser.ast.parse", side_effect=SyntaxError):
            result = dependency_parser.find_undefined_variables(test_function)
        self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# Module-level helpers used by TestGetCallDependencies
# ---------------------------------------------------------------------------


def _func_no_external(x, y):
    """Function with no external dependencies (only uses its arguments)."""
    return x + y


def _helper_func(z):
    """A plain helper; will be used as a mock dependency."""
    return z * 2


def _func_with_versioned_dependency():
    """Function that uses a real imported dependency with package metadata."""
    return VersionInfo


class _UnversionedClass:
    """A locally-defined class that has no package version."""

    pass


def _func_with_unversioned_class():
    """Function whose only dependency is a locally-defined class (no version)."""
    return _UnversionedClass()


def _func_using_json():
    """Helper function that uses json from stdlib."""
    return json.dumps({"key": "value"})


def _func_calling_helper_with_external_dep():
    """Function that calls another function which depends on an external package."""
    return _func_using_json()


class TestGetCallDependencies(unittest.TestCase):
    def test_no_external_dependencies(self):
        """A function that only uses its own arguments returns an empty dict."""
        result = dependency_parser.get_call_dependencies(_func_no_external)
        self.assertIsInstance(result, dict)
        self.assertEqual(result, {})

    def test_cycle_detection_via_visited(self):
        """If the function's FQN is already in ``_visited``, it returns immediately."""
        fqn = versions.VersionInfo.of(_func_no_external).fully_qualified_name
        pre_visited: set[str] = {fqn}
        result = dependency_parser.get_call_dependencies(
            _func_no_external, _visited=pre_visited
        )
        self.assertIsInstance(result, dict)
        self.assertEqual(result, {})

    def test_unversioned_callable_dependency_is_recursed(self):
        """An unversioned callable dependency triggers a recursive call."""
        call_log: list[object] = []

        original_find = dependency_parser.find_undefined_variables

        def tracking_find(func):
            call_log.append(func)
            if func is _func_no_external:
                return {"helper": _helper_func}
            return original_find(func)

        with patch.object(
            dependency_parser, "find_undefined_variables", side_effect=tracking_find
        ):
            dependency_parser.get_call_dependencies(_func_no_external)

        # find_undefined_variables must have been called for both the original
        # function and the unversioned callable helper.
        self.assertIn(_func_no_external, call_log)
        self.assertIn(_helper_func, call_log)

    def test_non_callable_unversioned_dependency_not_recursed(self):
        """A non-callable, unversioned dependency is recorded but NOT recursed into."""
        call_log: list[object] = []
        non_callable_dep = 42  # plain integer, not callable

        original_find = dependency_parser.find_undefined_variables

        def tracking_find(func):
            call_log.append(func)
            if func is _func_no_external:
                return {"magic_number": non_callable_dep}
            return original_find(func)

        with patch.object(
            dependency_parser, "find_undefined_variables", side_effect=tracking_find
        ):
            result = dependency_parser.get_call_dependencies(_func_no_external)

        # The integer must be recorded in the result (a key must exist).
        self.assertTrue(len(result) > 0)
        # find_undefined_variables must NOT have been called for the integer.
        self.assertNotIn(non_callable_dep, call_log)

    def test_records_package_info_metadata_for_real_dependency(self):
        result = dependency_parser.get_call_dependencies(
            _func_with_versioned_dependency
        )

        dependency = result["VersionInfo"]
        self.assertEqual(dependency.localname, "VersionInfo")
        self.assertEqual(dependency.info.qualname, "VersionInfo")
        self.assertIsNotNone(dependency.info.version)

    def test_versioned_class_dependency_does_not_raise(self):
        """A class dependency that has a version must not raise."""
        result = dependency_parser.get_call_dependencies(
            _func_with_versioned_dependency
        )
        self.assertIn("VersionInfo", result)

    def test_unversioned_class_dependency_raises_type_error(self):
        """A class dependency without a version must raise TypeError."""
        with self.assertRaises(TypeError):
            dependency_parser.get_call_dependencies(_func_with_unversioned_class)

    def test_recursive_dependency_detection(self):
        """When f calls g and g uses an external package, get_call_dependencies(f) should detect the package.

        This test verifies that dependency detection is recursive: if function f depends on
        unversioned callable g, and g depends on a versioned external package (e.g., json.dumps),
        then calling get_call_dependencies(f) should include json in the results.
        """
        result = dependency_parser.get_call_dependencies(
            _func_calling_helper_with_external_dep
        )

        # The result should contain json.dumps from the stdlib (via the helper)
        self.assertTrue(
            any("json" in key for key in result),
            f"Expected json dependency in result keys: {list(result.keys())}",
        )


if __name__ == "__main__":
    unittest.main()
