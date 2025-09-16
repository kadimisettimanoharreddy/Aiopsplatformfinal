# backend/app/notifications.py
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from typing import List, Dict, Any
from .database import AsyncSessionLocal
from .models import UserNotification
from sqlalchemy.future import select
from sqlalchemy import desc, func
from .utils import get_current_user  # Changed from .auth to .utils
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/api/notifications")
async def get_user_notifications(
    current_user: dict = Depends(get_current_user),
    limit: int = 20,
    unread_only: bool = False
):
    """Get user's notifications"""
    try:
        async with AsyncSessionLocal() as db:
            query = (
                select(UserNotification)
                .where(UserNotification.user_id == current_user['id'])
                .order_by(desc(UserNotification.created_at))
            )
            
            if unread_only:
                query = query.where(UserNotification.is_read == False)
            
            query = query.limit(limit)
            
            result = await db.execute(query)
            notifications = result.scalars().all()
            
            # Get unread count
            unread_result = await db.execute(
                select(func.count(UserNotification.id))
                .where(
                    UserNotification.user_id == current_user['id'],
                    UserNotification.is_read == False
                )
            )
            unread_count = unread_result.scalar()
            
            notification_responses = []
            for notif in notifications:
                notification_responses.append({
                    "id": str(notif.id),
                    "title": notif.title,
                    "message": notif.message,
                    "status": notif.status,
                    "deployment_details": notif.deployment_details or {},
                    "terraform_logs": notif.terraform_logs,
                    "is_read": notif.is_read,
                    "created_at": notif.created_at.isoformat(),
                    "read_at": notif.read_at.isoformat() if notif.read_at else None
                })
            
            return {
                "notifications": notification_responses,
                "unread_count": unread_count or 0,
                "total_count": len(notification_responses)
            }
            
    except Exception as e:
        logger.error(f"Failed to get notifications: {e}")
        return {"notifications": [], "unread_count": 0, "total_count": 0}

@router.post("/api/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Mark specific notification as read"""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(UserNotification)
                .where(
                    UserNotification.id == notification_id,
                    UserNotification.user_id == current_user['id']
                )
            )
            notification = result.scalar_one_or_none()
            
            if not notification:
                return {"error": "Notification not found"}
            
            notification.is_read = True
            notification.read_at = datetime.utcnow()
            await db.commit()
            
            return {"message": "Notification marked as read"}
            
    except Exception as e:
        logger.error(f"Failed to mark notification as read: {e}")
        return {"error": "Failed to update notification"}

@router.post("/api/notifications/mark-all-read")
async def mark_all_notifications_read(current_user: dict = Depends(get_current_user)):
    """Mark all user's notifications as read"""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(UserNotification)
                .where(
                    UserNotification.user_id == current_user['id'],
                    UserNotification.is_read == False
                )
            )
            notifications = result.scalars().all()
            
            for notification in notifications:
                notification.is_read = True
                notification.read_at = datetime.utcnow()
            
            await db.commit()
            
            return {"message": f"Marked {len(notifications)} notifications as read"}
            
    except Exception as e:
        logger.error(f"Failed to mark all notifications as read: {e}")
        return {"error": "Failed to update notifications"}

@router.get("/api/notifications/unread-count")
async def get_unread_count(current_user: dict = Depends(get_current_user)):
    """Get count of unread notifications"""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(func.count(UserNotification.id))
                .where(
                    UserNotification.user_id == current_user['id'],
                    UserNotification.is_read == False
                )
            )
            unread_count = result.scalar()
            return {"unread_count": unread_count or 0}
            
    except Exception as e:
        logger.error(f"Failed to get unread count: {e}")
        return {"unread_count": 0}