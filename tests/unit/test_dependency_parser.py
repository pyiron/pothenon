import ast
import json
import json as json_alias
import textwrap
import unittest
from unittest.mock import patch

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


class TestImportStatements(unittest.TestCase):
    def test_to_import_statement_with_qualname(self):
        info = VersionInfo(module="package.module", qualname="Thing", version="1.2.3")

        self.assertEqual(
            dependency_parser._to_import_statement(info, "Thing"),
            "from package.module import Thing",
        )
        self.assertEqual(
            dependency_parser._to_import_statement(info, "Alias"),
            "from package.module import Thing as Alias",
        )

    def test_to_import_statement_without_qualname(self):
        dotted = VersionInfo(module="package.module", qualname=None, version="1.2.3")
        top_level = VersionInfo(module="json", qualname=None, version="1.2.3")
        deep_dotted = VersionInfo(
            module="mod.submod.subsubmod", qualname=None, version="1.2.3"
        )

        self.assertEqual(
            dependency_parser._to_import_statement(dotted, "module_alias"),
            "from package import module as module_alias",
        )
        self.assertEqual(
            dependency_parser._to_import_statement(top_level, "json_alias"),
            "import json as json_alias",
        )
        self.assertEqual(
            dependency_parser._to_import_statement(deep_dotted, "subsubmod"),
            "from mod.submod import subsubmod",
        )
        self.assertEqual(
            dependency_parser._to_import_statement(deep_dotted, "subsubmod_alias"),
            "from mod.submod import subsubmod as subsubmod_alias",
        )

    def test_to_import_statement_with_dotted_qualname(self):
        info = VersionInfo(module="mod", qualname="Scope.Target", version="1.2.3")

        self.assertEqual(
            dependency_parser._to_import_statement(info, "Target"),
            "from mod.Scope import Target",
        )
        self.assertEqual(
            dependency_parser._to_import_statement(info, "TargetAlias"),
            "from mod.Scope import Target as TargetAlias",
        )

    def test_package_info_import_statement_property(self):
        versioned = dependency_parser.PackageInfo(
            localname="VersionInfo",
            info=VersionInfo(
                module="pyiron_snippets.versions",
                qualname="VersionInfo",
                version="1.2.3",
            ),
        )
        unversioned = dependency_parser.PackageInfo(
            localname="VersionInfo",
            info=VersionInfo(
                module="pyiron_snippets.versions", qualname="VersionInfo", version=None
            ),
        )

        self.assertEqual(
            versioned.import_statement,
            "from pyiron_snippets.versions import VersionInfo",
        )
        self.assertEqual(unversioned.import_statement, "")

    def test_package_info_export_includes_dependencies_and_source(self):
        dependency = dependency_parser.PackageInfo(
            localname="helper",
            info=VersionInfo(module="pkg", qualname="helper", version="1.0.0"),
        )
        package = dependency_parser.PackageInfo(
            localname="root",
            info=VersionInfo(module="local", qualname="root", version=None),
            source_code="def root():\n    return helper()\n",
            dependency={"helper": dependency},
        )

        self.assertEqual(
            package.export(),
            "from pkg import helper\n\n" "def root():\n    return helper()\n",
        )

    def test_package_info_str_matches_export(self):
        package = dependency_parser.PackageInfo(
            localname="x",
            info=VersionInfo(module="local", qualname="x", version=None),
            source_code="x = 1\n",
        )
        self.assertEqual(str(package), package.export())


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
        with patch(
            "pothenon.annotation_literalizer.ast.parse", side_effect=SyntaxError
        ):
            result = dependency_parser.find_undefined_variables(test_function)
        self.assertEqual(result, {})


class TestResolveOrImport(unittest.TestCase):
    def test_uses_scope_resolution_when_available(self):
        scope = object()
        resolved = object()

        with (
            patch.object(
                dependency_parser.object_scope,
                "resolve_attribute_to_object",
                return_value=resolved,
            ) as resolve_attribute_to_object,
            patch.object(dependency_parser.importlib, "import_module") as import_module,
        ):
            result = dependency_parser._resolve_or_import("json", scope)

        resolve_attribute_to_object.assert_called_once_with("json", scope)
        import_module.assert_not_called()
        self.assertIs(result, resolved)

    def test_imports_top_level_module_when_scope_resolution_fails(self):
        scope = object()

        with (
            patch.object(
                dependency_parser.object_scope,
                "resolve_attribute_to_object",
                side_effect=ValueError("not in scope"),
            ) as resolve_attribute_to_object,
            patch.object(
                dependency_parser.importlib, "import_module", return_value=json
            ) as import_module,
        ):
            result = dependency_parser._resolve_or_import("json", scope)

        resolve_attribute_to_object.assert_called_once_with("json", scope)
        import_module.assert_called_once_with("json")
        self.assertIs(result, json)

    def test_raises_value_error_when_scope_and_import_both_fail(self):
        scope = object()

        with (
            patch.object(
                dependency_parser.object_scope,
                "resolve_attribute_to_object",
                side_effect=ValueError("not in scope"),
            ) as resolve_attribute_to_object,
            patch.object(
                dependency_parser.importlib,
                "import_module",
                side_effect=ImportError("cannot import"),
            ) as import_module,
            self.assertRaisesRegex(
                ValueError,
                "Cannot resolve 'does_not_exist' in the current scope and failed to "
                "import it as a top-level module or package.",
            ),
        ):
            dependency_parser._resolve_or_import("does_not_exist", scope)

        resolve_attribute_to_object.assert_called_once_with("does_not_exist", scope)
        import_module.assert_called_once_with("does_not_exist")


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
    key_value = {"key": "value"}
    return json.dumps(key_value)


