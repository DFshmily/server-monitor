"""Email sending via SMTP (used for registration verification codes)."""
import logging
import smtplib
import ssl
from email.mime.text import MIMEText
from email.header import Header

from app.core.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM

logger = logging.getLogger(__name__)


def send_email(to_addr: str, subject: str, html_body: str) -> bool:
    """Send an HTML email via SMTP. Returns True on success."""
    if not SMTP_USER or not SMTP_PASS:
        logger.warning("SMTP not configured: MONITOR_SMTP_USER / MONITOR_SMTP_PASS missing")
        return False

    msg = MIMEText(html_body, "html", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = SMTP_FROM or SMTP_USER
    msg["To"] = to_addr

    try:
        if SMTP_PORT == 465:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=15) as s:
                s.login(SMTP_USER, SMTP_PASS)
                s.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
                s.starttls()
                s.login(SMTP_USER, SMTP_PASS)
                s.send_message(msg)
        logger.info("Email sent to %s: %s", to_addr, subject)
        return True
    except Exception as e:
        logger.error("Email send failed to %s: %s", to_addr, e)
        return False


def send_verification_code(to_addr: str, code: str) -> bool:
    subject = "【DFshmily 监控】注册验证码"
    html = f"""
    <div style="font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;
                max-width:480px;margin:0 auto;padding:32px 24px;
                background:#f5f5f7;border-radius:16px;">
      <div style="background:#fff;border-radius:12px;padding:32px 24px;
                  box-shadow:0 4px 16px rgba(0,0,0,.06);">
        <h2 style="margin:0 0 8px;color:#1d1d1f;font-size:20px;">DFshmily の🌐 注册验证</h2>
        <p style="color:#6e6e73;font-size:14px;line-height:1.6;">你好!你正在注册 DFshmily 服务器监控。请在注册页面输入以下验证码完成验证:</p>
        <div style="text-align:center;margin:24px 0;">
          <span style="display:inline-block;background:#f5f3ff;color:#7c3aed;
                       font-size:28px;font-weight:700;letter-spacing:8px;
                       padding:12px 24px;border-radius:12px;">{code}</span>
        </div>
        <p style="color:#aeaeb2;font-size:12px;line-height:1.6;">
          验证码 10 分钟内有效。如果这不是你本人操作,请忽略本邮件。<br/>
          —— DFshmily 服务器监控
        </p>
      </div>
    </div>
    """
    return send_email(to_addr, subject, html)
