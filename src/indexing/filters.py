import fnmatch
from pathlib import Path
from typing import Any

from src.config import settings


class IgnoreFilter:
    def __init__(self, ignore_patterns: list[str] | None = None):
        self.ignore_patterns = ignore_patterns or settings.ignore_patterns
        self._compiled_patterns: list[str] = []

    def should_ignore(self, path: Path, repo_root: Path) -> bool:
        try:
            relative_path = path.relative_to(repo_root)
        except ValueError:
            return True

        relative_str = str(relative_path)

        for pattern in self.ignore_patterns:
            if self._matches_pattern(relative_str, pattern):
                return True

        return False

    def _matches_pattern(self, path: str, pattern: str) -> bool:
        if pattern.endswith("/"):
            dir_pattern = pattern[:-1]
            if path.startswith(dir_pattern + "/") or path == dir_pattern:
                return True
            if fnmatch.fnmatch(path + "/", pattern):
                return True

        if fnmatch.fnmatch(path, pattern):
            return True

        if fnmatch.fnmatch(path, f"**/{pattern}"):
            return True

        if "/" not in pattern:
            parts = path.split("/")
            for part in parts:
                if fnmatch.fnmatch(part, pattern):
                    return True

        return False


class GitIgnoreFilter:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.patterns: list[tuple[str, bool]] = []
        self._load_gitignore()

    def _load_gitignore(self) -> None:
        gitignore_path = self.repo_root / ".gitignore"
        if gitignore_path.exists():
            with open(gitignore_path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue

                    is_negation = line.startswith("!")
                    if is_negation:
                        line = line[1:]

                    self.patterns.append((line, is_negation))

    def should_ignore(self, path: Path) -> bool:
        try:
            relative_path = path.relative_to(self.repo_root)
        except ValueError:
            return True

        relative_str = str(relative_path)
        result = False

        for pattern, is_negation in self.patterns:
            if self._matches_gitignore_pattern(relative_str, pattern):
                result = not is_negation

        return result

    def _matches_gitignore_pattern(self, path: str, pattern: str) -> bool:
        if pattern.startswith("/"):
            if path == pattern[1:] or path.startswith(pattern[1:] + "/"):
                return True
        elif pattern.endswith("/"):
            if path.startswith(pattern) or "/" + path.startswith("/" + pattern):
                return True
        else:
            if fnmatch.fnmatch(path, pattern):
                return True
            if fnmatch.fnmatch(path, f"**/{pattern}"):
                return True
            if fnmatch.fnmatch(path, f"*/{pattern}"):
                return True

        return False


class FileFilter:
    SUPPORTED_EXTENSIONS = {
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".md",
        ".txt",
        ".yaml",
        ".yml",
        ".toml",
        ".cfg",
        ".ini",
        ".json",
    }

    BINARY_EXTENSIONS = {
        ".pyc",
        ".pyo",
        ".so",
        ".dll",
        ".dylib",
        ".exe",
        ".bin",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".7z",
        ".mp3",
        ".mp4",
        ".avi",
        ".mov",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".db",
        ".sqlite",
        ".sqlite3",
    }

    def __init__(
        self,
        repo_root: Path,
        ignore_patterns: list[str] | None = None,
        supported_extensions: set[str] | None = None,
    ):
        self.repo_root = repo_root
        self.ignore_filter = IgnoreFilter(ignore_patterns)
        self.gitignore_filter = GitIgnoreFilter(repo_root)
        self.supported_extensions = supported_extensions or self.SUPPORTED_EXTENSIONS

    def should_include(self, path: Path) -> bool:
        if not path.is_file():
            return False

        if self.ignore_filter.should_ignore(path, self.repo_root):
            return False

        if self.gitignore_filter.should_ignore(path):
            return False

        extension = path.suffix.lower()

        if extension in self.BINARY_EXTENSIONS:
            return False

        return True

    def is_code_file(self, path: Path) -> bool:
        return path.suffix.lower() in {".py", ".js", ".ts", ".jsx", ".tsx"}

    def is_doc_file(self, path: Path) -> bool:
        return path.suffix.lower() in {".md", ".txt", ".rst"}

    def is_config_file(self, path: Path) -> bool:
        return path.suffix.lower() in {".yaml", ".yml", ".toml", ".cfg", ".ini", ".json"}


def filter_files(repo_root: Path, file_filter: FileFilter | None = None) -> list[dict[str, Any]]:
    if file_filter is None:
        file_filter = FileFilter(repo_root)

    files: list[dict[str, Any]] = []

    for path in repo_root.rglob("*"):
        if file_filter.should_include(path):
            try:
                stat = path.stat()
                files.append(
                    {
                        "path": str(path.relative_to(repo_root)),
                        "absolute_path": str(path),
                        "size": stat.st_size,
                        "extension": path.suffix.lower(),
                        "is_code": file_filter.is_code_file(path),
                        "is_doc": file_filter.is_doc_file(path),
                        "is_config": file_filter.is_config_file(path),
                    }
                )
            except OSError:
                continue

    return files