def _func_calling_helper_with_external_dep():
    """Function that calls another function which depends on an external package."""
    return _func_using_json()


def _func_with_duplicate_fqn_different_localnames():
    """Function that uses the same package under different local names.

    This tests that local names (not fully qualified names) are used as keys,
    preventing collisions when the same package is imported with different aliases.
    """
    return json.dumps({}) + json_alias.dumps({})


class SomeGlobalClass:
    pass

some_global_class = SomeGlobalClass()
some_global_class.some_attr = 42

def _func_with_forbidden_global_class():
    """Function that uses a global class defined in the module.

    This tests that global classes defined in the module are not allowed as dependencies.
    """
    return some_global_class.some_attr + 1

some_global_variable = 42

def _func_with_forbidden_global_variable():
    """Function that uses a global variable defined in the module.

    This tests that global variables defined in the module are not allowed as dependencies.
    """
    return some_global_variable + 1


class TestGetCallDependencies(unittest.TestCase):
    def test_no_external_dependencies(self):
        """A function that only uses its own arguments returns an empty dict."""
        result = dependency_parser.get_call_dependencies(_func_no_external)
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

    def test_same_fqn_different_localnames_no_collision(self):
        """When the same package is imported with different local names, both should be in the result.

        This verifies the fix: using local names as keys (not fully qualified names)
        prevents collisions when the same package is imported with different aliases
        (e.g., `import numpy` and `import numpy as np`).
        """
        result = dependency_parser.get_call_dependencies(
            _func_with_duplicate_fqn_different_localnames
        )

        # Both local names should be present (not overwritten)
        self.assertIn("json", result)
        self.assertIn("json_alias", result)
        self.assertEqual(len(result), 2)

        # Both should have the same fully qualified name (json)
        self.assertEqual(result["json"].info.module, "json")
        self.assertEqual(result["json_alias"].info.module, "json")

    def test_forbidden_global_class_raises_error(self):
        """Using a global class defined in the module should raise a ValueError."""
        with self.assertRaises(ValueError) as context:
            dependency_parser.get_call_dependencies(_func_with_forbidden_global_class)

        self.assertIn(
            "'some_global_class' is not a class or callable without a version",
            str(context.exception),
        )

    def test_forbidden_global_variable_raises_error(self):
        """Using a global variable defined in the module should raise a ValueError."""
        with self.assertRaises(ValueError) as context:
            dependency_parser.get_call_dependencies(_func_with_forbidden_global_variable)

        self.assertIn(
            "'some_global_variable' is not a callable or module with a version",
            str(context.exception),
        )


class TestGetFullSource(unittest.TestCase):
    def test_get_full_source_collects_source_and_dependencies(self):
        expected_info = VersionInfo(module="module", qualname="func", version="1.2.3")
        expected_dependencies = {
            "dep": dependency_parser.PackageInfo(
                localname="dep",
                info=VersionInfo(module="dep_mod", qualname="dep", version="0.1.0"),
            )
        }
        expected_source = "def _func_no_external(x, y):\n    return x + y"

        with (
            patch.object(
                dependency_parser.versions.VersionInfo, "of", return_value=expected_info
            ) as version_of,
            patch.object(
                dependency_parser.annotation_literalizer,
                "transform",
                return_value=expected_source,
            ) as transform,
            patch.object(
                dependency_parser,
                "get_call_dependencies",
                return_value=expected_dependencies,
            ) as get_call_dependencies,
        ):
            result = dependency_parser.get_full_source(_func_no_external)

        version_of.assert_called_once_with(_func_no_external)
        transform.assert_called_once_with(_func_no_external)
        get_call_dependencies.assert_called_once_with(_func_no_external)
        self.assertEqual(
            result,
            dependency_parser.PackageInfo(
                localname="_func_no_external",
                info=expected_info,
                source_code=expected_source,
                dependency=expected_dependencies,
            ),
        )


if __name__ == "__main__":
    unittest.main()
