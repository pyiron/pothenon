import warnings

warnings.warn(
    "pothenon.validator is deprecated; use pothenon.package_resolver instead.",
    DeprecationWarning,
    stacklevel=2,
)

from pothenon.package_resolver import *  # noqa: F401,F403

__all__ = [
    "_get_conda_packages",
    "_get_distribution_map",
    "classify_package",
    "get_conda_environment",
]
