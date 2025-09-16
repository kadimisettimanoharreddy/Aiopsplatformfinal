from fastapi import WebSocket
from typing import Dict, Optional
import json
import logging
import asyncio

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept WebSocket connection and store user mapping"""
        await websocket.accept()
        self.active_connections[user_id] = websocket
        logger.info(f"User {user_id} connected via WebSocket")

    def disconnect(self, user_id: str):
        """Remove user connection"""
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            logger.info(f"User {user_id} disconnected from WebSocket")

    async def send_personal_message(self, user_id: str, message: dict):
        """Send message to specific user"""
        if user_id in self.active_connections:
            websocket = self.active_connections[user_id]
            try:
                await websocket.send_text(json.dumps(message))
                logger.debug(f"Sent message to {user_id}: {message.get('type', 'unknown')}")
            except Exception as e:
                logger.error(f"Error sending message to {user_id}: {e}")
                self.disconnect(user_id)

    async def send_popup_notification(
        self, 
        user_id: str, 
        title: str, 
        message: str, 
        notification_type: str = "info",
        extra_data: Optional[dict] = None
    ):
        """Send popup notification to user with enhanced data"""
        notification_data = {
            "type": "popup_notification",
            "popup": {
                "title": title,
                "message": message,
                "type": notification_type,
                "duration": 8000 if notification_type == "success" else 5000,
                "timestamp": asyncio.get_event_loop().time()
            }
        }
        
        # Add extra data for rich notifications (like deployment info)
        if extra_data:
            notification_data["popup"]["data"] = extra_data
            
            # Add action URL for deployment notifications
            if extra_data.get("console_url"):
                notification_data["popup"]["actionUrl"] = extra_data["console_url"]
                notification_data["popup"]["actionText"] = "ACCESS CONSOLE"
        
        await self.send_personal_message(user_id, notification_data)
        logger.info(f"Sent {notification_type} popup to {user_id}: {title}")

    async def send_deployment_notification(
        self,
        user_id: str,
        request_id: str,
        deployment_details: dict
    ):
        """Send detailed deployment completion notification"""
        try:
            # Extract key information
            instance_id = deployment_details.get('instance_id', '')
            public_ip = deployment_details.get('public_ip', '')
            console_url = deployment_details.get('console_url', '')
            ssh_command = deployment_details.get('ssh_command', '')
            resource_name = deployment_details.get('resource_name', request_id)
            
            # Determine resource type for message
            resource_type = "EC2 Instance" if "ec2" in request_id else "Virtual Machine"
            
            # Send popup notification
            await self.send_popup_notification(
                user_id,
                f"{resource_type} Ready!",
                f"Your {resource_name} is now running and ready to use.",
                "success",
                {
                    "request_id": request_id,
                    "resource_name": resource_name,
                    "instance_id": instance_id,
                    "public_ip": public_ip,
                    "console_url": console_url,
                    "ssh_command": ssh_command,
                    "deployment_time": asyncio.get_event_loop().time()
                }
            )
            
            # Also send detailed message for the chat (optional)
            detailed_message = {
                "type": "deployment_complete",
                "request_id": request_id,
                "details": deployment_details
            }
            
            await self.send_personal_message(user_id, detailed_message)
            
        except Exception as e:
            logger.error(f"Error sending deployment notification: {e}")

    async def send_pr_notification(self, user_id: str, request_id: str, pr_number: int):
        """Send pull request created notification"""
        await self.send_popup_notification(
            user_id,
            "Pull Request Created",
            f"Your request {request_id.split('_')[-2]} submitted as PR #{pr_number}. You'll be notified when deployed.",
            "info"
        )

    async def send_approval_notification(self, user_id: str, environment: str, approved: bool):
        """Send environment approval notification"""
        if approved:
            await self.send_popup_notification(
                user_id,
                "Environment Access Approved",
                f"You now have access to {environment} environment. You can create resources there.",
                "success"
            )
        else:
            await self.send_popup_notification(
                user_id,
                "Environment Access Denied", 
                f"Access to {environment} environment was not approved. Contact your manager for details.",
                "error"
            )

    async def send_error_notification(self, user_id: str, title: str, message: str):
        """Send error notification to user"""
        await self.send_popup_notification(
            user_id,
            title,
            message,
            "error"
        )

    async def broadcast_message(self, message: dict):
        """Send message to all connected users (admin only)"""
        disconnected_users = []
        
        for user_id, websocket in self.active_connections.items():
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error broadcasting to {user_id}: {e}")
                disconnected_users.append(user_id)
        
        # Clean up disconnected users
        for user_id in disconnected_users:
            self.disconnect(user_id)
        
        logger.info(f"Broadcasted message to {len(self.active_connections)} users")

    def get_connected_users(self) -> list:
        """Get list of currently connected users"""
        return list(self.active_connections.keys())

    def is_user_connected(self, user_id: str) -> bool:
        """Check if specific user is connected"""
        return user_id in self.active_connections


manager = ConnectionManager()