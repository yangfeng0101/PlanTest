# Notification Service for Report Service
import httpx
import logging
import os
import asyncio
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


class NotificationLog(BaseModel):
    """Notification log entry"""
    id: str
    channel: NotificationChannel
    recipient: str
    title: str
    success: bool
    error_message: Optional[str] = None
    timestamp: datetime = datetime.utcnow()


# In-memory notification log storage
_notification_logs: List[NotificationLog] = []


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
        smtp_use_tls: bool = True,
    ):
        self.feishu_webhook = feishu_webhook
        self.dingtalk_webhook = dingtalk_webhook
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.email_from = email_from
        self.smtp_use_tls = smtp_use_tls

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
        import uuid

        if not self.feishu_webhook:
            logger.warning("Feishu webhook not configured")
            self._log_notification(
                NotificationChannel.FEISHU,
                "not_configured",
                message.title,
                False,
                "Feishu webhook URL not configured"
            )
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
                    self._log_notification(
                        NotificationChannel.FEISHU,
                        self.feishu_webhook,
                        message.title,
                        True
                    )
                    return True
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                    logger.warning(f"Feishu notification failed: {error_msg}")
                    self._log_notification(
                        NotificationChannel.FEISHU,
                        self.feishu_webhook,
                        message.title,
                        False,
                        error_msg
                    )
                    return False

        except httpx.ConnectError as e:
            error_msg = "Cannot connect to Feishu webhook"
            logger.error(error_msg)
            self._log_notification(
                NotificationChannel.FEISHU,
                self.feishu_webhook,
                message.title,
                False,
                error_msg
            )
            return False
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Feishu notification error: {error_msg}")
            self._log_notification(
                NotificationChannel.FEISHU,
                self.feishu_webhook or "unknown",
                message.title,
                False,
                error_msg
            )
            return False

    async def send_dingtalk(self, message: NotificationMessage) -> bool:
        """Send notification to DingTalk via webhook

        Args:
            message: Notification message

        Returns:
            True if successful
        """
        import uuid

        if not self.dingtalk_webhook:
            logger.warning("DingTalk webhook not configured")
            self._log_notification(
                NotificationChannel.DINGTALK,
                "not_configured",
                message.title,
                False,
                "DingTalk webhook URL not configured"
            )
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
                    result = response.json()
                    # DingTalk returns {"errcode": 0, "errmsg": "ok"} on success
                    if result.get("errcode") == 0:
                        logger.info(f"DingTalk notification sent: {message.title}")
                        self._log_notification(
                            NotificationChannel.DINGTALK,
                            self.dingtalk_webhook,
                            message.title,
                            True
                        )
                        return True
                    else:
                        error_msg = f"errcode: {result.get('errcode')}, errmsg: {result.get('errmsg')}"
                        logger.warning(f"DingTalk notification failed: {error_msg}")
                        self._log_notification(
                            NotificationChannel.DINGTALK,
                            self.dingtalk_webhook,
                            message.title,
                            False,
                            error_msg
                        )
                        return False
                else:
                    error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
                    logger.warning(f"DingTalk notification failed: {error_msg}")
                    self._log_notification(
                        NotificationChannel.DINGTALK,
                        self.dingtalk_webhook,
                        message.title,
                        False,
                        error_msg
                    )
                    return False

        except httpx.ConnectError:
            error_msg = "Cannot connect to DingTalk webhook"
            logger.error(error_msg)
            self._log_notification(
                NotificationChannel.DINGTALK,
                self.dingtalk_webhook,
                message.title,
                False,
                error_msg
            )
            return False
        except Exception as e:
            error_msg = str(e)
            logger.error(f"DingTalk notification error: {error_msg}")
            self._log_notification(
                NotificationChannel.DINGTALK,
                self.dingtalk_webhook or "unknown",
                message.title,
                False,
                error_msg
            )
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
        import uuid
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        if not self.smtp_host or not self.smtp_user:
            logger.warning("SMTP not configured")
            self._log_notification(
                NotificationChannel.EMAIL,
                ", ".join(recipients),
                message.title,
                False,
                "SMTP not configured (missing host or user)"
            )
            return False

        try:
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

            # HTML body
            html_body = f"""
            <html>
            <body>
                <h2 style="color: {self._get_severity_color(message.severity)}">
                    [{message.severity.upper()}] {message.title}
                </h2>
                <p>{message.content}</p>
            """
            if message.details:
                html_body += "<h3>Details:</h3><ul>"
                for key, value in message.details.items():
                    html_body += f"<li><strong>{key}</strong>: {value}</li>"
                html_body += "</ul>"
            html_body += f"""
                <p><small>Time: {datetime.utcnow().isoformat()}</small></p>
            </body>
            </html>
            """
            msg.attach(MIMEText(html_body, "html"))

            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.smtp_use_tls:
                    server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(
                    self.email_from or self.smtp_user,
                    recipients,
                    msg.as_string()
                )

            logger.info(f"Email notification sent to {len(recipients)} recipients")
            self._log_notification(
                NotificationChannel.EMAIL,
                ", ".join(recipients),
                message.title,
                True
            )
            return True

        except smtplib.SMTPAuthenticationError as e:
            error_msg = f"SMTP authentication failed: {e}"
            logger.error(error_msg)
            self._log_notification(
                NotificationChannel.EMAIL,
                ", ".join(recipients),
                message.title,
                False,
                error_msg
            )
            return False
        except smtplib.SMTPException as e:
            error_msg = f"SMTP error: {e}"
            logger.error(error_msg)
            self._log_notification(
                NotificationChannel.EMAIL,
                ", ".join(recipients),
                message.title,
                False,
                error_msg
            )
            return False
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Email notification error: {error_msg}")
            self._log_notification(
                NotificationChannel.EMAIL,
                ", ".join(recipients),
                message.title,
                False,
                error_msg
            )
            return False

    def _get_severity_color(self, severity: str) -> str:
        """Get HTML color for severity level"""
        colors = {
            "info": "#3b82f6",      # blue
            "warning": "#f59e0b",   # yellow/orange
            "error": "#ef4444",     # red
            "critical": "#dc2626",  # dark red
        }
        return colors.get(severity, "#3b82f6")

    def _log_notification(
        self,
        channel: NotificationChannel,
        recipient: str,
        title: str,
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        """Log notification attempt"""
        import uuid

        log_entry = NotificationLog(
            id=str(uuid.uuid4()),
            channel=channel,
            recipient=recipient,
            title=title,
            success=success,
            error_message=error_message,
            timestamp=datetime.utcnow(),
        )
        _notification_logs.append(log_entry)

        # Keep only last 1000 logs
        if len(_notification_logs) > 1000:
            _notification_logs.pop(0)

    def get_logs(
        self,
        channel: Optional[NotificationChannel] = None,
        success_only: bool = False,
        limit: int = 100,
    ) -> List[NotificationLog]:
        """Get notification logs

        Args:
            channel: Filter by channel
            success_only: Only return successful notifications
            limit: Maximum number of logs to return

        Returns:
            List of notification logs
        """
        logs = _notification_logs

        if channel:
            logs = [l for l in logs if l.channel == channel]
        if success_only:
            logs = [l for l in logs if l.success]

        # Sort by timestamp descending
        logs = sorted(logs, key=lambda l: l.timestamp, reverse=True)
        return logs[:limit]


# Create default instance from environment
notification_service = NotificationService(
    feishu_webhook=os.getenv("FEISHU_WEBHOOK_URL"),
    dingtalk_webhook=os.getenv("DINGTALK_WEBHOOK_URL"),
    smtp_host=os.getenv("SMTP_HOST"),
    smtp_port=int(os.getenv("SMTP_PORT", "587")),
    smtp_user=os.getenv("SMTP_USER"),
    smtp_password=os.getenv("SMTP_PASSWORD"),
    email_from=os.getenv("EMAIL_FROM"),
    smtp_use_tls=os.getenv("SMTP_USE_TLS", "true").lower() == "true",
)
