"""User-Agent binding and daily summary API routes."""

import uuid
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import get_current_user
from app.database import get_db
from app.models.agent import Agent
from app.models.user import User
from app.models.user_agent_binding import DailySummary, UserAgentBinding
from app.models.org import OrgMember, OrgDepartment

router = APIRouter(prefix="/bindings", tags=["bindings"])


# ─── Schemas ───────────────────────────────────────────

class BindingCreate(BaseModel):
    agent_id: uuid.UUID
    org_role: str = "member"  # "leader" | "member"


class BindingUpdate(BaseModel):
    org_role: str | None = None  # "leader" | "member"
    department_id: uuid.UUID | None = None


class BindingOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    agent_id: uuid.UUID
    department_id: uuid.UUID | None = None
    department_name: str | None = None
    org_role: str = "member"
    is_active: bool
    created_at: datetime
    agent_name: str | None = None
    agent_avatar: str | None = None
    agent_role: str | None = None
    agent_status: str | None = None

    model_config = {"from_attributes": True}


class DailySummaryOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    summary_date: date
    content: str
    agent_details: dict
    total_tasks_completed: int
    total_messages: int
    total_tokens_used: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Bindings CRUD ─────────────────────────────────────

@router.get("/", response_model=list[BindingOut])
async def list_my_bindings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all agent bindings for the current user."""
    result = await db.execute(
        select(UserAgentBinding)
        .where(UserAgentBinding.user_id == current_user.id)
        .options(
            selectinload(UserAgentBinding.agent),
            selectinload(UserAgentBinding.department),
        )
        .order_by(UserAgentBinding.created_at.desc())
    )
    bindings = result.scalars().all()
    return [
        BindingOut(
            id=b.id,
            user_id=b.user_id,
            agent_id=b.agent_id,
            department_id=b.department_id,
            department_name=b.department.name if b.department else None,
            org_role=b.org_role,
            is_active=b.is_active,
            created_at=b.created_at,
            agent_name=b.agent.name if b.agent else None,
            agent_avatar=b.agent.avatar_url if b.agent else None,
            agent_role=b.agent.role_description if b.agent else None,
            agent_status=b.agent.status if b.agent else None,
        )
        for b in bindings
    ]


@router.get("/user/{user_id}", response_model=list[BindingOut])
async def list_user_bindings(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all agent bindings for a specific user (admin or self)."""
    if current_user.id != user_id and current_user.role not in ("platform_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Not authorized")
    result = await db.execute(
        select(UserAgentBinding)
        .where(UserAgentBinding.user_id == user_id)
        .options(
            selectinload(UserAgentBinding.agent),
            selectinload(UserAgentBinding.department),
        )
        .order_by(UserAgentBinding.created_at.desc())
    )
    bindings = result.scalars().all()
    return [
        BindingOut(
            id=b.id,
            user_id=b.user_id,
            agent_id=b.agent_id,
            department_id=b.department_id,
            department_name=b.department.name if b.department else None,
            org_role=b.org_role,
            is_active=b.is_active,
            created_at=b.created_at,
            agent_name=b.agent.name if b.agent else None,
            agent_avatar=b.agent.avatar_url if b.agent else None,
            agent_role=b.agent.role_description if b.agent else None,
            agent_status=b.agent.status if b.agent else None,
        )
        for b in bindings
    ]


