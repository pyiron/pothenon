import sys
import warnings
from functools import cache
from importlib.metadata import distributions, packages_distributions

from pyiron_snippets import versions


@cache
def _get_conda_packages() -> dict[str, dict[str, str]]:
    try:
        from conda.base.context import context
        from conda.core.prefix_data import PrefixData

        return {
            record.name: {
                "version": record.version,
                "source": "pip" if str(record.channel) == "pypi" else "conda",
            }
            for record in PrefixData(context.active_prefix).iter_records()
        }
    except ImportError:
        pass

    # Fallback: use importlib.metadata when conda is not available
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


def get_conda_environment(
    packages: list[versions.VersionInfo],
    name: str | None = None,
) -> str:
    """
    Get the content of package information to a Conda environment.yml file.

    Standard-library packages are omitted. Unknown packages are skipped
    with a warning.

    Args:
        packages (list[versions.VersionInfo]):
            Packages to export.
        name (str | None):
            Optional Conda environment name.
    """
    conda_dependencies: list[str] = []
    pip_dependencies: list[str] = []

    for package in packages:
        distribution, source = classify_package(package)

        if source == "stdlib":
            continue

        if source == "unknown":
            warnings.warn(
                f"Skipping unknown package " f"{package.module}=={package.version}.",
                stacklevel=2,
            )
            continue

        if source == "conda":
            conda_dependencies.append(f"{distribution}={package.version}")
        elif source == "pip":
            pip_dependencies.append(f"{distribution}=={package.version}")

    lines = []

    if name is not None:
        lines.append(f"name: {name}")

    lines.append("dependencies:")

    for dependency in sorted(set(conda_dependencies)):
        lines.append(f"  - {dependency}")

    if pip_dependencies:
        lines.append("  - pip")
        lines.append("  - pip:")

        for dependency in sorted(set(pip_dependencies)):
            lines.append(f"      - {dependency}")

    return "\n".join(lines)
