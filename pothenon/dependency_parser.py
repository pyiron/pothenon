from __future__ import annotations

import ast
import builtins
import importlib
import inspect
import textwrap
import types
import typing
from collections.abc import Callable
from typing import Any

from pyiron_snippets import versions

from pothenon import annotation_literalizer, object_scope


def _to_import_statement(info: versions.VersionInfo, localname: str) -> str:
    # module: A.B, qualname: C, localname: C -> "from A.B import C"
    # module: A.B, qualname: C, localname: D -> "from A.B import C as D"
    # module: A.B, qualname: None, localname: C -> "from A import B as C"
    # module: A, qualname: B, localname: B -> "from A import B"
    # module: A, qualname: B, localname: C -> "from A import B as C"
    # module: A, qualname: None, localname: A -> "import A"
    # module: A, qualname: None, localname: B -> "import A as B"
    if info.qualname is None:
        if "." in info.module:
            pkg, mod = info.module.rsplit(".", 1)
            if mod == localname:
                return f"from {pkg} import {mod}"
            return f"from {pkg} import {mod} as {localname}"

        if info.module == localname:
            return f"import {info.module}"
        return f"import {info.module} as {localname}"

    if "." in info.qualname:
        qualname_parent, qualname_name = info.qualname.rsplit(".", 1)
        from_module = f"{info.module}.{qualname_parent}"
        if qualname_name == localname:
            return f"from {from_module} import {qualname_name}"
        return f"from {from_module} import {qualname_name} as {localname}"

    if info.qualname == localname:
        return f"from {info.module} import {info.qualname}"
    return f"from {info.module} import {info.qualname} as {localname}"


class PackageInfo(typing.NamedTuple):
    localname: str
    info: versions.VersionInfo
    source_code: str | None = None
    dependency: dict[str, PackageInfo] | None = None

    @property
    def import_statement(self) -> str:
        return (
            _to_import_statement(self.info, self.localname)
            if self.info.version is not None
            else ""
        )

    def export(self, _seen: set[int] | None = None) -> str:
        seen = set() if _seen is None else _seen
        if id(self) in seen:
            return ""
        seen.add(id(self))

        chunks: list[str] = []
        if self.dependency:
            for name in sorted(self.dependency):
                dep_text = self.dependency[name].export(seen)
                if dep_text:
                    chunks.append(dep_text)

        if self.import_statement:
            chunks.append(self.import_statement)
        if self.source_code:
            chunks.append(self.source_code)

        return "\n\n".join(chunks)

    def __str__(self) -> str:
        return self.export()


CallDependencies = dict[str, PackageInfo]


def split_by_version_availability(
    call_dependencies: CallDependencies,
) -> tuple[CallDependencies, CallDependencies]:
    """
    Partition *call_dependencies* by whether a version string is available.

    Args:
        call_dependencies: The dependency map to partition.

    Returns:
        A ``(has_version, no_version)`` tuple of :data:`CallDependencies` dicts.
    """
    has_version: CallDependencies = {}
    no_version: CallDependencies = {}
    for info, dependency in call_dependencies.items():
        if dependency.info.version is None:
            no_version[info] = dependency
        else:
            has_version[info] = dependency

    return has_version, no_version


