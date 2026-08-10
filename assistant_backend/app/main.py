from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import settings
from .assistant import ask_assistant
from .tools import get_database


app = FastAPI(
    title="YOI Assistant API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.FRONTEND_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


class ChatRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=4000,
    )
    context: dict = Field(
        default_factory=dict,
    )


class ChatResponse(BaseModel):
    answer: str
    model: str
    tool_trace: list[dict]
    usage: dict
    estimated_paid_cost_usd: float
    estimated_current_cost_usd: float
    response_time_ms: float


@app.get("/health")
def health() -> dict:
    database = get_database()
    return {
        "status": "ok",
        "model": settings.GEMINI_MODEL,
        "available_data_tables": sorted(
            database.available_tables
        ),
        "tract_csv_exists": settings.TRACT_YOI_CSV.exists(),
        "region_csv_exists": settings.REGION_YOI_CSV.exists(),
        "indicator_meta_exists": settings.INDICATOR_META_CSV.exists(),
        "methodology_file_exists": settings.METHODOLOGY_FILE.exists(),
    }


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> dict:
    try:
        return ask_assistant(
            request.message,
            context=request.context,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc
