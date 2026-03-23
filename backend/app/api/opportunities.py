"""Business Opportunity (商机) API routes."""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import get_current_user
from app.database import get_db
from app.models.opportunity import Opportunity, OpportunityLog
from app.models.user import User

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


# ─── Schemas ───────────────────────────────────────────

class OpportunityCreate(BaseModel):
    customer_name: str
    visit_date: Optional[str] = None       # ISO datetime or YYYY-MM-DD
    solution: Optional[str] = None
    project_duration: Optional[str] = None
    project_scale: Optional[str] = None
    visit_summary: Optional[str] = None
    contact_person: Optional[str] = None
    contact_info: Optional[str] = None
    stage: str = "initial_contact"
    priority: str = "medium"
    estimated_amount: Optional[float] = None
    currency: str = "CNY"
    win_probability: Optional[int] = None
    next_action: Optional[str] = None
    next_action_date: Optional[str] = None
    risk_flag: Optional[str] = None
    risk_note: Optional[str] = None
    tags: Optional[list[str]] = None
    extra_data: Optional[dict] = None
    raw_input: Optional[str] = None


class OpportunityUpdate(BaseModel):
    customer_name: Optional[str] = None
    visit_date: Optional[str] = None
    solution: Optional[str] = None
    project_duration: Optional[str] = None
    project_scale: Optional[str] = None
    visit_summary: Optional[str] = None
    contact_person: Optional[str] = None
    contact_info: Optional[str] = None
    stage: Optional[str] = None
    priority: Optional[str] = None
    estimated_amount: Optional[float] = None
    currency: Optional[str] = None
    win_probability: Optional[int] = None
    next_action: Optional[str] = None
    next_action_date: Optional[str] = None
    risk_flag: Optional[str] = None
    risk_note: Optional[str] = None
    tags: Optional[list[str]] = None
    extra_data: Optional[dict] = None


class OpportunityLogCreate(BaseModel):
    log_type: str = "note"   # stage_change / follow_up / risk_alert / note
    content: str


# ─── Helpers ───────────────────────────────────────────

def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _serialize_opportunity(opp: Opportunity) -> dict:
    d = object.__getattribute__(opp, "__dict__")

    def _rel(name):
        val = d.get(name)
        if val is None:
            return None
        if hasattr(val, "__tablename__"):
            return val
        return None

    agent = _rel("created_by_agent")
    user = _rel("created_by_user")

    return {
        "id": str(opp.id),
        "customer_name": opp.customer_name,
        "visit_date": opp.visit_date.isoformat() if opp.visit_date else None,
        "solution": opp.solution,
        "project_duration": opp.project_duration,
        "project_scale": opp.project_scale,
        "visit_summary": opp.visit_summary,
        "contact_person": opp.contact_person,
        "contact_info": opp.contact_info,
        "stage": opp.stage,
        "priority": opp.priority,
        "estimated_amount": float(opp.estimated_amount) if opp.estimated_amount is not None else None,
        "currency": opp.currency,
        "win_probability": opp.win_probability,
        "next_action": opp.next_action,
        "next_action_date": opp.next_action_date.isoformat() if opp.next_action_date else None,
        "risk_flag": opp.risk_flag,
        "risk_note": opp.risk_note,
        "tags": opp.tags or [],
        "extra_data": opp.extra_data or {},
        "raw_input": opp.raw_input,
        "created_by_agent_id": str(opp.created_by_agent_id) if opp.created_by_agent_id else None,
        "created_by_agent_name": agent.name if agent else None,
        "created_by_user_id": str(opp.created_by_user_id) if opp.created_by_user_id else None,
        "created_by_user_name": user.display_name if user else None,
        "created_at": opp.created_at.isoformat() if opp.created_at else None,
        "updated_at": opp.updated_at.isoformat() if opp.updated_at else None,
    }


STAGE_LABELS = {
    "initial_contact": "初步接触",
    "demand_confirmed": "需求确认",
    "proposal": "方案报价",
    "negotiation": "商务谈判",
    "won": "赢单",
    "lost": "输单",
}


# ─── CRUD ──────────────────────────────────────────────

