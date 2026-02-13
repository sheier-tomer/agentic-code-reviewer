from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import CodeChunk
from src.indexing.embedder import Embedder


class VectorSearch:
    def __init__(self, embedder: Embedder | None = None):
        self.embedder = embedder or Embedder()

    async def search(
        self,
        db: AsyncSession,
        query: str,
        repo_id: str | None = None,
        top_k: int = 20,
        min_similarity: float | None = None,
    ) -> list[dict[str, Any]]:
        min_similarity = min_similarity or settings.min_similarity_threshold

        query_embedding = await self.embedder.embed_single(query)

        if repo_id:
            sql = text("""
                SELECT 
                    id, file_path, chunk_type, symbol_name, 
                    start_line, end_line, content, language,
                    1 - (embedding <=> :embedding) as similarity
                FROM code_chunks
                WHERE repo_id = :repo_id
                  AND 1 - (embedding <=> :embedding) > :min_similarity
                ORDER BY similarity DESC
                LIMIT :limit
            """)
            result = await db.execute(
                sql,
                {
                    "embedding": str(query_embedding),
                    "repo_id": repo_id,
                    "min_similarity": min_similarity,
                    "limit": top_k,
                },
            )
        else:
            sql = text("""
                SELECT 
                    id, file_path, chunk_type, symbol_name, 
                    start_line, end_line, content, language,
                    1 - (embedding <=> :embedding) as similarity
                FROM code_chunks
                WHERE 1 - (embedding <=> :embedding) > :min_similarity
                ORDER BY similarity DESC
                LIMIT :limit
            """)
            result = await db.execute(
                sql,
                {
                    "embedding": str(query_embedding),
                    "min_similarity": min_similarity,
                    "limit": top_k,
                },
            )

        rows = result.fetchall()

        return [
            {
                "id": str(row.id),
                "file_path": row.file_path,
                "chunk_type": row.chunk_type,
                "symbol_name": row.symbol_name,
                "start_line": row.start_line,
                "end_line": row.end_line,
                "content": row.content,
                "language": row.language,
                "similarity": float(row.similarity),
            }
            for row in rows
        ]

    async def search_by_symbol(
        self,
        db: AsyncSession,
        symbol_name: str,
        repo_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = select(CodeChunk).where(CodeChunk.symbol_name == symbol_name)

        if repo_id:
            query = query.where(CodeChunk.repo_id == repo_id)

        result = await db.execute(query)
        chunks = result.scalars().all()

        return [
            {
                "id": str(chunk.id),
                "file_path": chunk.file_path,
                "chunk_type": chunk.chunk_type,
                "symbol_name": chunk.symbol_name,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "content": chunk.content,
                "language": chunk.language,
            }
            for chunk in chunks
        ]

    async def get_file_chunks(
        self,
        db: AsyncSession,
        file_path: str,
        repo_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = select(CodeChunk).where(CodeChunk.file_path == file_path)

        if repo_id:
            query = query.where(CodeChunk.repo_id == repo_id)

        query = query.order_by(CodeChunk.start_line)

        result = await db.execute(query)
        chunks = result.scalars().all()

        return [
            {
                "id": str(chunk.id),
                "file_path": chunk.file_path,
                "chunk_type": chunk.chunk_type,
                "symbol_name": chunk.symbol_name,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "content": chunk.content,
                "language": chunk.language,
            }
            for chunk in chunks
        ]
