# Notification Service for Device Service
import httpx
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class NotificationChannel(str, Enum):
    """Supported notification channels"""
    FEISHU = "feishu"
    DINGTALK = "dingtalk"
    EMAIL = "email"


class NotificationMessage(BaseModel):
    """Notification message model"""
    title: str
    content: str
    severity: str = "info"  # info, warning, error, critical
    details: Dict[str, Any] = {}


class NotificationService:
    """Service for sending notifications through various channels"""

    def __init__(
        self,
        feishu_webhook: Optional[str] = None,
        dingtalk_webhook: Optional[str] = None,
        smtp_host: Optional[str] = None,
        smtp_port: int = 587,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        email_from: Optional[str] = None,
    ):
        self.feishu_webhook = feishu_webhook
        self.dingtalk_webhook = dingtalk_webhook
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.email_from = email_from

    async def send_notification(
        self,
        message: NotificationMessage,
        channels: List[NotificationChannel],
        recipients: Optional[List[str]] = None,
    ) -> Dict[str, bool]:
        """Send notification through specified channels

        Args:
            message: Notification message
            channels: List of channels to send through
            recipients: Optional list of recipients (emails for email channel)

        Returns:
            Dict mapping channel to success status
        """
        results = {}

        for channel in channels:
            try:
                if channel == NotificationChannel.FEISHU:
                    results[channel] = await self.send_feishu(message)
                elif channel == NotificationChannel.DINGTALK:
                    results[channel] = await self.send_dingtalk(message)
                elif channel == NotificationChannel.EMAIL:
                    if recipients:
                        results[channel] = await self.send_email(message, recipients)
                    else:
                        logger.warning("No recipients specified for email notification")
                        results[channel] = False
            except Exception as e:
                logger.error(f"Failed to send {channel} notification: {e}")
                results[channel] = False

        return results

    async def send_feishu(self, message: NotificationMessage) -> bool:
        """Send notification to Feishu via webhook

        Args:
            message: Notification message

        Returns:
            True if successful
        """
        if not self.feishu_webhook:
            logger.warning("Feishu webhook not configured")
            return False

        try:
            # Feishu interactive card format
            color_map = {
                "info": "blue",
                "warning": "yellow",
                "error": "red",
                "critical": "red",
            }

            card = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {
                            "tag": "plain_text",
                            "content": f"[{message.severity.upper()}] {message.title}"
                        },
                        "template": color_map.get(message.severity, "blue")
                    },
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "tag": "plain_text",
                                "content": message.content
                            }
                        }
                    ]
                }
            }

            # Add details if present
            if message.details:
                fields = []
                for key, value in message.details.items():
                    fields.append({
                        "is_short": True,
                        "text": {
                            "tag": "lark_md",
                            "content": f"**{key}**: {value}"
                        }
                    })
                if fields:
                    card["card"]["elements"].append({
                        "tag": "div",
                        "fields": fields
                    })

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.feishu_webhook,
                    json=card,
                    timeout=10.0
                )

                if response.status_code == 200:
                    logger.info(f"Feishu notification sent: {message.title}")
                    return True
                else:
                    logger.warning(f"Feishu notification failed: {response.status_code}")
                    return False

        except httpx.ConnectError:
            logger.error("Cannot connect to Feishu webhook")
            return False
        except Exception as e:
            logger.error(f"Feishu notification error: {e}")
            return False

    async def send_dingtalk(self, message: NotificationMessage) -> bool:
        """Send notification to DingTalk via webhook

        Args:
            message: Notification message

        Returns:
            True if successful
        """
        if not self.dingtalk_webhook:
            logger.warning("DingTalk webhook not configured")
            return False

        try:
            dingtalk_message = {
                "msgtype": "markdown",
                "markdown": {
                    "title": f"[{message.severity.upper()}] {message.title}",
                    "text": f"### {message.title}\n\n"
                            f"**严重程度**: {message.severity}\n\n"
                            f"**详情**: {message.content}\n\n"
                            f"**时间**: {datetime.utcnow().isoformat()}"
                }
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.dingtalk_webhook,
                    json=dingtalk_message,
                    timeout=10.0
                )

                if response.status_code == 200:
                    logger.info(f"DingTalk notification sent: {message.title}")
                    return True
                else:
                    logger.warning(f"DingTalk notification failed: {response.status_code}")
                    return False

        except httpx.ConnectError:
            logger.error("Cannot connect to DingTalk webhook")
            return False
        except Exception as e:
            logger.error(f"DingTalk notification error: {e}")
            return False

    async def send_email(
        self,
        message: NotificationMessage,
        recipients: List[str],
    ) -> bool:
        """Send email notification via SMTP

        Args:
            message: Notification message
            recipients: List of email addresses

        Returns:
            True if successful
        """
        if not self.smtp_host or not self.smtp_user:
            logger.warning("SMTP not configured")
            return False

        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[{message.severity.upper()}] {message.title}"
            msg["From"] = self.email_from or self.smtp_user
            msg["To"] = ", ".join(recipients)

            # Text body
            text_body = f"{message.title}\n\n{message.content}\n\n"
            if message.details:
                text_body += "Details:\n"
                for key, value in message.details.items():
                    text_body += f"  {key}: {value}\n"
            text_body += f"\nTime: {datetime.utcnow().isoformat()}"

            msg.attach(MIMEText(text_body, "plain"))

            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(
                    self.email_from or self.smtp_user,
                    recipients,
                    msg.as_string()
                )

            logger.info(f"Email notification sent to {len(recipients)} recipients")
            return True

        except Exception as e:
            logger.error(f"Email notification error: {e}")
            return False


# Create default instance from environment
import os

notification_service = NotificationService(
    feishu_webhook=os.getenv("FEISHU_WEBHOOK_URL"),
    dingtalk_webhook=os.getenv("DINGTALK_WEBHOOK_URL"),
    smtp_host=os.getenv("SMTP_HOST"),
    smtp_port=int(os.getenv("SMTP_PORT", "587")),
    smtp_user=os.getenv("SMTP_USER"),
    smtp_password=os.getenv("SMTP_PASSWORD"),
    email_from=os.getenv("EMAIL_FROM"),
)
