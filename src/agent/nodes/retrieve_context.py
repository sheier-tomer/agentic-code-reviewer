from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.state import AgentState, CodeChunk
from src.agent.tools.vector_search import VectorSearch
from src.indexing.embedder import Embedder


async def retrieve_context(
    state: AgentState,
    db: AsyncSession,
    top_k: int = 20,
) -> AgentState:
    if state.errors:
        return state

    vector_search = VectorSearch(Embedder())

    try:
        results = await vector_search.search(
            db=db,
            query=state.task_description,
            repo_id=state.repo_id,
            top_k=top_k,
        )

        state.retrieved_chunks = [
            CodeChunk(
                id=r["id"],
                file_path=r["file_path"],
                chunk_type=r["chunk_type"],
                symbol_name=r["symbol_name"],
                start_line=r["start_line"],
                end_line=r["end_line"],
                content=r["content"],
                language=r["language"],
                similarity=r["similarity"],
            )
            for r in results
        ]

        affected_files = list({c.file_path for c in state.retrieved_chunks})
        state.affected_files = affected_files[:10]

    except Exception as e:
        state.errors.append(f"Failed to retrieve context: {e}")

    return state
