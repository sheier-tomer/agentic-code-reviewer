import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tiktoken

from src.config import settings


@dataclass
class ChunkMetadata:
    file_path: str
    chunk_type: str
    symbol_name: str | None
    start_line: int
    end_line: int
    content: str
    language: str
    docstring: str | None = None
    dependencies: list[str] = field(default_factory=list)
    complexity_score: int | None = None


class CodeChunker:
    MAX_CHUNK_TOKENS = 500
    OVERLAP_TOKENS = 50

    LANGUAGE_MAP = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "jsx",
        ".tsx": "tsx",
    }

    def __init__(self, max_chunk_tokens: int = 500):
        self.max_chunk_tokens = max_chunk_tokens
        self.encoding = tiktoken.get_encoding("cl100k_base")

    def chunk_file(self, file_path: Path, content: str) -> list[ChunkMetadata]:
        extension = file_path.suffix.lower()
        language = self.LANGUAGE_MAP.get(extension, "text")

        if language == "python":
            return self._chunk_python(file_path, content, language)
        else:
            return self._chunk_generic(file_path, content, language)

    def _chunk_python(self, file_path: Path, content: str, language: str) -> list[ChunkMetadata]:
        chunks: list[ChunkMetadata] = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return self._chunk_generic(file_path, content, language)

        lines = content.splitlines()

        module_docstring = ast.get_docstring(tree)
        if module_docstring:
            chunks.append(
                ChunkMetadata(
                    file_path=str(file_path),
                    chunk_type="module",
                    symbol_name=None,
                    start_line=1,
                    end_line=min(10, len(lines)),
                    content="\n".join(lines[: min(10, len(lines))]),
                    language=language,
                    docstring=module_docstring,
                )
            )

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                chunk = self._extract_function(file_path, node, lines, language)
                if chunk:
                    chunks.append(chunk)
            elif isinstance(node, ast.ClassDef):
                class_chunks = self._extract_class(file_path, node, lines, language)
                chunks.extend(class_chunks)

        return chunks if chunks else self._chunk_generic(file_path, content, language)

    def _extract_function(
        self, file_path: Path, node: ast.FunctionDef | ast.AsyncFunctionDef, lines: list[str], language: str
    ) -> ChunkMetadata | None:
        start_line = node.lineno
        end_line = node.end_lineno or start_line
        content = "\n".join(lines[start_line - 1 : end_line])

        token_count = len(self.encoding.encode(content))
        if token_count > self.max_chunk_tokens:
            content = self._truncate_content(content, self.max_chunk_tokens)
            end_line = start_line + content.count("\n")

        dependencies = self._extract_dependencies(node)

        return ChunkMetadata(
            file_path=str(file_path),
            chunk_type="function",
            symbol_name=node.name,
            start_line=start_line,
            end_line=end_line,
            content=content,
            language=language,
            docstring=ast.get_docstring(node),
            dependencies=dependencies,
            complexity_score=self._calculate_complexity(node),
        )

    def _extract_class(
        self, file_path: Path, node: ast.ClassDef, lines: list[str], language: str
    ) -> list[ChunkMetadata]:
        chunks: list[ChunkMetadata] = []

        class_start = node.lineno
        class_end = node.end_lineno or class_start
        class_content = "\n".join(lines[class_start - 1 : class_end])
        class_docstring = ast.get_docstring(node)

        class_token_count = len(self.encoding.encode(class_content))

        if class_token_count <= self.max_chunk_tokens:
            chunks.append(
                ChunkMetadata(
                    file_path=str(file_path),
                    chunk_type="class",
                    symbol_name=node.name,
                    start_line=class_start,
                    end_line=class_end,
                    content=class_content,
                    language=language,
                    docstring=class_docstring,
                )
            )
        else:
            header_end = class_start
            for i, child in enumerate(node.body):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    header_end = child.lineno - 1
                    break

            if header_end > class_start:
                header_content = "\n".join(lines[class_start - 1 : header_end])
                chunks.append(
                    ChunkMetadata(
                        file_path=str(file_path),
                        chunk_type="class",
                        symbol_name=node.name,
                        start_line=class_start,
                        end_line=header_end,
                        content=header_content,
                        language=language,
                        docstring=class_docstring,
                    )
                )

            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_chunk = self._extract_function(file_path, child, lines, language)
                    if method_chunk:
                        chunks.append(method_chunk)

        return chunks

    def _extract_dependencies(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
        dependencies: set[str] = set()

        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                dependencies.add(child.id)
            elif isinstance(child, ast.Attribute):
                if isinstance(child.value, ast.Name):
                    dependencies.add(f"{child.value.id}.{child.attr}")

        return list(dependencies)

    def _calculate_complexity(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
        complexity = 1

        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
            elif isinstance(child, (ast.And, ast.Or)):
                complexity += 1

        return complexity

    def _chunk_generic(self, file_path: Path, content: str, language: str) -> list[ChunkMetadata]:
        chunks: list[ChunkMetadata] = []
        lines = content.splitlines()

        tokens = self.encoding.encode(content)
        total_tokens = len(tokens)

        if total_tokens <= self.max_chunk_tokens:
            return [
                ChunkMetadata(
                    file_path=str(file_path),
                    chunk_type="module",
                    symbol_name=None,
                    start_line=1,
                    end_line=len(lines),
                    content=content,
                    language=language,
                )
            ]

        current_start = 0
        chunk_index = 0

        while current_start < total_tokens:
            current_end = min(current_start + self.max_chunk_tokens, total_tokens)

            chunk_tokens = tokens[current_start:current_end]
            chunk_content = self.encoding.decode(chunk_tokens)

            start_line = self._find_line_number(tokens, current_start, lines)
            end_line = self._find_line_number(tokens, current_end - 1, lines)

            chunks.append(
                ChunkMetadata(
                    file_path=str(file_path),
                    chunk_type="module",
                    symbol_name=f"chunk_{chunk_index}",
                    start_line=start_line,
                    end_line=end_line,
                    content=chunk_content,
                    language=language,
                )
            )

            current_start = current_end - self.OVERLAP_TOKENS
            chunk_index += 1

        return chunks

    def _find_line_number(self, tokens: list[int], token_index: int, lines: list[str]) -> int:
        char_count = 0
        for i, token in enumerate(tokens[: token_index + 1]):
            char_count += len(self.encoding.decode([token]))

        line_num = 1
        current_chars = 0
        for line in lines:
            current_chars += len(line) + 1
            if current_chars >= char_count:
                return line_num
            line_num += 1

        return line_num

    def _truncate_content(self, content: str, max_tokens: int) -> str:
        tokens = self.encoding.encode(content)
        if len(tokens) <= max_tokens:
            return content
        return self.encoding.decode(tokens[:max_tokens])


class DocChunker:
    MAX_CHUNK_TOKENS = 500

    def __init__(self, max_chunk_tokens: int = 500):
        self.max_chunk_tokens = max_chunk_tokens
        self.encoding = tiktoken.get_encoding("cl100k_base")

    def chunk_file(self, file_path: Path, content: str) -> list[ChunkMetadata]:
        extension = file_path.suffix.lower()

        if extension == ".md":
            return self._chunk_markdown(file_path, content)
        else:
            return self._chunk_generic(file_path, content)

    def _chunk_markdown(self, file_path: Path, content: str) -> list[ChunkMetadata]:
        chunks: list[ChunkMetadata] = []
        lines = content.splitlines()

        sections: list[tuple[str, int, int]] = []
        current_section_start = 0
        current_section_title = "Introduction"

        for i, line in enumerate(lines):
            if line.startswith("#"):
                if i > current_section_start:
                    sections.append((current_section_title, current_section_start, i - 1))
                current_section_start = i
                current_section_title = line.lstrip("#").strip()

        if current_section_start < len(lines):
            sections.append((current_section_title, current_section_start, len(lines) - 1))

        for title, start, end in sections:
            section_content = "\n".join(lines[start : end + 1])
            token_count = len(self.encoding.encode(section_content))

            if token_count > self.max_chunk_tokens:
                sub_chunks = self._split_large_section(file_path, section_content, start, title)
                chunks.extend(sub_chunks)
            else:
                chunks.append(
                    ChunkMetadata(
                        file_path=str(file_path),
                        chunk_type="doc",
                        symbol_name=title,
                        start_line=start + 1,
                        end_line=end + 1,
                        content=section_content,
                        language="markdown",
                    )
                )

        return chunks

    def _split_large_section(
        self, file_path: Path, content: str, start_line: int, title: str
    ) -> list[ChunkMetadata]:
        chunks: list[ChunkMetadata] = []
        paragraphs = re.split(r"\n\s*\n", content)

        current_content = ""
        current_start = start_line
        chunk_index = 0

        for para in paragraphs:
            para_with_newline = para + "\n\n"
            if len(self.encoding.encode(current_content + para_with_newline)) > self.max_chunk_tokens:
                if current_content:
                    chunks.append(
                        ChunkMetadata(
                            file_path=str(file_path),
                            chunk_type="doc",
                            symbol_name=f"{title} (part {chunk_index + 1})",
                            start_line=current_start + 1,
                            end_line=current_start + current_content.count("\n"),
                            content=current_content.strip(),
                            language="markdown",
                        )
                    )
                    chunk_index += 1
                current_content = para_with_newline
            else:
                current_content += para_with_newline

        if current_content:
            chunks.append(
                ChunkMetadata(
                    file_path=str(file_path),
                    chunk_type="doc",
                    symbol_name=f"{title} (part {chunk_index + 1})" if chunk_index > 0 else title,
                    start_line=current_start + 1,
                    end_line=current_start + current_content.count("\n"),
                    content=current_content.strip(),
                    language="markdown",
                )
            )

        return chunks

    def _chunk_generic(self, file_path: Path, content: str) -> list[ChunkMetadata]:
        tokens = self.encoding.encode(content)

        if len(tokens) <= self.max_chunk_tokens:
            return [
                ChunkMetadata(
                    file_path=str(file_path),
                    chunk_type="doc",
                    symbol_name=None,
                    start_line=1,
                    end_line=content.count("\n") + 1,
                    content=content,
                    language="text",
                )
            ]

        chunks: list[ChunkMetadata] = []
        lines = content.splitlines()

        for i in range(0, len(tokens), self.max_chunk_tokens):
            chunk_tokens = tokens[i : i + self.max_chunk_tokens]
            chunk_content = self.encoding.decode(chunk_tokens)

            chunks.append(
                ChunkMetadata(
                    file_path=str(file_path),
                    chunk_type="doc",
                    symbol_name=f"chunk_{i // self.max_chunk_tokens}",
                    start_line=1,
                    end_line=len(lines),
                    content=chunk_content,
                    language="text",
                )
            )

        return chunks
