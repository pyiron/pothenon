import inspect
from collections.abc import Callable
from pathlib import Path

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
    source_file = Path(inspect.getsourcefile(func)).resolve()

    # Find the enclosing git repository
    repo = git.Repo(source_file, search_parent_directories=True)

    # Remote URL (if any)
    try:
        remote_url = repo.remotes.origin.url
    except (AttributeError, IndexError):
        remote_url = None

    return {
        "file": str(source_file),
        "repo_root": str(repo.working_tree_dir),
        "remote_url": remote_url,
        "commit": repo.head.commit.hexsha,
        "short_commit": repo.head.commit.hexsha[:7],
        "branch": None if repo.head.is_detached else repo.active_branch.name,
        "dirty": repo.is_dirty(),
    }
