import tempfile
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
            patch.object(
                git_parser, "_from_pyproject", return_value=expected
            ) as from_pp,
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
            result = git_parser.get_repository_dependencies(
                "https://example.com/repo.git"
            )

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
            result = git_parser.get_repository_dependencies(
                "https://example.com/repo.git"
            )

        self.assertEqual(result, [])


class TestParseRequirement(unittest.TestCase):
    def test_simple_package(self):
        dep = git_parser._parse_requirement("numpy", "requirements.txt")
        self.assertEqual(dep.name, "numpy")
        self.assertEqual(dep.specifier, "")
        self.assertEqual(dep.source, "requirements.txt")

    def test_with_version_specifier(self):
        dep = git_parser._parse_requirement("numpy>=1.0", "requirements.txt")
        self.assertEqual(dep.name, "numpy")
        self.assertEqual(dep.specifier, ">=1.0")

    def test_with_extras(self):
        dep = git_parser._parse_requirement("requests[security]>=2.0", "pyproject.toml")
        self.assertEqual(dep.name, "requests")
        self.assertEqual(dep.specifier, "[security]>=2.0")

    def test_no_match_returns_raw_as_name(self):
        dep = git_parser._parse_requirement("???", "requirements.txt")
        self.assertEqual(dep.name, "???")
        self.assertEqual(dep.specifier, "")


class TestFromRequirements(unittest.TestCase):
    def _write_file(self, tmp_path, filename, content):
        p = Path(tmp_path) / filename
        p.write_text(content, encoding="utf-8")
        return p

    def test_basic_requirements(self):

        with tempfile.TemporaryDirectory() as tmp:
            self._write_file(tmp, "requirements.txt", "numpy>=1.0\npandas==2.0\n")
            deps = git_parser._from_requirements(Path(tmp))

        self.assertEqual(len(deps), 2)
        self.assertEqual(deps[0].name, "numpy")
        self.assertEqual(deps[0].specifier, ">=1.0")
        self.assertEqual(deps[1].name, "pandas")
        self.assertEqual(deps[1].specifier, "==2.0")

    def test_inline_comments_stripped(self):

        with tempfile.TemporaryDirectory() as tmp:
            self._write_file(tmp, "requirements.txt", "numpy>=1  # pinned\n")
            deps = git_parser._from_requirements(Path(tmp))

        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0].name, "numpy")
        self.assertEqual(deps[0].specifier, ">=1")

    def test_blank_lines_and_comment_only_lines_skipped(self):

        with tempfile.TemporaryDirectory() as tmp:
            self._write_file(tmp, "requirements.txt", "\n# just a comment\nnumpy\n")
            deps = git_parser._from_requirements(Path(tmp))

        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0].name, "numpy")

    def test_flag_lines_skipped(self):

        with tempfile.TemporaryDirectory() as tmp:
            self._write_file(
                tmp, "requirements.txt", "--index-url https://example.com\nnumpy\n"
            )
            deps = git_parser._from_requirements(Path(tmp))

        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0].name, "numpy")

    def test_include_via_r_flag(self):

        with tempfile.TemporaryDirectory() as tmp:
            self._write_file(tmp, "base.txt", "scipy>=1.0\n")
            self._write_file(tmp, "requirements.txt", "-r base.txt\nnumpy\n")
            deps = git_parser._from_requirements(Path(tmp))

        names = [d.name for d in deps]
        self.assertIn("scipy", names)
        self.assertIn("numpy", names)

    def test_missing_requirements_file_returns_empty(self):

        with tempfile.TemporaryDirectory() as tmp:
            deps = git_parser._from_requirements(Path(tmp))

        self.assertIsNone(deps)


class TestFromPyproject(unittest.TestCase):
    def _write_pyproject(self, tmp_path, content):
        p = Path(tmp_path) / "pyproject.toml"
        p.write_text(content, encoding="utf-8")

    def test_pep621_dependencies(self):

        with tempfile.TemporaryDirectory() as tmp:
            self._write_pyproject(
                tmp,
                '[project]\ndependencies = ["numpy>=1.0", "pandas==2.0"]\n',
            )
            deps = git_parser._from_pyproject(Path(tmp))

        self.assertEqual(len(deps), 2)
        self.assertEqual(deps[0].name, "numpy")
        self.assertEqual(deps[0].specifier, ">=1.0")
        self.assertEqual(deps[0].source, "pyproject.toml")
        self.assertEqual(deps[1].name, "pandas")

    def test_pep621_optional_dependencies(self):

        with tempfile.TemporaryDirectory() as tmp:
            self._write_pyproject(
                tmp,
                '[project.optional-dependencies]\ndev = ["pytest>=7"]\n',
            )
            deps = git_parser._from_pyproject(Path(tmp))

        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0].name, "pytest")

    def test_poetry_dependencies(self):

        with tempfile.TemporaryDirectory() as tmp:
            self._write_pyproject(
                tmp,
                '[tool.poetry.dependencies]\npython = "^3.9"\nnumpy = ">=1.0"\n',
            )
            deps = git_parser._from_pyproject(Path(tmp))

        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0].name, "numpy")
        self.assertEqual(deps[0].specifier, ">=1.0")
        self.assertEqual(deps[0].source, "poetry")

    def test_poetry_dict_dependency(self):

        with tempfile.TemporaryDirectory() as tmp:
            self._write_pyproject(
                tmp,
                '[tool.poetry.dependencies]\nnumpy = {version = ">=1.0", optional = true}\n',
            )
            deps = git_parser._from_pyproject(Path(tmp))

        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0].name, "numpy")
        self.assertEqual(deps[0].specifier, ">=1.0")

    def test_pdm_dependencies(self):

        with tempfile.TemporaryDirectory() as tmp:
            self._write_pyproject(
                tmp,
                '[tool.pdm.dependencies]\nnumpy = ">=1.0"\n',
            )
            deps = git_parser._from_pyproject(Path(tmp))

        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0].name, "numpy")
        self.assertEqual(deps[0].source, "pdm")

    def test_missing_pyproject_returns_empty(self):

        with tempfile.TemporaryDirectory() as tmp:
            deps = git_parser._from_pyproject(Path(tmp))

        self.assertIsNone(deps)

    def test_pyproject_with_no_known_sections_returns_empty(self):

        with tempfile.TemporaryDirectory() as tmp:
            self._write_pyproject(tmp, "[build-system]\nrequires = []\n")
            deps = git_parser._from_pyproject(Path(tmp))

        self.assertEqual(deps, [])


if __name__ == "__main__":
    unittest.main()
