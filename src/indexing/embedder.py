import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from src.config import settings
from src.indexing.chunker import ChunkMetadata, CodeChunker, DocChunker
from src.indexing.filters import FileFilter, filter_files


@dataclass
class EmbeddedChunk:
    id: str
    file_path: str
    chunk_type: str
    symbol_name: str | None
    start_line: int
    end_line: int
    content: str
    language: str
    embedding: list[float]
    docstring: str | None = None
    dependencies: list[str] | None = None
    complexity_score: int | None = None


class Embedder:
    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self.model = model or settings.embedding_model
        effective_base_url = base_url or settings.openai_base_url or None
        self.client = AsyncOpenAI(
            api_key=api_key or settings.openai_api_key,
            base_url=effective_base_url,
        )

    async def embed_single(self, text: str) -> list[float]:
        response = await self.client.embeddings.create(input=text, model=self.model)
        return response.data[0].embedding

    async def embed_batch(self, texts: list[str], batch_size: int = 100) -> list[list[float]]:
        embeddings: list[list[float]] = []
        
        # Filter out empty texts
        valid_texts = [t for t in texts if t and t.strip()]
        if not valid_texts:
            return []

        for i in range(0, len(valid_texts), batch_size):
            batch = valid_texts[i : i + batch_size]
            response = await self.client.embeddings.create(input=batch, model=self.model)
            batch_embeddings = [item.embedding for item in response.data]
            embeddings.extend(batch_embeddings)

        return embeddings


class RepoIngester:
    MAX_FILE_SIZE = 1_000_000

    def __init__(
        self,
        repo_root: Path,
        embedder: Embedder | None = None,
        code_chunker: CodeChunker | None = None,
        doc_chunker: DocChunker | None = None,
    ):
        self.repo_root = repo_root
        self.embedder = embedder or Embedder()
        self.code_chunker = code_chunker or CodeChunker()
        self.doc_chunker = doc_chunker or DocChunker()
        self.file_filter = FileFilter(repo_root)

    async def ingest(self) -> tuple[list[EmbeddedChunk], list[dict[str, Any]]]:
        file_manifest = filter_files(self.repo_root, self.file_filter)
        all_chunks: list[ChunkMetadata] = []

        for file_info in file_manifest:
            file_path = Path(file_info["absolute_path"])

            if file_info["size"] > self.MAX_FILE_SIZE:
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            if file_info["is_code"]:
                chunks = self.code_chunker.chunk_file(file_path, content)
            elif file_info["is_doc"]:
                chunks = self.doc_chunker.chunk_file(file_path, content)
            else:
                continue

            all_chunks.extend(chunks)

        embedded_chunks = await self._embed_chunks(all_chunks)

        return embedded_chunks, file_manifest

    async def _embed_chunks(self, chunks: list[ChunkMetadata]) -> list[EmbeddedChunk]:
        if not chunks:
            return []

        import uuid

        # Filter out chunks with empty content
        valid_chunks = [c for c in chunks if c.content and c.content.strip()]
        if not valid_chunks:
            return []

        texts = [self._prepare_text_for_embedding(chunk) for chunk in valid_chunks]
        embeddings = await self.embedder.embed_batch(texts)

        embedded_chunks: list[EmbeddedChunk] = []
        for i, chunk in enumerate(valid_chunks):
            embedded_chunks.append(
                EmbeddedChunk(
                    id=str(uuid.uuid4()),
                    file_path=chunk.file_path,
                    chunk_type=chunk.chunk_type,
                    symbol_name=chunk.symbol_name,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    content=chunk.content,
                    language=chunk.language,
                    embedding=embeddings[i],
                    docstring=chunk.docstring,
                    dependencies=chunk.dependencies,
                    complexity_score=chunk.complexity_score,
                )
            )

        return embedded_chunks

    def _prepare_text_for_embedding(self, chunk: ChunkMetadata) -> str:
        parts: list[str] = []

        if chunk.symbol_name:
            parts.append(f"Symbol: {chunk.symbol_name}")

        if chunk.docstring:
            parts.append(f"Documentation: {chunk.docstring}")

        parts.append(chunk.content)

        return "\n".join(parts)


async def ingest_repository(repo_path: Path) -> tuple[list[EmbeddedChunk], list[dict[str, Any]]]:
    ingester = RepoIngester(repo_path)
    return await ingester.ingest()
