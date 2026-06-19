import ast
import unittest

from pothenon import annotation_literalizer


def _annotated_function(values: "list[int]") -> "dict[str, int]":
    return {str(v): v for v in values}


def _factory():
    def inner(values: "list[int]") -> "tuple[int, ...]":
        return tuple(values)

    return inner


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


if __name__ == "__main__":
    unittest.main()
