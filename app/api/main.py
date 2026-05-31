from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy import text

from app.api.routers import countries, fields, graph, papers
from app.db.database import get_session_factory
from app.logging_config import configure_logging
from app.schemas.schemas import HealthResponse

configure_logging()

app = FastAPI(
    title="Paper Citation Explorer API",
    version="1.0.0",
    description=(
        "REST API over the ingested OpenAlex / World Bank / hipolabs corpus. "
        "Serves the citation graph (Tab 1) and country analytics (Tab 2)."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
def health() -> dict:
    database = "up"
    try:
        session = get_session_factory()()
        try:
            session.execute(text("SELECT 1"))
        finally:
            session.close()
    except Exception as exc:
        logger.warning("Health check DB probe failed: {}", exc)
        database = "down"
    return {"status": "ok" if database == "up" else "degraded", "database": database}


app.include_router(papers.router, prefix="/api", tags=["papers"])
app.include_router(graph.router, prefix="/api", tags=["graph"])
app.include_router(fields.router, prefix="/api", tags=["fields"])
app.include_router(countries.router, prefix="/api", tags=["countries"])


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on {} {}: {}", request.method, request.url.path, exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
