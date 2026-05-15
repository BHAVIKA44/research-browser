import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.exceptions import DomainError
from app.core.logging import configure_logging
from app.core.settings import settings

configure_logging()
app = FastAPI(title="Research Browser API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    request.state.trace_id = request.headers.get("x-trace-id", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["x-request-id"] = request.state.request_id
    response.headers["x-trace-id"] = request.state.trace_id
    return response


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError):
    return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message, "details": exc.details, "request_id": request.state.request_id})


@app.exception_handler(Exception)
async def unknown_error_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"code": "INTERNAL_ERROR", "message": "Unexpected server error", "details": {"error_type": type(exc).__name__}, "request_id": request.state.request_id})


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(router)
