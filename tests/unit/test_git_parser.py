import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pothenon import git_parser


class _MissingOrigin:
    @property
    def origin(self):
        raise IndexError


class TestGetGitInfo(unittest.TestCase):
    def test_get_git_info_returns_metadata(self):
        source_file = "/tmp/repo/tests/unit/test_git_parser.py"
        repo_root = str(Path(source_file).resolve().parents[2])
        relative_source_file = str(Path("tests/unit/test_git_parser.py"))
        repo = SimpleNamespace(
            working_tree_dir=repo_root,
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
                "file": relative_source_file,
                "repo_root": repo_root,
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
        repo.is_dirty.assert_called_once_with(untracked_files=True)

    def test_get_git_info_handles_missing_origin_and_detached_head(self):
        source_file = "/tmp/repo/tests/unit/test_git_parser.py"
        repo_root = str(Path(source_file).resolve().parents[2])
        relative_source_file = str(Path("tests/unit/test_git_parser.py"))
        repo = SimpleNamespace(
            working_tree_dir=repo_root,
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
        self.assertEqual(info["file"], relative_source_file)

    def test_invalid_git_repository(self):
        with (
            patch.object(
                git_parser.inspect, "getsourcefile", return_value="/tmp/repo/missing.py"
            ),
            patch.object(
                git_parser.git,
                "Repo",
                side_effect=git_parser.git.exc.InvalidGitRepositoryError,
            ),
            self.assertRaises(ValueError) as context,
        ):
            _ = git_parser.get_git_info(Path)

        self.assertIn("No git repository found", str(context.exception))

    def test_load_function(self):
        f = git_parser.load_function(
            "DotDict",
            remote_url="git@github.com:pyiron/pyiron_snippets.git",
            file_name="pyiron_snippets/dotdict.py",
        )
        f.my_value = 1
        self.assertEqual(f.my_value, 1)


class TestGetRepositoryDependencies(unittest.TestCase):
    def test_returns_dependencies_from_pyproject_first(self):
        expected = [
            git_parser.Dependency(name="numpy", specifier=">=1.0", source="pyproject")
        ]
        repo = SimpleNamespace(git=SimpleNamespace(checkout=Mock()))

        with (
            patch.object(git_parser.git.Repo, "clone_from", return_value=repo) as clone,
            patch.object(git_parser, "_from_pyproject", return_value=expected) as from_pp,
            patch.object(git_parser, "_from_requirements", return_value=[]) as from_req,
        ):
            result = git_parser.get_repository_dependencies(
                "https://example.com/repo.git", commit="abc123"
            )

        self.assertEqual(result, expected)
        clone.assert_called_once()
        repo.git.checkout.assert_called_once_with("abc123")
        from_pp.assert_called_once()
        from_req.assert_not_called()

    def test_falls_back_to_requirements_when_pyproject_empty(self):
        expected = [
            git_parser.Dependency(
                name="pandas", specifier="==2.0.0", source="requirements.txt"
            )
        ]
        repo = SimpleNamespace(git=SimpleNamespace(checkout=Mock()))

        with (
            patch.object(git_parser.git.Repo, "clone_from", return_value=repo),
            patch.object(git_parser, "_from_pyproject", return_value=[]) as from_pp,
            patch.object(
                git_parser, "_from_requirements", return_value=expected
            ) as from_req,
        ):
            result = git_parser.get_repository_dependencies("https://example.com/repo.git")

        self.assertEqual(result, expected)
        repo.git.checkout.assert_not_called()
        from_pp.assert_called_once()
        from_req.assert_called_once()

    def test_returns_empty_list_when_no_extractors_find_dependencies(self):
        repo = SimpleNamespace(git=SimpleNamespace(checkout=Mock()))

        with (
            patch.object(git_parser.git.Repo, "clone_from", return_value=repo),
            patch.object(git_parser, "_from_pyproject", return_value=[]),
            patch.object(git_parser, "_from_requirements", return_value=[]),
        ):
            result = git_parser.get_repository_dependencies("https://example.com/repo.git")

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
