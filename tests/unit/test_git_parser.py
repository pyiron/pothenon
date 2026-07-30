from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from pothenon import git_parser


class _MissingOrigin:
    @property
    def origin(self):
        raise IndexError


class TestGetGitInfo(unittest.TestCase):
    def test_get_git_info_returns_metadata(self):
        source_file = "tests/unit/test_git_parser.py"
        repo = SimpleNamespace(
            working_tree_dir="/tmp/repo",
            remotes=SimpleNamespace(
                origin=SimpleNamespace(url="git@github.com:pyiron/pothenon.git")
            ),
            head=SimpleNamespace(
                commit=SimpleNamespace(
                    hexsha="8bc2b82eb6e6c97dad4b3b01ccd522ce2ca6c38a"
                ),
                is_detached=False,
            ),
            active_branch=SimpleNamespace(name="git"),
            is_dirty=Mock(return_value=False),
        )

        with (
            patch.object(git_parser.inspect, "getsourcefile", return_value=source_file),
            patch.object(git_parser.git, "Repo", return_value=repo) as repo_cls,
        ):
            info = git_parser.get_git_info(git_parser.get_git_info)

        self.assertEqual(
            info,
            {
                "file": str(Path(source_file).resolve()),
                "repo_root": "/tmp/repo",
                "remote_url": "git@github.com:pyiron/pothenon.git",
                "commit": "8bc2b82eb6e6c97dad4b3b01ccd522ce2ca6c38a",
                "short_commit": "8bc2b82",
                "branch": "git",
                "dirty": False,
            },
        )
        repo_cls.assert_called_once_with(
            Path(source_file).resolve(), search_parent_directories=True
        )
        repo.is_dirty.assert_called_once_with()

    def test_get_git_info_handles_missing_origin_and_detached_head(self):
        source_file = "tests/unit/test_git_parser.py"
        repo = SimpleNamespace(
            working_tree_dir="/tmp/repo",
            remotes=_MissingOrigin(),
            head=SimpleNamespace(
                commit=SimpleNamespace(
                    hexsha="1234567890abcdef1234567890abcdef12345678"
                ),
                is_detached=True,
            ),
            is_dirty=Mock(return_value=True),
        )

        with (
            patch.object(git_parser.inspect, "getsourcefile", return_value=source_file),
            patch.object(git_parser.git, "Repo", return_value=repo),
        ):
            info = git_parser.get_git_info(git_parser.get_git_info)

        self.assertEqual(info["remote_url"], None)
        self.assertEqual(info["branch"], None)
        self.assertEqual(info["dirty"], True)
        self.assertEqual(info["short_commit"], "1234567")


if __name__ == "__main__":
    unittest.main()