@router.get("/")
async def list_opportunities(
    search: Optional[str] = None,
    stage: Optional[str] = None,
    priority: Optional[str] = None,
    risk_flag: Optional[str] = None,
    agent_id: Optional[str] = None,
    sort_by: Optional[str] = "created_at",
    sort_dir: Optional[str] = "desc",
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List opportunities with filters. All users in the same tenant share the table."""
    query = select(Opportunity).where(
        Opportunity.tenant_id == current_user.tenant_id,
    )

    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(
                Opportunity.customer_name.ilike(pattern),
                Opportunity.solution.ilike(pattern),
                Opportunity.visit_summary.ilike(pattern),
                Opportunity.contact_person.ilike(pattern),
            )
        )
    if stage:
        query = query.where(Opportunity.stage == stage)
    if priority:
        query = query.where(Opportunity.priority == priority)
    if risk_flag:
        query = query.where(Opportunity.risk_flag == risk_flag)
    if agent_id:
        query = query.where(Opportunity.created_by_agent_id == uuid.UUID(agent_id))

    # Sorting — whitelist allowed columns
    _ALLOWED_SORT = {"created_at", "updated_at", "customer_name", "visit_date", "estimated_amount", "stage", "priority"}
    col_name = sort_by if sort_by in _ALLOWED_SORT else "created_at"
    col = getattr(Opportunity, col_name)
    query = query.order_by(desc(col) if sort_dir == "desc" else col)

    # Total count
    count_q = select(func.count()).select_from(
        query.with_only_columns(Opportunity.id).subquery()
    )
    total = (await db.execute(count_q)).scalar_one()

    query = query.options(
        selectinload(Opportunity.created_by_agent),
        selectinload(Opportunity.created_by_user),
    ).offset(offset).limit(limit)

    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "items": [_serialize_opportunity(o) for o in items],
        "total": total,
        "stages": STAGE_LABELS,
    }


@router.get("/stats")
async def opportunity_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate stats for the dashboard."""
    base = select(Opportunity).where(Opportunity.tenant_id == current_user.tenant_id)

    # Count by stage
    stage_q = (
        select(Opportunity.stage, func.count(Opportunity.id))
        .where(Opportunity.tenant_id == current_user.tenant_id)
        .group_by(Opportunity.stage)
    )
    stage_rows = (await db.execute(stage_q)).fetchall()
    by_stage = {row[0]: row[1] for row in stage_rows}

    # Total estimated amount
    amount_q = (
        select(func.sum(Opportunity.estimated_amount))
        .where(Opportunity.tenant_id == current_user.tenant_id)
    )
    total_amount = (await db.execute(amount_q)).scalar_one() or 0

    # Risk counts
    risk_q = (
        select(Opportunity.risk_flag, func.count(Opportunity.id))
        .where(
            Opportunity.tenant_id == current_user.tenant_id,
            Opportunity.risk_flag.isnot(None),
            Opportunity.risk_flag != "none",
        )
        .group_by(Opportunity.risk_flag)
    )
    risk_rows = (await db.execute(risk_q)).fetchall()
    by_risk = {row[0]: row[1] for row in risk_rows}

    total_q = select(func.count(Opportunity.id)).where(Opportunity.tenant_id == current_user.tenant_id)
    total = (await db.execute(total_q)).scalar_one()

    return {
        "total": total,
        "by_stage": by_stage,
        "total_estimated_amount": float(total_amount),
        "by_risk": by_risk,
        "stages": STAGE_LABELS,
    }


@router.get("/{opp_id}")
async def get_opportunity(
    opp_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Opportunity)
        .where(Opportunity.id == opp_id)
        .options(
            selectinload(Opportunity.created_by_agent),
            selectinload(Opportunity.created_by_user),
        )
    )
    opp = result.scalar_one_or_none()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    if opp.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="No permission")
    return _serialize_opportunity(opp)


