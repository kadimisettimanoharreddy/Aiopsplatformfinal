from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timedelta
import secrets

from .database import get_db
from .models import User, EnvironmentApproval
from .schemas import UserCreate, UserLogin, OTPVerify, Token
from .utils import hash_password, verify_password, create_access_token, get_current_user
from .email_service import send_otp_email

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register")
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    otp = str(secrets.randbelow(900000) + 100000)
    
    new_user = User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        department=payload.department,
        manager_email=payload.manager_email,
        otp_code=otp,
        otp_expires_at=datetime.utcnow() + timedelta(minutes=10),
        is_verified=False
    )
    
    db.add(new_user)
    await db.commit()
    
    await send_otp_email(payload.email, otp)
    
    return {
        "message": "Registration successful. OTP sent to your email.",
        "email": payload.email
    }

@router.post("/login")
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid email or password")
    
    if not user.is_verified:
        otp = str(secrets.randbelow(900000) + 100000)
        user.otp_code = otp
        user.otp_expires_at = datetime.utcnow() + timedelta(minutes=10)
        await db.commit()
        
        await send_otp_email(user.email, otp)
        return {
            "message": "Account not verified. OTP sent to your email.",
            "email": user.email,
            "requires_verification": True
        }
    
    otp = str(secrets.randbelow(900000) + 100000)
    user.otp_code = otp
    user.otp_expires_at = datetime.utcnow() + timedelta(minutes=10)
    await db.commit()
    
    await send_otp_email(user.email, otp)
    
    return {
        "message": "OTP sent to your email for secure login.",
        "email": user.email,
        "requires_otp": True
    }

@router.post("/verify-otp", response_model=Token)
async def verify_otp(payload: OTPVerify, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    
    if not user.otp_code or user.otp_code != payload.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    
    if user.otp_expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="OTP expired")
    
    user.otp_code = None
    user.otp_expires_at = None
    user.is_verified = True
    await db.commit()
    
    access_token = create_access_token({"sub": user.email})
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/profile")
async def get_profile(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "name": current_user.name,
        "email": current_user.email,
        "department": current_user.department,
        "environment_access": current_user.environment_access
    }

@router.get("/approve/{token}")
async def approve_environment_access(token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EnvironmentApproval, User)
        .join(User)
        .where(EnvironmentApproval.approval_token == token)
    )
    approval_data = result.first()
    
    if not approval_data:
        raise HTTPException(status_code=404, detail="Invalid approval token")
    
    approval, user = approval_data
    
    if approval.status != "pending":
        return {"message": f"Request already {approval.status}"}
    
    # Update approval status
    approval.status = "approved"
    approval.approved_at = datetime.utcnow()
    
    # Update user environment access
    user.environment_access[approval.environment] = True
    
    await db.commit()
    
    # Send notification to user
    from .websocket_manager import manager
    await manager.send_popup_notification(
        user.email,
        "Environment Access Approved",
        f"Your access to {approval.environment} environment has been approved!",
        "success"
    )
    
    return {"message": f"Access to {approval.environment} environment approved for {user.name}"}