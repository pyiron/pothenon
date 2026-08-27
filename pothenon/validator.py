import json
import subprocess
import sys
import warnings
from functools import cache

from pyiron_snippets import versions


@cache
def _get_conda_packages() -> dict[str, dict[str, str]]:
    try:
        result = subprocess.run(
            ["conda", "list", "--json"],
            capture_output=True,
            text=True,
            check=True,
        )
        packages = json.loads(result.stdout)
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
    ) as exc:
        warnings.warn(
            f"Unable to query conda packages via `conda list --json`: {exc}",
            stacklevel=2,
        )
        return {}

    return {
        pkg["name"]: {
            "version": pkg["version"],
            "source": "pip" if pkg.get("channel") == "pypi" else "conda",
        }
        for pkg in packages
        if "name" in pkg and "version" in pkg
    }


def classify_package(package: versions.VersionInfo) -> str:
    """
    Classify a package as either "stdlib", "conda", "pip", or "unknown".

    Args:
        package (versions.VersionInfo): The package to classify.

    Returns:
        str: The classification of the package.
    """
    module = package.module.split(".", 1)[0]
    if module in sys.stdlib_module_names:
        return "stdlib"
    conda_packages = _get_conda_packages()
    if (
        module in conda_packages
        and conda_packages[module]["version"] == package.version
    ):
        return conda_packages[module]["source"]
    warnings.warn(
        f"Package {package.module}=={package.version} not found in conda"
        " environment or in the standard library. This could be due to the"
        " package having a different name in conda.",
        stacklevel=2,
    )
    return "unknown"
