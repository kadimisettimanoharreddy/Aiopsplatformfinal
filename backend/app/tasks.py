# backend/app/tasks.py
import logging
import asyncio
import json
import importlib
from celery import Celery
from typing import Dict, Any, Optional
import httpx
import redis

from .config import CELERY_BROKER_URL, API_URL, API_TOKEN, REDIS_URL
from .database import AsyncSessionLocal, get_infra_sync, SyncSessionLocal
from .models import InfrastructureRequest
from sqlalchemy.future import select
from sqlalchemy import update

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

celery_app = Celery("aiops_tasks", broker=CELERY_BROKER_URL)
_redis_client = redis.from_url(REDIS_URL) if REDIS_URL else None


def _run_async_safely(coro_fn, *args, **kwargs):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        coro = coro_fn(*args, **kwargs)
        return loop.run_until_complete(coro)
    finally:
        try:
            to_cancel = asyncio.all_tasks(loop=loop)
            for t in to_cancel:
                t.cancel()
            loop.run_until_complete(asyncio.sleep(0))
        except Exception:
            pass
        try:
            loop.close()
        finally:
            asyncio.set_event_loop(None)


def _update_db_sync(request_identifier: str, pr_number: Optional[int]) -> Dict[str, Any]:
    """
    Synchronous database update to avoid asyncio event loop conflicts.
    This runs in the same thread as Celery task, avoiding the async context issues.
    """
    try:
        with SyncSessionLocal() as db:
            # Use synchronous update query
            if pr_number:
                result = db.execute(
                    update(InfrastructureRequest)
                    .where(InfrastructureRequest.request_identifier == request_identifier)
                    .values(
                        pr_number=int(pr_number),
                        status="pending_approval"
                    )
                )
            else:
                result = db.execute(
                    update(InfrastructureRequest)
                    .where(InfrastructureRequest.request_identifier == request_identifier)
                    .values(status="pr_failed")
                )
            
            db.commit()
            
            if result.rowcount > 0:
                logger.info("Successfully updated DB for %s with PR #%s", request_identifier, pr_number)
                return {"db_updated": True, "rows_affected": result.rowcount}
            else:
                logger.warning("No rows updated for request %s", request_identifier)
                return {"db_updated": False, "error": "no_rows_affected"}
                
    except Exception as e:
        logger.exception("Failed to update DB for %s: %s", request_identifier, e)
        return {"db_updated": False, "db_error": str(e)}


@celery_app.task(name="aiops.health_check")
def health_check() -> str:
    return "ok"


@celery_app.task(name="aiops.process_infrastructure_request")
def process_infrastructure_request(request_identifier: str, user_email: str) -> Dict[str, Any]:
    """
    Celery entrypoint:
    - Perform a short synchronous lookup to ensure the request exists and gather its payload.
    - Then run the async pipeline in an isolated loop, passing the infra payload so the async code
      doesn't do the initial SELECT (avoids asyncpg 'another operation is in progress' races).
    """
    try:
        logger.info("Celery task starting processing: %s", request_identifier)

        # 1) sync lookup (safe in Celery synchronous context)
        try:
            infra_row = get_infra_sync(request_identifier)
        except Exception as e:
            logger.exception("Synchronous DB lookup failed for %s: %s", request_identifier, e)
            return {"request_identifier": request_identifier, "status": "failed", "error": f"sync-db-lookup-failed: {e}"}

        if not infra_row:
            logger.error("Request %s not found (sync lookup)", request_identifier)
            return {"request_identifier": request_identifier, "status": "failed", "error": "request-not-found"}

        # Convert the ORM object to a serializable payload with the fields the async pipeline needs.
        # Adjust field names here if your InfrastructureRequest model stores them differently.
        infra_payload = {
            "id": getattr(infra_row, "id", None),
            "request_identifier": getattr(infra_row, "request_identifier", request_identifier),
            "user_id": getattr(infra_row, "user_id", None),
            "user_email": getattr(infra_row, "user_email", user_email),
            "request_parameters": getattr(infra_row, "request_parameters", None),
            "status": getattr(infra_row, "status", None),
            "created_at": getattr(infra_row, "created_at", None),
        }

        # 2) Run the async orchestration without doing the initial DB select
        result = _run_async_safely(_process_request_async, request_identifier, user_email, infra_payload)
        
        # 3) Update database synchronously after async operations complete
        pr_number = result.get("pr_number")
        db_result = _update_db_sync(request_identifier, pr_number)
        result.update(db_result)
        
        logger.info("Finished processing: %s -> %s", request_identifier, result.get("status"))
        return result

    except Exception as e:
        logger.exception("Error processing request %s: %s", request_identifier, e)
        return {"request_identifier": request_identifier, "status": "failed", "error": str(e)}


