import importlib.util
import inspect
import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import git


def get_git_info(func: Callable) -> dict:
    """
    Get git information for the repository containing the given function.

    Args:
        func (Callable): The function to inspect.

    Returns:
        dict: A dictionary containing git information, including:
            - file: The file where the function is defined.
            - repo_root: The root directory of the git repository.
            - remote_url: The URL of the remote repository (if any).
            - commit: The current commit hash.
            - short_commit: The short version of the current commit hash.
            - branch: The current branch name (None if detached).
            - dirty: Boolean indicating if there are uncommitted changes.
    """
    # File where the function is defined
    source_path = inspect.getsourcefile(func)
    if source_path is None:
        raise ValueError(f"Cannot determine source file for {func!r}.")
    source_file = Path(source_path).resolve()

    # Find the enclosing git repository
    try:
        repo = git.Repo(source_file, search_parent_directories=True)
    except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError) as e:
        raise ValueError(f"No git repository found for {source_file}.") from e
    # Remote URL (if any)
    try:
        remote_url = repo.remotes.origin.url
    except (AttributeError, IndexError):
        remote_url = None

    return {
        "file": str(source_file.relative_to(repo.working_tree_dir)),
        "repo_root": str(repo.working_tree_dir),
        "remote_url": remote_url,
        "commit": repo.head.commit.hexsha,
        "short_commit": repo.head.commit.hexsha[:7],
        "branch": None if repo.head.is_detached else repo.active_branch.name,
        "dirty": repo.is_dirty(untracked_files=True),
    }


def load_function(
    function_name: str, remote_url: str, file_name: str, commit: str | None = None
):
    with TemporaryDirectory() as tmpdir:
        # Clone the repository
        remote_url = "https://" + remote_url.replace("git@", "").replace(
            "https://", ""
        ).replace(":", "/")
        repo = git.Repo.clone_from(remote_url, tmpdir)

        # Checkout the desired commit
        if commit is not None:
            repo.git.checkout(commit)

        # Load the module
        file_path = Path(tmpdir) / file_name

        spec = importlib.util.spec_from_file_location(
            file_path.stem,
            file_path,
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        return getattr(module, function_name)


@dataclass(frozen=True)
class Dependency:
    name: str
    specifier: str = ""
    source: str = ""

    def __str__(self):
        return f"{self.name}{self.specifier}"


def get_repository_dependencies(
    repo_url: str,
    commit: str | None = None,
) -> list[Dependency] | None:
    """
    Extract dependencies from a git repository.

    Args:
        repo_url (str): Git repository URL.
        commit (str, optional): Commit hash to checkout. Defaults to None.

    Returns:
        List of Dependency objects.
    """

    with TemporaryDirectory() as tmp:
        repo_path = Path(tmp)

        normalized_url = repo_url
        if repo_url.startswith("git@"):
            normalized_url = "https://" + repo_url.replace("git@", "").replace(":", "/")

        repo = git.Repo.clone_from(normalized_url, repo_path)
        if commit:
            repo.git.checkout(commit)

        file_found = False
        for extractor in (
            _from_pyproject,
            _from_requirements,
        ):
            deps = extractor(repo_path)

            if isinstance(deps, list):
                file_found = True

            if deps:
                return deps

    return [] if file_found else None


def _from_pyproject(repo_path: Path) -> list[Dependency] | None:
    path = repo_path / "pyproject.toml"

    if not path.exists():
        return None

    with open(path, "rb") as f:
        data = tomllib.load(f)

    def _from_pep_621(data: dict) -> list[Dependency]:
        result = []
        project = data.get("project", {})

        for dep in project.get("dependencies", []):
            result.append(
                _parse_requirement(
                    dep,
                    "pyproject.toml",
                )
            )

        for group in project.get(
            "optional-dependencies",
            {},
        ).values():

            for dep in group:
                result.append(
                    _parse_requirement(
                        dep,
                        "pyproject.toml",
                    )
                )
        return result

    def _from_poetry(data: dict) -> list[Dependency]:
        result = []
        poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {})

        for name, value in poetry.items():

            if name == "python":
                continue

            if isinstance(value, str):
                result.append(
                    Dependency(
                        name,
                        value,
                        "poetry",
                    )
                )

            elif isinstance(value, dict):
                result.append(
                    Dependency(
                        name,
                        value.get("version", ""),
                        "poetry",
                    )
                )
        return result

    def _from_pdm(data: dict) -> list[Dependency]:
        pdm = data.get("tool", {}).get("pdm", {}).get("dependencies", {})

        return [
            Dependency(
                name,
                str(version),
                "pdm",
            )
            for name, version in pdm.items()
        ]

    for extractor in (
        _from_pep_621,
        _from_poetry,
        _from_pdm,
    ):
        if result := extractor(data):
            return result

    return []


def _parse_requirement(
    requirement: str,
    source: str,
) -> Dependency:

    match = re.match(
        r"([A-Za-z0-9_.-]+)(.*)",
        requirement,
    )

    if not match:
        return Dependency(
            requirement,
            "",
            source,
        )

    return Dependency(
        name=match.group(1),
        specifier=match.group(2),
        source=source,
    )


def _from_requirements(repo_path: Path) -> list[Dependency] | None:

    path = repo_path / "requirements.txt"

    if not path.exists():
        return None

    result: list[Dependency] = []

    def _parse_file(req_path: Path) -> None:
        for raw in req_path.read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue

            if line.startswith(("-r ", "--requirement ")):
                _, include = line.split(maxsplit=1)
                include_path = (req_path.parent / include).resolve()
                if include_path.exists():
                    _parse_file(include_path)
                continue

            if line.startswith("-"):
                continue

            result.append(_parse_requirement(line, req_path.name))

    _parse_file(path)

    return result
