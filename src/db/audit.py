import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AuditLog


class AuditLogger:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(
        self,
        run_id: str,
        event_type: str,
        event_data: dict[str, Any],
        actor: str = "system",
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            id=uuid.uuid4(),
            run_id=uuid.UUID(run_id) if run_id else None,
            event_type=event_type,
            event_data=event_data,
            actor=actor,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=datetime.utcnow(),
        )

        self.db.add(entry)
        await self.db.commit()

        return entry

    async def log_run_started(
        self,
        run_id: str,
        task_type: str,
        task_description: str,
    ) -> None:
        await self.log(
            run_id=run_id,
            event_type="RUN_STARTED",
            event_data={
                "task_type": task_type,
                "task_description": task_description[:500],
            },
        )

    async def log_repo_ingested(
        self,
        run_id: str,
        file_count: int,
        commit_sha: str | None,
    ) -> None:
        await self.log(
            run_id=run_id,
            event_type="REPO_INGESTED",
            event_data={
                "file_count": file_count,
                "commit_sha": commit_sha,
            },
        )

    async def log_context_retrieved(
        self,
        run_id: str,
        chunk_ids: list[str],
        similarities: list[float],
    ) -> None:
        await self.log(
            run_id=run_id,
            event_type="CONTEXT_RETRIEVED",
            event_data={
                "chunk_count": len(chunk_ids),
                "avg_similarity": sum(similarities) / len(similarities) if similarities else 0,
            },
        )

    async def log_plan_generated(
        self,
        run_id: str,
        plan_summary: str,
        confidence: float,
    ) -> None:
        await self.log(
            run_id=run_id,
            event_type="PLAN_GENERATED",
            event_data={
                "plan_summary": plan_summary[:500],
                "confidence": confidence,
            },
        )

    async def log_patch_generated(
        self,
        run_id: str,
        files_affected: list[str],
        lines_added: int,
        lines_removed: int,
    ) -> None:
        await self.log(
            run_id=run_id,
            event_type="PATCH_GENERATED",
            event_data={
                "files_affected": files_affected,
                "lines_added": lines_added,
                "lines_removed": lines_removed,
            },
        )

    async def log_check_executed(
        self,
        run_id: str,
        check_name: str,
        passed: bool,
        error_count: int,
    ) -> None:
        await self.log(
            run_id=run_id,
            event_type="CHECK_EXECUTED",
            event_data={
                "check_name": check_name,
                "passed": passed,
                "error_count": error_count,
            },
        )

    async def log_decision_made(
        self,
        run_id: str,
        decision: str,
        quality_score: float,
        risk_score: float,
    ) -> None:
        await self.log(
            run_id=run_id,
            event_type="DECISION_MADE",
            event_data={
                "decision": decision,
                "quality_score": quality_score,
                "risk_score": risk_score,
            },
        )

    async def get_run_trace(self, run_id: str) -> list[dict[str, Any]]:
        from sqlalchemy import select

        result = await self.db.execute(
            select(AuditLog)
            .where(AuditLog.run_id == uuid.UUID(run_id))
            .order_by(AuditLog.created_at)
        )

        entries = result.scalars().all()

        return [
            {
                "id": str(entry.id),
                "event_type": entry.event_type,
                "event_data": entry.event_data,
                "actor": entry.actor,
                "created_at": entry.created_at.isoformat(),
            }
            for entry in entries
        ]