@router.post("/", status_code=201)
async def create_opportunity(
    data: OpportunityCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    opp = Opportunity(
        customer_name=data.customer_name,
        visit_date=_parse_datetime(data.visit_date),
        solution=data.solution,
        project_duration=data.project_duration,
        project_scale=data.project_scale,
        visit_summary=data.visit_summary,
        contact_person=data.contact_person,
        contact_info=data.contact_info,
        stage=data.stage,
        priority=data.priority,
        estimated_amount=data.estimated_amount,
        currency=data.currency,
        win_probability=data.win_probability,
        next_action=data.next_action,
        next_action_date=_parse_datetime(data.next_action_date),
        risk_flag=data.risk_flag,
        risk_note=data.risk_note,
        tags=data.tags or [],
        extra_data=data.extra_data or {},
        raw_input=data.raw_input,
        created_by_user_id=current_user.id,
        tenant_id=current_user.tenant_id,
    )
    db.add(opp)
    await db.flush()

    log = OpportunityLog(
        opportunity_id=opp.id,
        log_type="stage_change",
        content=f"商机创建：{data.customer_name}",
        created_by_user_id=current_user.id,
    )
    db.add(log)

    await db.flush()
    await db.commit()

    # Reload with relationships
    result = await db.execute(
        select(Opportunity).where(Opportunity.id == opp.id).options(
            selectinload(Opportunity.created_by_agent),
            selectinload(Opportunity.created_by_user),
        )
    )
    opp = result.scalar_one()
    return _serialize_opportunity(opp)


@router.patch("/{opp_id}")
async def update_opportunity(
    opp_id: uuid.UUID,
    data: OpportunityUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Opportunity).where(Opportunity.id == opp_id))
    opp = result.scalar_one_or_none()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    if opp.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="No permission")

    old_stage = opp.stage
    update_fields = data.model_dump(exclude_unset=True)

    # Handle date string → datetime conversion
    for date_field in ("visit_date", "next_action_date"):
        if date_field in update_fields:
            update_fields[date_field] = _parse_datetime(update_fields[date_field])

    for field, value in update_fields.items():
        setattr(opp, field, value)

    # Log stage change
    if data.stage and data.stage != old_stage:
        old_label = STAGE_LABELS.get(old_stage, old_stage)
        new_label = STAGE_LABELS.get(data.stage, data.stage)
        log = OpportunityLog(
            opportunity_id=opp.id,
            log_type="stage_change",
            content=f"阶段变更：{old_label} → {new_label}",
            created_by_user_id=current_user.id,
        )
        db.add(log)

    await db.commit()

    result = await db.execute(
        select(Opportunity).where(Opportunity.id == opp.id).options(
            selectinload(Opportunity.created_by_agent),
            selectinload(Opportunity.created_by_user),
        )
    )
    opp = result.scalar_one()
    return _serialize_opportunity(opp)


@router.delete("/{opp_id}", status_code=204)
async def delete_opportunity(
    opp_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Opportunity).where(Opportunity.id == opp_id))
    opp = result.scalar_one_or_none()
    if not opp:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    if opp.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="No permission")
    # Only admin or creator can delete
    if current_user.role not in ("platform_admin", "org_admin") and opp.created_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only admin or creator can delete")
    await db.delete(opp)
    await db.commit()


# ─── Logs ──────────────────────────────────────────────

@router.get("/{opp_id}/logs")
async def list_opportunity_logs(
    opp_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify access
    opp_r = await db.execute(select(Opportunity).where(Opportunity.id == opp_id))
    opp = opp_r.scalar_one_or_none()
    if not opp or opp.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Not found")

    result = await db.execute(
        select(OpportunityLog)
        .where(OpportunityLog.opportunity_id == opp_id)
        .order_by(OpportunityLog.created_at.desc())
    )
    logs = result.scalars().all()
    return [
        {
            "id": str(l.id),
            "log_type": l.log_type,
            "content": l.content,
            "extra_data": l.extra_data,
            "created_by_agent_id": str(l.created_by_agent_id) if l.created_by_agent_id else None,
            "created_by_user_id": str(l.created_by_user_id) if l.created_by_user_id else None,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]


@router.post("/{opp_id}/logs")
async def add_opportunity_log(
    opp_id: uuid.UUID,
    data: OpportunityLogCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    opp_r = await db.execute(select(Opportunity).where(Opportunity.id == opp_id))
    opp = opp_r.scalar_one_or_none()
    if not opp or opp.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Not found")

    log = OpportunityLog(
        opportunity_id=opp_id,
        log_type=data.log_type,
        content=data.content,
        created_by_user_id=current_user.id,
    )
    db.add(log)
    await db.commit()
    return {
        "id": str(log.id),
        "log_type": log.log_type,
        "content": log.content,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }
