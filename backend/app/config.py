from pathlib import Path
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)


AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_DEFAULT_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

API_TOKEN = os.getenv("API_TOKEN", "github-actions-service-token-change-in-production")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://conversacloud:password@localhost/conversacloud")

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Security
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Email
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# Frontend
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# GitHub
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO_OWNER = os.getenv("GITHUB_REPO_OWNER", "your-org")
GITHUB_REPO_NAME = os.getenv("GITHUB_REPO_NAME", "conversacloud")

# API
API_URL = os.getenv("API_URL", "http://localhost:8000")

# Celery
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")

# LLM intent parsing toggle
LLM_INTENT_ENABLED = os.getenv("LLM_INTENT_ENABLED", "true").lower() == "true"

# CORS
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    FRONTEND_URL
]