class UndefinedVariableVisitor(ast.NodeVisitor):
    """AST visitor that collects used and locally-defined variable names.

    Local (nested) function definitions inside the analysed function body are
    **not** supported: encountering one raises :exc:`NotImplementedError` so
    that callers fail fast with a clear message instead of silently producing
    wrong dependency results.

    Class definitions at any nesting level are tracked in :attr:`defined_vars`
    so that class names used later in the same scope are not reported as
    undefined symbols.
    """

    def __init__(self):
        self.used_vars: set[str] = set()
        self.defined_vars: set[str] = set()
        self._nesting_depth: int = 0
        self.imports: list[ast.Import] = []
        self.import_froms: list[ast.ImportFrom] = []

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.used_vars.add(node.id)
        elif isinstance(node.ctx, ast.Store):
            self.defined_vars.add(node.id)

    def _visit_function_def(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if self._nesting_depth > 0:
            keyword = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            raise NotImplementedError(
                f"Local function definitions are not supported: "
                f"'{keyword} {node.name}' inside a function body cannot be "
                "analysed for dependencies."
            )
        # Register the function name and all of its parameters so that
        # recursive calls and uses of any argument inside the body are not
        # reported as undefined external symbols.
        self.defined_vars.add(node.name)
        all_args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
        for arg in all_args:
            self.defined_vars.add(arg.arg)
        if node.args.vararg:
            self.defined_vars.add(node.args.vararg.arg)
        if node.args.kwarg:
            self.defined_vars.add(node.args.kwarg.arg)
        self._nesting_depth += 1
        self.generic_visit(node)
        self._nesting_depth -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function_def(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function_def(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.defined_vars.add(node.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.import_froms.append(node)

    def visit_Import(self, node: ast.Import) -> None:
        self.imports.append(node)


def _resolve_or_import(name: str, scope: object_scope.Scope) -> object:
    try:
        return object_scope.resolve_attribute_to_object(name, scope)
    except ValueError:
        # If the name cannot be resolved in the current scope, attempt to
        # import it as a top-level module or package.
        try:
            return importlib.import_module(name)
        except ImportError as e:
            raise ValueError(
                f"Cannot resolve '{name}' in the current scope and failed to "
                f"import it as a top-level module or package."
            ) from e


def find_undefined_variables(
    func_or_var: Callable[..., Any] | type[Any],
) -> dict[str, object]:
    """
    Find variables that are used but not defined in the source of *func_or_var*.

    If the source code for *func_or_var* cannot be retrieved or parsed (e.g.,
    for certain built-in objects or when no source is available), this
    function returns an empty dict instead of raising an exception.
    """
    try:
        # Prefer actual source code over string representations for both
        # callables and other inspectable objects (e.g. classes, modules).
        if inspect.isfunction(func_or_var):
            raw_source = annotation_literalizer.transform(func_or_var)
        else:
            raw_source = inspect.getsource(func_or_var)
    except (OSError, TypeError, SyntaxError):
        # No reliable source available; treat as having no undefined variables.
        return {}

    source = textwrap.dedent(raw_source)

    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Source could not be parsed as Python code; fail gracefully.
        return {}

    visitor = UndefinedVariableVisitor()
    visitor.visit(tree)
    undefined_vars = (visitor.used_vars - visitor.defined_vars).difference(
        set(dir(builtins))
    )
    scope = object_scope.get_scope(func_or_var)
    return {item: _resolve_or_import(item, scope) for item in undefined_vars}


def get_call_dependencies(
    func_or_var: Callable[..., Any] | type[Any],
    version_scraping: versions.VersionScrapingMap | None = None,
    _call_dependencies: CallDependencies | None = None,
) -> CallDependencies:

    call_dependencies: CallDependencies = _call_dependencies or {}

    # Find variables that are used but not defined
    for name, obj in find_undefined_variables(func_or_var).items():
        info = versions.VersionInfo.of(obj, version_scraping=version_scraping)

        if info.version is None:
            if inspect.isclass(obj):
                raise TypeError(f"{name!r} is a class without a version")
            if callable(obj):
                call_dependencies[name] = PackageInfo(
                    name,
                    info,
                    source_code=annotation_literalizer.transform(obj),
                    dependency=get_call_dependencies(
                        obj, version_scraping, call_dependencies
                    ),
                )
            else:
                raise ValueError(
                    f"{name!r} is not a class or callable without a version"
                )
        else:
            if not callable(obj) and not isinstance(obj, types.ModuleType):
                raise ValueError(f"{name!r} is not a callable or module with a version")
            call_dependencies[name] = PackageInfo(name, info)
    return call_dependencies


def get_full_source(func_or_var: Callable[..., Any] | type[Any]) -> PackageInfo:
    try:
        if inspect.isfunction(func_or_var):
            source = annotation_literalizer.transform(func_or_var)
        else:
            source = inspect.getsource(func_or_var)
    except (OSError, TypeError):
        source = None

    return PackageInfo(
        localname=func_or_var.__name__,
        info=versions.VersionInfo.of(func_or_var),
        source_code=source,
        dependency=get_call_dependencies(func_or_var),
    )
