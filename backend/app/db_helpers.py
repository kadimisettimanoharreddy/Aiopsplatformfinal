import logging
from typing import Optional
from .database import AsyncSessionLocal
from .models import InfrastructureRequest, User
from sqlalchemy.future import select

logger = logging.getLogger(__name__)

async def get_user_email_by_request(request_identifier: str) -> Optional[str]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(InfrastructureRequest, User)
            .join(User, User.id == InfrastructureRequest.user_id)
            .where(InfrastructureRequest.request_identifier == request_identifier)
        )
        row = result.first()
        if not row:
            return None
        infra, user = row
        return user.email
