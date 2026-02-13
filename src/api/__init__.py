from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import health_router, runs_router
from src.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agentic AI Code Reviewer",
        description="AI-powered code review and auto-refactor system",
        version="0.1.0",
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.include_router(health_router)
    app.include_router(runs_router, prefix="/api")
    
    @app.on_event("startup")
    async def startup():
        pass
    
    @app.on_event("shutdown")
    async def shutdown():
        pass
    
    return app
