# backend/app/main.py
import logging
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .auth import router as auth_router
from .chat import router as chat_router
from .infrastructure import router as infrastructure_router
from .config import ALLOWED_ORIGINS
from .database import engine, Base
from .notification_routes import router as notification_router
from .metrics import MetricsMiddleware, metrics_handler, update_system_metrics
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("aiops_platform")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)

app = FastAPI(title="AIOps Platform API", version="1.0.0")

# Add Prometheus metrics middleware
app.add_middleware(MetricsMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Add metrics endpoint
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return await metrics_handler()

# Health check with metrics
@app.get("/health")
async def health():
    """Service health check"""
    return {"status": "healthy", "service": "AIOps Platform API"}

# Include existing routers
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(infrastructure_router)
app.include_router(notification_router)

try:
    from .notify_handler import start_listener_in_thread
    has_notify = True
except Exception:
    has_notify = False
    logger.info("notify_handler not available; websocket notify listener will not start automatically.")

try:
    from .tasks import celery_app, health_check
    has_celery = True
except Exception:
    celery_app = None
    health_check = None
    has_celery = False
    logger.info("Celery tasks not found; celery-health endpoint will report not configured.")

@app.on_event("startup")
async def startup():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created/ensured successfully.")
    except Exception as e:
        logger.exception(f"Failed to create DB tables on startup: {e}")

    # Start the notify listener thread if available
    if has_notify:
        try:
            start_listener_in_thread()
            logger.info("Started notify listener thread (Redis pubsub -> websocket).")
        except Exception as e:
            logger.exception(f"Failed to start notify listener: {e}")

    # Start system metrics collection
    asyncio.create_task(update_system_metrics())
    logger.info("Started system metrics collection.")

    if has_celery:
        logger.info("Celery available (health_check task present).")
    else:
        logger.info("Celery not configured or tasks module missing. Skipping Celery init.")

@app.get("/celery-health")
async def celery_health():
    """Optional celery health endpoint"""
    if not has_celery or health_check is None:
        return {"status": "unavailable", "detail": "Celery not configured on this instance."}
    
    try:
        async_result = health_check.delay()
        res = async_result.get(timeout=5)
        return {"status": "healthy", "celery_workers": "running", "task_result": res}
    except Exception as e:
        logger.exception("Celery health check failed")
        return {"status": "unhealthy", "error": str(e)}
        

@app.get("/")
async def root():
    return {"message": "Welcome to AIOps Platform API", "status": "ok"}