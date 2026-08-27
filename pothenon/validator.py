import sys
import warnings
from functools import cache
from importlib.metadata import distributions, packages_distributions

from pyiron_snippets import versions


@cache
def _get_conda_packages() -> dict[str, dict[str, str]]:
    result = {}
    for dist in distributions():
        meta = dist.metadata
        name = meta.get("Name")
        version = meta.get("Version")
        if not name or not version:
            continue
        installer = (meta.get("Installer") or "").lower()
        source = "pip" if installer == "pip" else "conda"
        result[name] = {"version": version, "source": source}
    return result


@cache
def _get_distribution_map() -> dict[str, list[str]]:
    return packages_distributions()


def classify_package(package: versions.VersionInfo) -> tuple[str, str]:
    """
    Classify a package as either "stdlib", "conda", "pip", or "unknown".

    Args:
        package (versions.VersionInfo): The package to classify.

    Returns:
        tuple[str, str]: A tuple containing the package name and its source.
    """
    module = package.module.split(".", 1)[0]

    if module in sys.stdlib_module_names:
        return module, "stdlib"

    conda_packages = _get_conda_packages()

    # First try the module name directly, since for many packages
    # the import and distribution names are identical.
    candidates = [module]

    # Add distribution names associated with this import name.
    candidates.extend(_get_distribution_map().get(module, []))

    for candidate in candidates:
        conda_package = conda_packages.get(candidate)

        if conda_package is not None and conda_package["version"] == package.version:
            return candidate, conda_package["source"]

    warnings.warn(
        f"Package {package.module}=={package.version} could not be matched to"
        " an installed distribution. Tried distribution names: "
        f"{candidates}.",
        stacklevel=2,
    )
    return "unknown", "unknown"
