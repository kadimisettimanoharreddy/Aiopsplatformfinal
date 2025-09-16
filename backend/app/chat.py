# backend/app/chat.py

from fastapi import APIRouter, WebSocket, Query, Depends
from fastapi.websockets import WebSocketDisconnect
import json
import logging
from .websocket_manager import manager
from .llm_processor import LLMProcessor
from .utils import verify_jwt_token
from .models import User

logger = logging.getLogger(__name__)

router = APIRouter()

@router.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    """WebSocket endpoint for chat communication"""
    try:
        # Authenticate user
        payload = verify_jwt_token(token)
        user_email = payload.get("sub")
        if not user_email:
            await websocket.close(code=4001, reason="Invalid token")
            return
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Connect user to WebSocket manager
    await manager.connect(websocket, user_email)
    llm_processor = LLMProcessor()
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            if message_data["type"] == "chat_message":
                # Get user info from database
                user_info = await get_user_info(user_email)
                
                if not user_info:
                    await manager.send_personal_message(user_email, {
                        "type": "chat_response",
                        "message": "User not found. Please log in again.",
                        "buttons": [],
                        "show_text_input": True
                    })
                    continue
                
                # Process message with LLM
                response = await llm_processor.process_user_message(
                    user_email,
                    message_data["message"],
                    user_info
                )
                
                # Send response with buttons
                await manager.send_personal_message(user_email, {
                    "type": "chat_response",
                    "message": response["message"],
                    "buttons": response.get("buttons", []),
                    "show_text_input": response.get("show_text_input", True),
                    "timestamp": message_data.get("timestamp")
                })
                
            elif message_data["type"] == "clear_conversation":
                # Handle conversation clearing
                user_info = await get_user_info(user_email)
                
                response = await llm_processor.process_user_message(
                    user_email,
                    "CLEAR_CONVERSATION",
                    user_info
                )
                
                await manager.send_personal_message(user_email, {
                    "type": "chat_response",
                    "message": response["message"],
                    "buttons": response.get("buttons", []),
                    "show_text_input": True
                })
                
            elif message_data["type"] == "ping":
                # Handle ping/keepalive
                await manager.send_personal_message(user_email, {
                    "type": "pong",
                    "timestamp": message_data.get("timestamp")
                })
                
            else:
                logger.warning(f"Unknown message type: {message_data.get('type')}")
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user: {user_email}")
        manager.disconnect(user_email)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON received from {user_email}: {e}")
        await manager.send_personal_message(user_email, {
            "type": "error",
            "message": "Invalid message format"
        })
    except Exception as e:
        logger.error(f"WebSocket error for user {user_email}: {e}")
        manager.disconnect(user_email)

async def get_user_info(user_email: str) -> dict:
    """Get user information from database"""
    from .database import AsyncSessionLocal
    from sqlalchemy.future import select
    
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.email == user_email))
            user = result.scalar_one_or_none()
            
            if user:
                return {
                    "user_id": str(user.id),
                    "name": user.name,
                    "email": user.email,
                    "department": user.department,
                    "manager_email": user.manager_email,
                    "environment_access": user.environment_access or {}
                }
            
            logger.warning(f"User not found: {user_email}")
            return {}
            
    except Exception as e:
        logger.error(f"Error fetching user info for {user_email}: {e}")
        return {}

# Health check endpoint for chat service
@router.get("/chat/health")
async def chat_health():
    """Health check for chat service"""
    return {
        "status": "healthy",
        "service": "chat",
        "connected_users": len(manager.get_connected_users())
    }