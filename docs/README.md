# pothenon

`pothenon` is a dependency parser for Python functions. Given a callable, it inspects the
function's source code and resolves each external symbol it references to its originating
Python package, including the package's version where available.

## Installation

```bash
pip install pothenon
```

## Usage

```python
from pothenon import dependency_parser
```

### Resolving dependencies of a user-defined function

When a function calls another function that is defined in the same (local) scope, `pothenon`
reports that function together with its own dependencies:

```python
import json
from math import sqrt

def add_one(x):
    return x + 1

def get_sqrt(x):
    return sqrt(x)

def my_operation(x):
    y = add_one(x)
    z = get_sqrt(y)
    return z

def dump_operation(x):
    y = my_operation(x)
    return json.dumps(y)

print(dependency_parser.get_full_source(dump_operation))
```

```
"""
import json

from math import sqrt

def get_sqrt(x):
    return sqrt(x)

def add_one(x):
    return x + 1

def my_operation(x):
    y = add_one(x)
    z = get_sqrt(y)
    return z

def dump_operation(x):
    y = my_operation(x)
    return json.dumps(y)
""" ```

## API

### `dependency_parser.get_call_dependencies(func)`

Analyses *func* and returns a `CallDependencies` dict mapping each external symbol name to a
`PackageInfo` named tuple with the following fields:

| Field | Description |
|---|---|
| `localname` | The name by which the symbol is referenced inside *func* |
| `info` | A `VersionInfo` with `module`, `qualname`, and `version` |
| `source_code` | Source code of the dependency (local callables only) |
| `dependency` | Recursively resolved dependencies of the dependency |

### `dependency_parser.split_by_version_availability(call_dependencies)`

Partitions a `CallDependencies` dict into two dicts: one for dependencies that have a version
string and one for those that do not.
