# backend/app/email_service.py

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from .config import SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, FRONTEND_URL

logger = logging.getLogger(__name__)


async def send_otp_email(to_email: str, otp: str):
    try:
        subject = "ConversaCloud - Login OTP"
        
        html_body = f"""
        <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">ConversaCloud</h1>
                </div>
                <div style="padding: 30px; background: #f9f9f9;">
                    <h2 style="color: #333;">Your Login OTP</h2>
                    <p style="font-size: 16px; color: #666;">Use this OTP to complete your login:</p>
                    <div style="background: white; padding: 20px; text-align: center; border-radius: 8px; margin: 20px 0;">
                        <h1 style="font-size: 32px; color: #667eea; margin: 0; letter-spacing: 5px;">{otp}</h1>
                    </div>
                    <p style="color: #999; font-size: 14px;">This OTP will expire in 10 minutes.</p>
                </div>
            </body>
        </html>
        """
        
        await send_email(to_email, subject, html_body)
        return True
    except Exception as e:
        logger.error(f"Failed to send OTP email: {e}")
        return False


async def send_environment_approval_email(manager_email: str, user_name: str, environment: str, approval_token: str):
    try:
        approve_link = f"{FRONTEND_URL}/approve/{approval_token}"
        deny_link = f"{FRONTEND_URL}/deny/{approval_token}"
        subject = f"Environment Access Request - {user_name}"
        
        html_body = f"""
        <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">ConversaCloud</h1>
                </div>
                <div style="padding: 30px; background: #f9f9f9;">
                    <h2 style="color: #333;">Environment Access Request</h2>
                    <p style="font-size: 16px; color: #666;">
                        <strong>{user_name}</strong> is requesting access to the 
                        <strong>{environment.upper()}</strong> environment.
                    </p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{approve_link}" style="background: #4CAF50; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block; margin-right: 10px;">Approve</a>
                        <a href="{deny_link}" style="background: #f44336; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">Deny</a>
                    </div>
                    <p style="color: #999; font-size: 14px;">This request will expire in 24 hours.</p>
                </div>
            </body>
        </html>
        """
        
        await send_email(manager_email, subject, html_body)
        return True
    except Exception as e:
        logger.error(f"Failed to send approval email: {e}")
        return False


async def send_email(to_email: str, subject: str, html_body: str):
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        logger.info(f"Email would be sent to {to_email}: {subject}")
        return
        
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = SMTP_USERNAME
    msg['To'] = to_email
    
    html_part = MIMEText(html_body, 'html')
    msg.attach(html_part)
    
    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.starttls()
    server.login(SMTP_USERNAME, SMTP_PASSWORD)
    server.send_message(msg)
    server.quit()