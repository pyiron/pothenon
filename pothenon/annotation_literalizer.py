import ast
import inspect
from typing import get_type_hints

def transform(func):
    source = inspect.getsource(func)
    tree = ast.parse(source)

    funcdef = tree.body[0]
    ns = func.__globals__

    hints = get_type_hints(func, include_extras=True)

    # ---- parameters ----
    for arg in funcdef.args.args:
        if arg.arg in hints:
            value = hints[arg.arg]
            arg.annotation = ast.parse(repr(value)).body[0].value

    # ---- return type ----
    if "return" in hints and funcdef.returns is not None:
        ret_value = hints["return"]
        funcdef.returns = ast.parse(repr(ret_value)).body[0].value

    return ast.unparse(tree)