async def _process_request_async(request_identifier: str, user_email: str, infra_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Async orchestration pipeline.
    This function RECEIVES the infra_payload (from sync lookup) and DOES NOT perform the initial DB SELECT.
    It continues to:
      - generate TFVARS,
      - create Github PR,
      - notify API and publish Redis.
    Note: Database update is now handled synchronously in the main Celery task.
    """
    try:
        logger.info("Running _process_request_async on loop %s", asyncio.get_running_loop())
    except Exception:
        pass

    result_payload: Dict[str, Any] = {"request_identifier": request_identifier, "status": "failed"}

    # infra_payload is trusted source from sync lookup
    infra = infra_payload

    # 1) Generate TFVARS locally into canonical repo workspace
    try:
        tm_mod = importlib.import_module("app.terraform_manager")
        TerraformManager = getattr(tm_mod, "TerraformManager")
        tm = TerraformManager()
        backend_path, clone_expected_path = await tm.generate_tfvars_for_request(request_identifier, request_obj=infra)
        result_payload["tfvars_written"] = True
        result_payload["tfvars_backend_path"] = str(backend_path)
        result_payload["tfvars_repo_path"] = str(clone_expected_path) if clone_expected_path else None
        logger.info("Local TFVARS generated for %s -> %s", request_identifier, backend_path)
    except Exception as e:
        logger.exception("Terraform tfvars generation failed for %s: %s", request_identifier, e)
        result_payload["tfvars_written"] = False
        result_payload["error"] = "tfvars_generation_failed:" + str(e)
        # continue to attempt PR creation (PR logic may generate tfvars itself)

    # 2) Create GitHub PR (clone remote, copy tfvars into clone, commit, push, create PR)
    pr_number: Optional[int] = None
    try:
        gh_mod = importlib.import_module("app.github_manager")
        GitHubManager = getattr(gh_mod, "GitHubManager")
        gh = GitHubManager()
        pr_number = await gh.create_pull_request(request_identifier)
        result_payload["pr_number"] = pr_number
        result_payload["status"] = "pr_created" if pr_number else "pr_failed"
        logger.info("Created PR #%s for request %s", pr_number, request_identifier)
    except Exception as e:
        logger.exception("GitHubManager failed to create PR for %s: %s", request_identifier, e)
        result_payload["error"] = "pr_creation_failed:" + str(e)
        result_payload["status"] = "failed"

    # 3) Database update is now handled synchronously in the main task

    # 4) Notify API (if configured)
    try:
        if API_URL and API_TOKEN:
            notify_url = f"{API_URL.rstrip('/')}/infrastructure/notify-deployment"
            payload = {
                "request_identifier": request_identifier,
                "user_email": user_email,
                "status": result_payload.get("status"),
                "pr_number": pr_number,
            }
            headers = {"Authorization": f"Bearer {API_TOKEN}", "Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(notify_url, json=payload, headers=headers)
                if resp.status_code in (200, 201):
                    try:
                        result_payload["notify_response"] = resp.json() if resp.content else {"status": "ok"}
                    except Exception:
                        result_payload["notify_response"] = {"status": "ok"}
                else:
                    result_payload["notify_status_code"] = resp.status_code
        else:
            result_payload["notify_error"] = "API_URL or API_TOKEN not configured"
    except Exception as e:
        logger.exception("Failed to notify user API")
        result_payload["notify_error"] = str(e)

    # 5) Publish Redis pubsub for frontend websocket or listeners
    try:
        if _redis_client:
            channel = f"deployment:{request_identifier}"
            msg = json.dumps({"request_id": request_identifier, "pr_number": pr_number, "status": result_payload.get("status")})
            _redis_client.publish(channel, msg)
            result_payload["redis_published"] = True
    except Exception as e:
        logger.exception("Failed to publish Redis message")
        result_payload["redis_published"] = False
        result_payload["redis_publish_error"] = str(e)

    return result_payload