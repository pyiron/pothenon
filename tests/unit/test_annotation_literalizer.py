import ast
import unittest
from pathlib import Path
from typing import Annotated

from pothenon import annotation_literalizer


def _annotated_function(values: "list[int]") -> "dict[str, int]":
    return {str(v): v for v in values}


def _factory():
    def inner(values: "list[int]") -> "tuple[int, ...]":
        return tuple(values)

    return inner


class _FakeURI:
    def __init__(self, value: str):
        self.value = value

    def __repr__(self) -> str:
        return f"_FakeURI({self.value!r})"


class _FakeNamespace:
    def __init__(self, base: str):
        self.base = base

    def __getattr__(self, name: str) -> _FakeURI:
        return _FakeURI(f"{self.base}{name}")


EX = _FakeNamespace("http://www.example.org/")


def _annotated_with_namespace_literal(
    x: Annotated[float, {"uri": EX.something}],
):
    return x


def _type_hint_without_repr(x: Path):
    return x


class TestAnnotationLiteralizer(unittest.TestCase):
    def test_transform_literalizes_forward_reference_annotations(self):
        transformed = annotation_literalizer.transform(_annotated_function)
        tree = ast.parse(transformed)
        funcdef = tree.body[0]

        self.assertEqual(ast.unparse(funcdef.args.args[0].annotation), "list[int]")
        self.assertEqual(ast.unparse(funcdef.returns), "dict[str, int]")

    def test_transform_handles_nested_function_source(self):
        transformed = annotation_literalizer.transform(_factory())
        tree = ast.parse(transformed)
        funcdef = tree.body[0]

        self.assertEqual(funcdef.name, "inner")
        self.assertEqual(ast.unparse(funcdef.args.args[0].annotation), "list[int]")
        self.assertEqual(ast.unparse(funcdef.returns), "tuple[int, ...]")

    def test_transform_keeps_function_body(self):
        transformed = annotation_literalizer.transform(_annotated_function)
        self.assertIn("return {str(v): v for v in values}", transformed)

    def test_transform_evaluates_attribute_metadata_in_annotated(self):
        transformed = annotation_literalizer.transform(
            _annotated_with_namespace_literal
        )
        tree = ast.parse(transformed)
        funcdef = tree.body[0]
        annotation = ast.unparse(funcdef.args.args[0].annotation)

        self.assertNotIn("EX.something", annotation)
        self.assertIn("http://www.example.org/something", annotation)

    def test_type_hint_without_repr_is_represented_as_string(self):
        transformed = annotation_literalizer.transform(_type_hint_without_repr)
        tree = ast.parse(transformed)
        funcdef = tree.body[0]
        annotation = ast.unparse(funcdef.args.args[0].annotation)
        self.assertEqual(annotation, "Path")


if __name__ == "__main__":
    unittest.main()
