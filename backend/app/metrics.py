# backend/app/metrics.py
import time
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from prometheus_client import CollectorRegistry, multiprocess, REGISTRY
from fastapi import Request, Response
from fastapi.responses import PlainTextResponse
import logging
import psutil
import asyncio
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Create custom registry for multiprocess mode
registry = CollectorRegistry()

# Define metrics for your application
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code'],
    registry=registry
)

REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    registry=registry
)

ACTIVE_CONNECTIONS = Gauge(
    'websocket_connections_active',
    'Number of active WebSocket connections',
    registry=registry
)

INFRASTRUCTURE_REQUESTS = Counter(
    'infrastructure_requests_total',
    'Total infrastructure requests',
    ['cloud_provider', 'environment', 'status'],
    registry=registry
)

DEPLOYMENT_DURATION = Histogram(
    'deployment_duration_seconds',
    'Time taken for deployments',
    ['cloud_provider', 'environment'],
    registry=registry
)

DATABASE_CONNECTIONS = Gauge(
    'database_connections_active',
    'Number of active database connections',
    registry=registry
)

CELERY_TASKS = Counter(
    'celery_tasks_total',
    'Total Celery tasks processed',
    ['task_name', 'status'],
    registry=registry
)

SYSTEM_CPU_USAGE = Gauge(
    'system_cpu_usage_percent',
    'System CPU usage percentage',
    registry=registry
)

SYSTEM_MEMORY_USAGE = Gauge(
    'system_memory_usage_bytes',
    'System memory usage in bytes',
    registry=registry
)

USER_REGISTRATIONS = Counter(
    'user_registrations_total',
    'Total user registrations',
    ['department'],
    registry=registry
)

AUTHENTICATION_ATTEMPTS = Counter(
    'authentication_attempts_total',
    'Total authentication attempts',
    ['status'],
    registry=registry
)

class MetricsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        start_time = time.time()
        
        # Skip metrics endpoint to avoid recursion
        if request.url.path == "/metrics":
            await self.app(scope, receive, send)
            return

        status_code = 200
        
        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            status_code = 500
            raise
        finally:
            # Record metrics
            duration = time.time() - start_time
            method = request.method
            endpoint = request.url.path
            
            REQUEST_COUNT.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code
            ).inc()
            
            REQUEST_DURATION.labels(
                method=method,
                endpoint=endpoint
            ).observe(duration)

async def update_system_metrics():
    """Update system metrics periodically"""
    while True:
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            SYSTEM_CPU_USAGE.set(cpu_percent)
            
            # Memory usage
            memory = psutil.virtual_memory()
            SYSTEM_MEMORY_USAGE.set(memory.used)
            
            await asyncio.sleep(30)  # Update every 30 seconds
        except Exception as e:
            logger.error(f"Error updating system metrics: {e}")
            await asyncio.sleep(30)

def track_websocket_connection(increment: bool = True):
    """Track WebSocket connections"""
    if increment:
        ACTIVE_CONNECTIONS.inc()
    else:
        ACTIVE_CONNECTIONS.dec()

def track_infrastructure_request(cloud_provider: str, environment: str, status: str):
    """Track infrastructure requests"""
    INFRASTRUCTURE_REQUESTS.labels(
        cloud_provider=cloud_provider,
        environment=environment,
        status=status
    ).inc()

def track_deployment_time(cloud_provider: str, environment: str, duration: float):
    """Track deployment duration"""
    DEPLOYMENT_DURATION.labels(
        cloud_provider=cloud_provider,
        environment=environment
    ).observe(duration)

def track_user_registration(department: str):
    """Track user registrations by department"""
    USER_REGISTRATIONS.labels(department=department).inc()

def track_authentication(success: bool):
    """Track authentication attempts"""
    status = "success" if success else "failure"
    AUTHENTICATION_ATTEMPTS.labels(status=status).inc()

def track_celery_task(task_name: str, status: str):
    """Track Celery task completion"""
    CELERY_TASKS.labels(task_name=task_name, status=status).inc()

async def metrics_handler() -> Response:
    """Endpoint to expose metrics"""
    try:
        data = generate_latest(registry)
        return PlainTextResponse(data, media_type=CONTENT_TYPE_LATEST)
    except Exception as e:
        logger.error(f"Error generating metrics: {e}")
        return PlainTextResponse("Error generating metrics", status_code=500)