import ast
import inspect
import textwrap
from typing import get_type_hints


def transform(func):
    source = textwrap.dedent(inspect.getsource(func))
    tree = ast.parse(source)

    funcdef = tree.body[0]

    hints = get_type_hints(func, include_extras=True)

    # ---- parameters ----
    for arg in funcdef.args.args:
        if arg.arg in hints:
            value = hints[arg.arg]
            try:
                arg.annotation = ast.parse(repr(value)).body[0].value
            except SyntaxError:
                pass

    # ---- return type ----
    if "return" in hints and funcdef.returns is not None:
        ret_value = hints["return"]
        try:
            funcdef.returns = ast.parse(repr(ret_value)).body[0].value
        except SyntaxError:
            pass

    return ast.unparse(tree)
