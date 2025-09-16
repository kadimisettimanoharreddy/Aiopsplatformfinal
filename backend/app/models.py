
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from .database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    department = Column(String(100), nullable=False)
    manager_email = Column(String(255), nullable=False)
    environment_access = Column(JSON, default={"dev": True, "qa": False, "prod": False})
    status = Column(String(20), default="active")
    otp_code = Column(String(6))
    otp_expires_at = Column(DateTime)
    reset_token = Column(String(255))
    reset_token_expires_at = Column(DateTime)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    requests = relationship("InfrastructureRequest", back_populates="user")
    notifications = relationship("UserNotification", back_populates="user")

class EnvironmentApproval(Base):
    __tablename__ = "environment_approvals"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    environment = Column(String(20), nullable=False)
    approval_token = Column(String(255), unique=True, nullable=False)
    status = Column(String(20), default="pending")
    manager_email = Column(String(255), nullable=False)
    requested_at = Column(DateTime, default=datetime.utcnow)
    approved_at = Column(DateTime)

class InfrastructureRequest(Base):
    __tablename__ = "infrastructure_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    request_identifier = Column(String(100), unique=True, nullable=False)
    cloud_provider = Column(String(20), nullable=False)
    environment = Column(String(20), nullable=False)
    resource_type = Column(String(50), nullable=False)
    request_parameters = Column(JSON, nullable=False)
    status = Column(String(30), default="pending")
    pr_number = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    deployed_at = Column(DateTime)
    
    user = relationship("User", back_populates="requests")
    terraform_state = relationship("TerraformState", back_populates="request", uselist=False)
    notifications = relationship("UserNotification", back_populates="request")

class TerraformState(Base):
    __tablename__ = "terraform_states"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey("infrastructure_requests.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    request_identifier = Column(String(100), nullable=False)
    cloud_provider = Column(String(20), nullable=False)
    environment = Column(String(20), nullable=False)
    terraform_state_file = Column(Text, nullable=False)
    resource_ids = Column(JSON)
    status = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    destroyed_at = Column(DateTime)
    
    request = relationship("InfrastructureRequest", back_populates="terraform_state")

class UserNotification(Base):
    __tablename__ = "user_notifications"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    request_id = Column(UUID(as_uuid=True), ForeignKey("infrastructure_requests.id"), nullable=False)
    request_identifier = Column(String(100), nullable=False)
    notification_type = Column(String(50), nullable=False, default='deployment')
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(20), nullable=False)
    deployment_details = Column(JSON, nullable=True)
    terraform_logs = Column(Text, nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    read_at = Column(DateTime, nullable=True)
    
    user = relationship("User", back_populates="notifications")
    request = relationship("InfrastructureRequest", back_populates="notifications")