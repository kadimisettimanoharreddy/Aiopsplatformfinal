# backend/app/infrastructure.py
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Dict, Any, Optional
import logging
from datetime import datetime
from uuid import UUID, uuid4

from .database import get_db, AsyncSessionLocal
from .models import User, InfrastructureRequest, TerraformState, UserNotification
from .schemas import InfrastructureRequestCreate
from .utils import get_current_user
from .websocket_manager import manager
from .config import API_TOKEN

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/infrastructure", tags=["infrastructure"])


def verify_github_token(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    try:
        token_type, token = authorization.split(" ", 1)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    if token_type.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid token type")
    if not API_TOKEN or token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid API token")
    return True


async def store_notification_in_db(user_email: str, request_id: str, status: str, details: dict):
    """Store notification for offline users"""
    try:
        async with AsyncSessionLocal() as db:
            # Get user and request
            user_result = await db.execute(select(User).where(User.email == user_email))
            user = user_result.scalar_one_or_none()
            
            request_result = await db.execute(select(InfrastructureRequest).where(InfrastructureRequest.request_identifier == request_id))
            request = request_result.scalar_one_or_none()
            
            if user and request:
                if status == "deployed":
                    title = f"Deployment Successful - {request_id.split('_')[-1]}"
                    message = details.get("message", f"Your infrastructure is ready! Instance ID: {details.get('instance_id', '')}")
                else:
                    title = f"Deployment Failed - {request_id.split('_')[-1]}"
                    message = details.get("message", "Deployment failed. DevOps team has been notified.")
                
                notification = UserNotification(
                    user_id=user.id,
                    request_id=request.id,
                    request_identifier=request_id,
                    notification_type="deployment",
                    title=title,
                    message=message,
                    status=status,
                    deployment_details=details,
                    is_read=False
                )
                db.add(notification)
                await db.commit()
                logger.info(f"Stored notification for {user_email}: {title}")
    except Exception as e:
        logger.error(f"Failed to store notification: {e}")


@router.post("/request")
async def create_infrastructure_request_endpoint(
    request_data: InfrastructureRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        db_request = InfrastructureRequest(
            user_id=current_user.id,
            request_identifier=request_data.request_identifier,
            cloud_provider=request_data.cloud_provider,
            environment=request_data.environment,
            resource_type=request_data.resource_type,
            request_parameters=request_data.parameters,
            status="pending"
        )

        db.add(db_request)
        await db.commit()
        await db.refresh(db_request)

        # dispatch celery
        from .tasks import process_infrastructure_request
        try:
            process_infrastructure_request.delay(request_data.request_identifier, current_user.email)
        except Exception:
            logger.exception("Failed to dispatch Celery task from HTTP endpoint (continuing)")

        logger.info(f"Infrastructure request created: {request_data.request_identifier}")

        return {
            "message": "Infrastructure request created successfully",
            "request_id": request_data.request_identifier,
            "status": "pending"
        }

    except Exception as e:
        logger.exception(f"Error creating infrastructure request: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create infrastructure request")


@router.get("/requests")
async def get_user_requests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        result = await db.execute(
            select(InfrastructureRequest, TerraformState)
            .outerjoin(TerraformState, InfrastructureRequest.request_identifier == TerraformState.request_identifier)
            .where(InfrastructureRequest.user_id == current_user.id)
            .order_by(InfrastructureRequest.created_at.desc())
        )

        requests = []
        for request, state in result.all():
            request_data = {
                "id": str(request.id),
                "request_identifier": request.request_identifier,
                "cloud_provider": request.cloud_provider,
                "environment": request.environment,
                "resource_type": request.resource_type,
                "status": request.status,
                "created_at": request.created_at.isoformat(),
                "pr_number": request.pr_number,
                "deployed_at": request.deployed_at.isoformat() if request.deployed_at else None
            }

            if state and state.resource_ids:
                request_data["resources"] = {
                    "instance_id": state.resource_ids.get("instance_id"),
                    "public_ip": state.resource_ids.get("public_ip"),
                    "console_url": state.resource_ids.get("console_url")
                }

            requests.append(request_data)

        return {"requests": requests}

    except Exception as e:
        logger.exception("Error fetching user requests")
        raise HTTPException(status_code=500, detail="Failed to fetch requests")


async def create_infrastructure_request(request_data: Dict[str, Any]) -> str:
    
    try:
        async with AsyncSessionLocal() as db:
            # Resolve/validate request_identifier
            req_id = request_data.get("request_identifier")
            if not req_id:
                raise ValueError("request_identifier is required in request_data")

            # 1) Resolve user_id
            resolved_user = None
            resolved_user_id = None
            user_id_value = request_data.get("user_id")
            user_email = request_data.get("user_email") or request_data.get("created_by")

            # If user_id provided - try to accept as UUID str or UUID instance
            if user_id_value:
                if isinstance(user_id_value, UUID):
                    resolved_user_id = user_id_value
                elif isinstance(user_id_value, str):
                    try:
                        resolved_user_id = UUID(user_id_value)
                    except Exception:
                        resolved_user_id = None
                else:
                    # numeric ints are not valid for UUID column — ignore and fallback to email
                    resolved_user_id = None

            # If user_id not resolved, try lookup by email
            if not resolved_user_id:
                if not user_email:
                    raise ValueError("Either valid user_id (UUID string) or user_email must be provided")

                q = await db.execute(select(User).where(User.email == user_email))
                user_obj = q.scalar_one_or_none()
                if user_obj:
                    resolved_user = user_obj
                    resolved_user_id = user_obj.id
                else:
                    # Auto-create minimal user so chat-initiated deploys work without manual DB entries
                    # NOTE: you can change creation logic if you want stricter behavior
                    new_user = User(
                        id=uuid4(),
                        email=user_email,
                        name=(user_email.split("@")[0] if isinstance(user_email, str) else "unknown"),
                        department=request_data.get("department") or "unknown"
                        # other optional fields may be left default
                    )
                    db.add(new_user)
                    await db.flush()   # populate new_user.id if necessary
                    # refresh may not be necessary here; we can use new_user.id
                    resolved_user = new_user
                    resolved_user_id = new_user.id
                    logger.info("Auto-created placeholder User for email=%s id=%s", user_email, resolved_user_id)

            # 2) Build the infrastructure request row
            db_request = InfrastructureRequest(
                user_id=resolved_user_id,
                request_identifier=req_id,
                cloud_provider=request_data.get("cloud_provider", "aws"),
                environment=request_data.get("environment", "dev"),
                resource_type=request_data.get("resource_type", "ec2"),
                request_parameters=request_data.get("parameters", {}),
                status="pending"
            )

            db.add(db_request)
            await db.commit()
            await db.refresh(db_request)

            logger.info("Helper created infrastructure request: %s (user_id=%s)", req_id, str(resolved_user_id))

            # 3) Dispatch Celery task so PR/pipeline is triggered automatically
            try:
                # import inside function to avoid circular imports at module load time
                from .tasks import process_infrastructure_request
                user_email_to_dispatch = (resolved_user.email if resolved_user else user_email)
                try:
                    process_infrastructure_request.delay(req_id, user_email_to_dispatch)
                except Exception:
                    # fallback: try synchronous run (useful for dev/debug)
                    logger.exception("Celery dispatch failed, falling back to synchronous processing.")
                    import asyncio as _asyncio
                    _asyncio.run(__import__("app.tasks").tasks._process_request_async(req_id, user_email_to_dispatch))  # note: only fallback
            except Exception:
                logger.exception("Failed to dispatch processing task (continuing)")

            return req_id

    except Exception as e:
        logger.error(f"Error in helper create_infrastructure_request: {str(e)}")
        raise


@router.post("/store-state")
async def store_terraform_state(
    state_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_github_token)
):
    try:
        request_id = state_data.get("request_identifier")
        if not request_id:
            raise HTTPException(status_code=400, detail="request_identifier is required")

        logger.info(f"Storing Terraform state for request: {request_id}")

        result = await db.execute(
            select(InfrastructureRequest).where(
                InfrastructureRequest.request_identifier == request_id
            )
        )
        infra_request = result.scalar_one_or_none()

        if not infra_request:
            logger.error(f"Infrastructure request not found: {request_id}")
            raise HTTPException(status_code=404, detail="Infrastructure request not found")

        existing_state_result = await db.execute(
            select(TerraformState).where(
                TerraformState.request_identifier == request_id
            )
        )
        terraform_state = existing_state_result.scalar_one_or_none()

        resource_ids = {
            "instance_id": state_data.get("instance_id"),
            "public_ip": state_data.get("public_ip"),
            "console_url": state_data.get("console_url")
        }

        if terraform_state:
            terraform_state.terraform_state_file = state_data.get("terraform_state", "")
            terraform_state.resource_ids = resource_ids
            terraform_state.status = state_data.get("status", "deployed")
            logger.info(f"Updated existing Terraform state for: {request_id}")
        else:
            terraform_state = TerraformState(
                request_id=infra_request.id,
                user_id=infra_request.user_id,
                request_identifier=request_id,
                cloud_provider=state_data.get("cloud_provider", infra_request.cloud_provider),
                environment=state_data.get("environment", infra_request.environment),
                terraform_state_file=state_data.get("terraform_state", ""),
                resource_ids=resource_ids,
                status=state_data.get("status", "deployed")
            )
            db.add(terraform_state)
            logger.info(f"Created new Terraform state for: {request_id}")

        infra_request.status = "deployed"
        infra_request.deployed_at = datetime.utcnow()

        await db.commit()

        logger.info(f"Successfully stored Terraform state for request {request_id}")
        return {"message": "Terraform state stored successfully", "status": "success"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error storing Terraform state: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to store Terraform state: {str(e)}")


@router.post("/notify-deployment")
async def notify_deployment_status(
    notification_data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_github_token)
):
    try:
        request_id = notification_data.get("request_identifier")
        user_email = notification_data.get("user_email")
        status = notification_data.get("status")
        
        if not request_id or not user_email:
            raise HTTPException(status_code=400, detail="request_identifier and user_email required")

        logger.info(f"Notification: {request_id} - {status}")

        if status == "pr_created":
            await _notify_pr_created(user_email, request_id, notification_data)
        elif status == "deployed":
            await _notify_deployment_success(user_email, request_id, notification_data, db)
        elif status == "failed":
            await _notify_deployment_failed(user_email, request_id, notification_data, db)

        return {"message": "Notification sent", "status": "success"}

    except Exception as e:
        logger.exception(f"Error sending notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _notify_pr_created(user_email: str, request_id: str, data: Dict[str, Any]):
    pr_number = data.get("pr_number")
    short_id = request_id.split('_')[-1]
    
    message = f"Request {short_id} submitted successfully. Pull Request #{pr_number} created and waiting for DevOps approval."

    await manager.send_personal_message(user_email, {
        "type": "pr_created",
        "request_id": request_id,
        "status": "pending_approval",
        "message": message,
        "buttons": [
            {"text": "Create New Request", "action": "create_ec2"}
        ],
        "show_text_input": True
    })

    await manager.send_popup_notification(
        user_email,
        "Request Submitted",
        f"PR #{pr_number} created. Waiting for approval.",
        "info"
    )


async def _notify_deployment_success(user_email: str, request_id: str, data: Dict[str, Any], db: AsyncSession):
    instance_id = data.get("instance_id", "")
    public_ip = data.get("public_ip", "")
    console_url = data.get("console_url", "")
    ssh_command = data.get("ssh_command", "")
    short_id = request_id.split('_')[-1]
    
    try:
        result = await db.execute(
            select(InfrastructureRequest).where(
                InfrastructureRequest.request_identifier == request_id
            )
        )
        infra_request = result.scalar_one_or_none()
        if infra_request:
            infra_request.status = "deployed"
            infra_request.deployed_at = datetime.utcnow()
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to update status: {e}")

    message = f"""Your infrastructure is ready!

Request: {short_id}
Instance ID: {instance_id}
Public IP: {public_ip}
SSH: {ssh_command}

Console: {console_url}"""

    await manager.send_personal_message(user_email, {
        "type": "deployment_complete",
        "request_id": request_id,
        "status": "deployed",
        "message": message,
        "deployment_data": {
            "instance_id": instance_id,
            "public_ip": public_ip,
            "console_url": console_url,
            "ssh_command": ssh_command
        },
        "buttons": [
            {"text": "Create New Request", "action": "create_ec2"}
        ],
        "show_text_input": True
    })

    popup_actions = []
    if console_url:
        popup_actions.append({
            "text": "Open Console",
            "url": console_url
        })

    await manager.send_popup_notification(
        user_email,
        "Infrastructure Ready!",
        f"Your instance {short_id} is running.",
        "success",
        {
            "instance_id": instance_id,
            "console_url": console_url,
            "actions": popup_actions
        }
    )

    # Store notification for offline users
    await store_notification_in_db(user_email, request_id, "deployed", {
        "message": message,
        "instance_id": instance_id,
        "public_ip": public_ip,
        "console_url": console_url,
        "ssh_command": ssh_command
    })


async def _notify_deployment_failed(user_email: str, request_id: str, data: Dict[str, Any], db: AsyncSession):
    short_id = request_id.split('_')[-1]
    
    try:
        result = await db.execute(
            select(InfrastructureRequest).where(
                InfrastructureRequest.request_identifier == request_id
            )
        )
        infra_request = result.scalar_one_or_none()
        if infra_request:
            infra_request.status = "failed"
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to update status: {e}")

    message = f"Deployment failed for request {short_id}. DevOps team has been notified."

    await manager.send_personal_message(user_email, {
        "type": "deployment_failed",
        "request_id": request_id,
        "status": "failed",
        "message": message,
        "buttons": [
            {"text": "Try Again", "action": "create_ec2"}
        ],
        "show_text_input": True
    })

    await manager.send_popup_notification(
        user_email,
        "Deployment Failed",
        f"Request {short_id} failed. DevOps notified.",
        "error"
    )

    # Store notification for offline users
    await store_notification_in_db(user_email, request_id, "failed", {
        "message": message,
        "error_message": data.get("error_message", "Deployment failed")
    })


@router.get("/health")
async def infrastructure_health():
    return {
        "status": "healthy",
        "service": "infrastructure",
        "timestamp": datetime.utcnow().isoformat()
    }