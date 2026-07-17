"""
Newsletter admin endpoints — every route here requires require_admin, which
checks the logged-in user's email against settings.ADMIN_EMAIL. Drafts are
AI-generated on demand but never sent without an explicit approve call.

POST /api/v1/admin/newsletter/generate            — create a new draft
GET  /api/v1/admin/newsletter/drafts               — list all issues
GET  /api/v1/admin/newsletter/{id}                 — one issue
PATCH /api/v1/admin/newsletter/{id}                — edit subject/content before sending
POST /api/v1/admin/newsletter/{id}/approve_and_send — send to every subscribed, verified user
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session

from auth.dependencies import require_admin
from db.database import get_db
from db.models import User, NewsletterIssue
from newsletter.generator import generate_draft
from notifications.mailer import send_email

logger = logging.getLogger(__name__)
router = APIRouter()


def _serialize(issue: NewsletterIssue) -> dict:
    return {
        "id": issue.id,
        "week_label": issue.week_label,
        "subject": issue.subject,
        "content_html": issue.content_html,
        "status": issue.status,
        "generated_at": issue.generated_at.isoformat() if issue.generated_at else None,
        "approved_by": issue.approved_by,
        "approved_at": issue.approved_at.isoformat() if issue.approved_at else None,
        "sent_at": issue.sent_at.isoformat() if issue.sent_at else None,
        "recipient_count": issue.recipient_count,
    }


@router.post("/admin/newsletter/generate")
async def generate(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    issue = generate_draft(db)
    return _serialize(issue)


@router.get("/admin/newsletter/drafts")
async def list_drafts(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    issues = db.query(NewsletterIssue).order_by(NewsletterIssue.generated_at.desc()).all()
    return [_serialize(i) for i in issues]


@router.get("/admin/newsletter/{issue_id}")
async def get_draft(issue_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    issue = db.query(NewsletterIssue).filter(NewsletterIssue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Newsletter issue not found.")
    return _serialize(issue)


class EditRequest(BaseModel):
    subject: Optional[str] = None
    content_html: Optional[str] = None


@router.patch("/admin/newsletter/{issue_id}")
async def edit_draft(
    issue_id: int, req: EditRequest,
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    issue = db.query(NewsletterIssue).filter(NewsletterIssue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Newsletter issue not found.")
    if issue.status != "draft":
        raise HTTPException(status_code=400, detail=f"Issue is already {issue.status} — can't edit.")

    if req.subject is not None:
        issue.subject = req.subject
    if req.content_html is not None:
        issue.content_html = req.content_html
    db.commit()
    db.refresh(issue)
    return _serialize(issue)


@router.post("/admin/newsletter/{issue_id}/approve_and_send")
async def approve_and_send(
    issue_id: int,
    admin: User = Depends(require_admin), db: Session = Depends(get_db),
):
    issue = db.query(NewsletterIssue).filter(NewsletterIssue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Newsletter issue not found.")
    if issue.status == "sent":
        raise HTTPException(status_code=400, detail="Already sent.")

    recipients = (
        db.query(User)
        .filter(User.is_verified == True, User.newsletter_subscribed == True)  # noqa: E712
        .all()
    )

    sent_count = 0
    for u in recipients:
        if send_email(u.email, issue.subject, issue.content_html):
            sent_count += 1

    issue.status = "sent"
    issue.approved_by = admin.email
    issue.approved_at = datetime.now(timezone.utc)
    issue.sent_at = datetime.now(timezone.utc)
    issue.recipient_count = sent_count
    db.commit()
    db.refresh(issue)

    logger.info(f"Newsletter #{issue.id} approved by {admin.email}, sent to {sent_count}/{len(recipients)} recipients")
    return _serialize(issue)