@router.post("/", response_model=BindingOut, status_code=status.HTTP_201_CREATED)
async def create_binding(
    data: BindingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bind an agent to the current user. The agent inherits user's department."""
    # Check agent exists
    agent_result = await db.execute(select(Agent).where(Agent.id == data.agent_id))
    agent = agent_result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Check duplicate
    existing = await db.execute(
        select(UserAgentBinding).where(
            UserAgentBinding.user_id == current_user.id,
            UserAgentBinding.agent_id == data.agent_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Binding already exists")

    # Find user's department from org_members via feishu_open_id
    department_id = None
    department_name = None
    if current_user.feishu_open_id:
        member_result = await db.execute(
            select(OrgMember)
            .where(OrgMember.feishu_open_id == current_user.feishu_open_id)
            .options(selectinload(OrgMember.department))
        )
        org_member = member_result.scalar_one_or_none()
        if org_member and org_member.department_id:
            department_id = org_member.department_id
            department_name = org_member.department.name if org_member.department else None

    binding = UserAgentBinding(
        user_id=current_user.id,
        agent_id=data.agent_id,
        department_id=department_id,
        org_role=data.org_role,
    )
    db.add(binding)
    await db.flush()
    return BindingOut(
        id=binding.id,
        user_id=binding.user_id,
        agent_id=binding.agent_id,
        department_id=department_id,
        department_name=department_name,
        org_role=binding.org_role,
        is_active=binding.is_active,
        created_at=binding.created_at,
        agent_name=agent.name,
        agent_avatar=agent.avatar_url,
        agent_role=agent.role_description,
        agent_status=agent.status,
    )


@router.delete("/{binding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_binding(
    binding_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove an agent binding."""
    result = await db.execute(
        select(UserAgentBinding).where(
            UserAgentBinding.id == binding_id,
            UserAgentBinding.user_id == current_user.id,
        )
    )
    binding = result.scalar_one_or_none()
    if not binding:
        raise HTTPException(status_code=404, detail="Binding not found")
    await db.delete(binding)


@router.patch("/{binding_id}/toggle")
async def toggle_binding(
    binding_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle a binding active/inactive."""
    result = await db.execute(
        select(UserAgentBinding).where(
            UserAgentBinding.id == binding_id,
            UserAgentBinding.user_id == current_user.id,
        )
    )
    binding = result.scalar_one_or_none()
    if not binding:
        raise HTTPException(status_code=404, detail="Binding not found")
    binding.is_active = not binding.is_active
    await db.flush()
    return {"is_active": binding.is_active}


@router.patch("/{binding_id}")
async def update_binding(
    binding_id: uuid.UUID,
    data: BindingUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a binding's org_role or department. Admin can update any, user only their own."""
    is_admin = current_user.role in ("platform_admin", "org_admin")
    query = select(UserAgentBinding).where(UserAgentBinding.id == binding_id)
    if not is_admin:
        query = query.where(UserAgentBinding.user_id == current_user.id)
    result = await db.execute(query)
    binding = result.scalar_one_or_none()
    if not binding:
        raise HTTPException(status_code=404, detail="Binding not found")
    
    if data.org_role is not None:
        if data.org_role not in ("leader", "member"):
            raise HTTPException(status_code=400, detail="org_role must be 'leader' or 'member'")
        binding.org_role = data.org_role
    if data.department_id is not None:
        binding.department_id = data.department_id
    
    await db.flush()
    return {
        "id": str(binding.id),
        "org_role": binding.org_role,
        "department_id": str(binding.department_id) if binding.department_id else None,
    }


# ─── Organization Chart with Digital Employees ─────────

@router.get("/org-chart")
async def get_org_chart_with_agents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get organization chart data including bound digital employees per department."""
    # Get all departments synced from Feishu
    dept_result = await db.execute(
        select(OrgDepartment)
        .where(OrgDepartment.tenant_id == current_user.tenant_id)
        .order_by(OrgDepartment.path)
    )
    departments = dept_result.scalars().all()

    # Get all bindings with department info
    bindings_result = await db.execute(
        select(UserAgentBinding)
        .options(
            selectinload(UserAgentBinding.agent),
            selectinload(UserAgentBinding.user),
            selectinload(UserAgentBinding.department),
        )
    )
    bindings = bindings_result.scalars().all()

    # Group bindings by department
    dept_agents: dict[str, list[dict]] = {}
    for b in bindings:
        dept_id = str(b.department_id) if b.department_id else "unassigned"
        if dept_id not in dept_agents:
            dept_agents[dept_id] = []
        dept_agents[dept_id].append({
            "binding_id": str(b.id),
            "agent_id": str(b.agent_id),
            "agent_name": b.agent.name if b.agent else None,
            "agent_avatar": b.agent.avatar_url if b.agent else None,
            "agent_status": b.agent.status if b.agent else None,
            "user_id": str(b.user_id),
            "user_name": b.user.display_name if b.user else None,
            "org_role": b.org_role,  # "leader" or "member"
            "is_active": b.is_active,
        })

    # Build response
    result = []
    for d in departments:
        result.append({
            "id": str(d.id),
            "name": d.name,
            "parent_id": str(d.parent_id) if d.parent_id else None,
            "path": d.path,
            "member_count": d.member_count,
            "digital_employees": dept_agents.get(str(d.id), []),
        })

    # Add unassigned agents
    if "unassigned" in dept_agents:
        result.append({
            "id": "unassigned",
            "name": "未分配部门",
            "parent_id": None,
            "path": "",
            "member_count": 0,
            "digital_employees": dept_agents["unassigned"],
        })

    return result


# ─── Daily Summaries ───────────────────────────────────

@router.get("/summaries", response_model=list[DailySummaryOut])
async def list_daily_summaries(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List daily summaries for the current user."""
    query = select(DailySummary).where(DailySummary.user_id == current_user.id)
    if start_date:
        query = query.where(DailySummary.summary_date >= start_date)
    if end_date:
        query = query.where(DailySummary.summary_date <= end_date)
    query = query.order_by(DailySummary.summary_date.desc()).limit(30)
    result = await db.execute(query)
    return [DailySummaryOut.model_validate(s) for s in result.scalars().all()]


@router.get("/summaries/{summary_date}", response_model=DailySummaryOut)
async def get_daily_summary(
    summary_date: date,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get daily summary for a specific date."""
    result = await db.execute(
        select(DailySummary).where(
            DailySummary.user_id == current_user.id,
            DailySummary.summary_date == summary_date,
        )
    )
    summary = result.scalar_one_or_none()
    if not summary:
        raise HTTPException(status_code=404, detail="No summary for this date")
    return DailySummaryOut.model_validate(summary)


@router.post("/summaries/generate")
async def generate_daily_summary(
    target_date: date | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger daily summary generation for a specific date (defaults to today)."""
    from app.services.daily_summary_service import generate_summary_for_user
    summary_date = target_date or date.today()
    summary = await generate_summary_for_user(db, current_user.id, summary_date)
    return DailySummaryOut.model_validate(summary)
