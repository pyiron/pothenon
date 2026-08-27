import json
import subprocess
import sys
import warnings
from functools import cache

from pyiron_snippets import versions


@cache
def _get_conda_packages() -> dict[str, str]:
    result = subprocess.run(
        ["conda", "list", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )

    return {
        pkg["name"]: {
            "version": pkg["version"],
            "source": "pip" if pkg.get("channel") == "pypi" else "conda",
        }
        for pkg in json.loads(result.stdout)
    }


def classify_package(package: versions.VersionInfo) -> str:
    """
    Classify a package as either "stdlib", "conda", "pip", or "unknown".

    Args:
        package (versions.VersionInfo): The package to classify.

    Returns:
        str: The classification of the package.
    """
    if package.module in sys.stdlib_module_names:
        return "stdlib"
    conda_packages = _get_conda_packages()
    if (
        package.module in conda_packages
        and conda_packages[package.module]["version"] == package.version
    ):
        return conda_packages[package.module]["source"]
    warnings.warn(
        f"Package {package.module}=={package.version} not found in conda"
        " environment or in the standard library. This could be due to the"
        " package having a different name in conda.",
        stacklevel=2,
    )
    return "unknown"
