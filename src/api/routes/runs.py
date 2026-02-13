from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import uuid

from src.agent.state import AgentState, Decision, RunStatus, TaskType
from src.agent.graph import build_graph


router = APIRouter(prefix="/api/runs", tags=["runs"])


class CreateRunRequest(BaseModel):
    repo_path: str
    task_description: str
    task_type: str = "review"


class RunResponse(BaseModel):
    id: str
    status: str
    task_type: str
    task_description: str
    decision: Optional[str] = None
    quality_score: Optional[float] = None
    risk_score: Optional[float] = None
    explanation: Optional[str] = None
    diff: Optional[str] = None
    errors: list[str] = []


class RunListResponse(BaseModel):
    id: str
    status: str
    task_type: str
    decision: Optional[str] = None
    quality_score: Optional[float] = None
    risk_score: Optional[float] = None
    created_at: str


@router.post("/", response_model=RunResponse)
async def create_run(request: CreateRunRequest):
    task_type = TaskType(request.task_type.lower())
    
    state = AgentState.create(
        repo_path=request.repo_path,
        task_type=task_type,
        task_description=request.task_description,
    )
    
    graph = build_graph()
    final_state = graph.invoke(state)
    
    return RunResponse(
        id=final_state.run_id,
        status=final_state.status.value,
        task_type=final_state.task_type.value,
        task_description=final_state.task_description,
        decision=final_state.decision.value if final_state.decision else None,
        quality_score=final_state.quality_score,
        risk_score=final_state.risk_score,
        explanation=final_state.explanation,
        diff=final_state.final_diff,
        errors=final_state.errors,
    )


@router.get("/", response_model=list[RunListResponse])
async def list_runs(limit: int = 20):
    from sqlalchemy import select
    from src.db.models import AgentRun, async_session
    
    async with async_session() as db:
        result = await db.execute(
            select(AgentRun)
            .order_by(AgentRun.created_at.desc())
            .limit(limit)
        )
        runs = result.scalars().all()
    
    return [
        RunListResponse(
            id=str(run.id),
            status=run.status,
            task_type=run.task_type,
            decision=run.decision,
            quality_score=run.quality_score,
            risk_score=run.risk_score,
            created_at=run.created_at.isoformat() if run.created_at else "",
        )
        for run in runs
    ]


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: str):
    from sqlalchemy import select
    from src.db.models import AgentRun, Patch, async_session
    
    async with async_session() as db:
        result = await db.execute(
            select(AgentRun).where(AgentRun.id == uuid.UUID(run_id))
        )
        run = result.scalar_one_or_none()
        
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        
        patch_result = await db.execute(
            select(Patch).where(Patch.run_id == run.id)
        )
        patch = patch_result.scalar_one_or_none()
    
    return RunResponse(
        id=str(run.id),
        status=run.status,
        task_type=run.task_type,
        task_description=run.task_description,
        decision=run.decision,
        quality_score=run.quality_score,
        risk_score=run.risk_score,
        diff=patch.diff_content if patch else None,
        errors=[],
    )


@router.get("/{run_id}/diff")
async def get_run_diff(run_id: str):
    from sqlalchemy import select
    from src.db.models import Patch, async_session
    
    async with async_session() as db:
        result = await db.execute(
            select(Patch).where(Patch.run_id == uuid.UUID(run_id))
        )
        patch = result.scalar_one_or_none()
        
        if not patch:
            raise HTTPException(status_code=404, detail="Patch not found")
    
    return {
        "diff": patch.diff_content,
        "files_affected": patch.files_affected,
        "lines_added": patch.lines_added,
        "lines_removed": patch.lines_removed,
    }


@router.get("/{run_id}/audit")
async def get_run_audit(run_id: str):
    from src.db.audit import AuditLogger
    from src.db.models import async_session
    
    async with async_session() as db:
        logger = AuditLogger(db)
        trace = await logger.get_run_trace(run_id)
    
    return {"trace": trace}
