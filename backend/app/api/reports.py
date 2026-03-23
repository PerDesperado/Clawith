"""Daily Reports API - Hierarchical report viewing and consolidation.

Permission-based access control:
- platform_admin: Can view all reports
- GM: Can view reports for centers they manage
- Director: Can view reports for teams they manage
- Leader/Deputy Leader: Can view reports for their team
- Member: Can only view their own report
"""

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import get_current_user
from app.database import get_db
from app.models.agent import Agent
from app.models.org import AgentRelationship, OrgMember
from app.models.team_task import AgentDailyReport
from app.models.user import User
from app.models.user_agent_binding import UserAgentBinding
from app.services.report_hierarchy_service import (
    get_team_hierarchy,
    get_team_reports_for_leader,
    generate_consolidated_report,
    get_agents_reporting_to_me,
    get_my_leader,
    can_view_report,
    get_agent_report,
    get_leader_with_members,
)
from app.services.agent_report_service import generate_agent_report
from app.services.org_permission_service import (
    get_viewable_scope,
    get_filtered_hierarchy,
    can_view_agent,
)

router = APIRouter(prefix="/reports", tags=["reports"])


# ─── Schemas ───────────────────────────────────────────

class AgentReportOut(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: str | None = None
    report_date: date
    summary: str | None
    completed_tasks: list = []
    in_progress_tasks: list = []
    planned_tasks: list = []
    blockers: list = []
    highlights: list = []
    tasks_completed_count: int = 0
    tasks_in_progress_count: int = 0
    messages_sent: int = 0
    tokens_used: int = 0
    report_status: str = "draft"
    is_auto_generated: bool = True

    model_config = {"from_attributes": True}


# ─── Helper: Check if agent is a leader ────────────────

async def _is_agent_leader(db: AsyncSession, agent_id: uuid.UUID) -> bool:
    """Check if an agent is linked to a leader org member."""
    result = await db.execute(
        select(AgentRelationship)
        .options(selectinload(AgentRelationship.member))
        .where(AgentRelationship.agent_id == agent_id)
    )
    rel = result.scalar_one_or_none()
    if not rel or not rel.member:
        return False
    return rel.member.title.lower() in ("leader", "组长", "主管", "经理", "总监")


async def _user_owns_agent(db: AsyncSession, user_id: uuid.UUID, agent_id: uuid.UUID) -> bool:
    """Check if user owns this agent through binding."""
    result = await db.execute(
        select(UserAgentBinding).where(
            UserAgentBinding.user_id == user_id,
            UserAgentBinding.agent_id == agent_id,
        )
    )
    return result.scalar_one_or_none() is not None


# ─── Team Hierarchy ────────────────────────────────────

@router.get("/hierarchy")
async def get_report_hierarchy(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the organization hierarchy filtered by current user's permissions.
    
    Access control:
    - platform_admin: Returns all departments -> centers -> teams
    - GM: Returns only centers they manage and teams under them
    - Director: Returns only teams they manage
    - Leader/Deputy Leader: Returns only their team
    - Member: Returns only their team (but can only see their own reports)
    
    Returns new hierarchy structure:
    {
        "departments": [
            {
                "id": "...",
                "name": "云产品一部",
                "centers": [
                    {
                        "id": "...",
                        "name": "计算中心",
                        "teams": [
                            {
                                "id": "...",
                                "name": "CVM组",
                                "leaders": [...],
                                "members": [...]
                            }
                        ]
                    }
                ]
            }
        ],
        "user_role": "leader",  // Current user's role
        "scope": "team"  // What level the user can see: "all", "department", "center", "team", "self"
    }
    """
    # Get user's viewable scope
    scope = await get_viewable_scope(db, current_user, current_user.tenant_id)
    
    # Get filtered hierarchy
    hierarchy = await get_filtered_hierarchy(db, current_user, current_user.tenant_id)
    
    # Determine scope description
    if scope.view_all:
        scope_level = "all"
    elif scope.user_role == "gm":
        scope_level = "center"
    elif scope.user_role == "director":
        scope_level = "team"
    elif scope.user_role in ("leader", "deputy_leader"):
        scope_level = "team"
    else:
        scope_level = "self"
    
    return {
        **hierarchy,
        "user_role": scope.user_role,
        "scope": scope_level,
    }


@router.get("/hierarchy/legacy")
async def get_report_hierarchy_legacy(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Legacy endpoint - Get the team hierarchy showing leader-member relationships.
    Based on agent_relationships -> org_members structure.
    
    DEPRECATED: Use /hierarchy instead which supports new org structure.
    """
    hierarchy = await get_team_hierarchy(db, current_user.tenant_id)
    return hierarchy


# ─── My Team's Reports (For Leaders) ───────────────────

@router.get("/my-team")
async def get_my_team_reports(
    agent_id: uuid.UUID = Query(..., description="The leader agent ID"),
    report_date: date = Query(default=None, description="Date for reports (defaults to today)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all team member reports for a leader.
    
    The leader agent (linked to org member with title="leader") can see:
    - Their own daily report
    - All team members' daily reports in the same department
    """
    # Verify the user owns this agent
    owns_agent = await _user_owns_agent(db, current_user.id, agent_id)
    is_leader = await _is_agent_leader(db, agent_id)
    is_admin = current_user.role in ("platform_admin", "org_admin")
    
    if not owns_agent and not is_admin:
        raise HTTPException(status_code=403, detail="You don't own this agent")
    
    if not is_leader and not is_admin:
        raise HTTPException(status_code=403, detail="This agent is not a leader")
    
    target_date = report_date or date.today()
    team_reports = await get_team_reports_for_leader(db, agent_id, target_date)
    
    if "error" in team_reports:
        raise HTTPException(status_code=404, detail=team_reports["error"])
    
    return team_reports


@router.get("/my-team/consolidated")
async def get_consolidated_report(
    agent_id: uuid.UUID = Query(..., description="The leader agent ID"),
    report_date: date = Query(default=None, description="Date for reports (defaults to today)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a consolidated report for a leader.
    
    This combines:
    - Leader's own work summary
    - All team members' summaries
    - Aggregated statistics
    
    This is what the leader would send to their upper-level leader.
    """
    # Verify the user owns this agent
    owns_agent = await _user_owns_agent(db, current_user.id, agent_id)
    is_leader = await _is_agent_leader(db, agent_id)
    is_admin = current_user.role in ("platform_admin", "org_admin")
    
    if not owns_agent and not is_admin:
        raise HTTPException(status_code=403, detail="You don't own this agent")
    
    if not is_leader and not is_admin:
        raise HTTPException(status_code=403, detail="This agent is not a leader")
    
    target_date = report_date or date.today()
    consolidated = await generate_consolidated_report(db, agent_id, target_date)
    
    if "error" in consolidated:
        raise HTTPException(status_code=404, detail=consolidated["error"])
    
    return consolidated


# ─── Individual Agent Reports ──────────────────────────

@router.get("/agent/{agent_id}")
async def get_agent_daily_report(
    agent_id: uuid.UUID,
    report_date: date = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a specific agent's daily report.
    
    Access rules (new hierarchy-based):
    - platform_admin: Can view any
    - GM: Can view if agent belongs to a team in a center they manage
    - Director: Can view if agent belongs to a team they manage
    - Leader/Deputy Leader: Can view if agent is in their team
    - Member: Can only view their own agent's report
    """
    target_date = report_date or date.today()
    
    # Use new permission service
    can_view = await can_view_agent(db, current_user, agent_id)
    
    if not can_view:
        raise HTTPException(status_code=403, detail="Not authorized to view this report")
    
    # Get the report
    report = await get_agent_report(db, agent_id, target_date)
    
    if not report:
        # Try to generate a report
        try:
            report = await generate_agent_report(db, agent_id, datetime.combine(target_date, datetime.min.time()))
            await db.commit()
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"No report found and could not generate: {str(e)}")
    
    # Get agent name
    agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = agent_result.scalar_one_or_none()
    
    return {
        "id": str(report.id),
        "agent_id": str(report.agent_id),
        "agent_name": agent.name if agent else None,
        "report_date": report.report_date.date().isoformat() if report.report_date else target_date.isoformat(),
        "summary": report.summary,
        "completed_tasks": report.completed_tasks or [],
        "in_progress_tasks": report.in_progress_tasks or [],
        "planned_tasks": report.planned_tasks or [],
        "blockers": report.blockers or [],
        "highlights": report.highlights or [],
        "tasks_completed_count": report.tasks_completed_count,
        "tasks_in_progress_count": report.tasks_in_progress_count,
        "messages_sent": report.messages_sent,
        "tokens_used": report.tokens_used,
        "report_status": report.report_status,
        "is_auto_generated": report.is_auto_generated,
    }


# ─── Report Generation ─────────────────────────────────

@router.post("/agent/{agent_id}/generate")
async def generate_report_for_agent(
    agent_id: uuid.UUID,
    report_date: date = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger report generation for an agent."""
    # Verify ownership
    owns_agent = await _user_owns_agent(db, current_user.id, agent_id)
    is_admin = current_user.role in ("platform_admin", "org_admin")
    
    if not owns_agent and not is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    target_date = report_date or date.today()
    
    try:
        report = await generate_agent_report(
            db, agent_id,
            datetime.combine(target_date, datetime.min.time()),
            tenant_id=current_user.tenant_id,
        )
        await db.commit()
        
        return {
            "id": str(report.id),
            "agent_id": str(report.agent_id),
            "report_date": report.report_date.date().isoformat() if report.report_date else target_date.isoformat(),
            "summary": report.summary,
            "tasks_completed_count": report.tasks_completed_count,
            "message": "Report generated successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


# ─── Who Reports to Me / Who I Report To ───────────────

@router.get("/my-members")
async def get_members_reporting_to_me(
    agent_id: uuid.UUID = Query(..., description="The leader agent ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get list of agents that report to this leader agent."""
    # Verify ownership
    owns_agent = await _user_owns_agent(db, current_user.id, agent_id)
    is_leader = await _is_agent_leader(db, agent_id)
    is_admin = current_user.role in ("platform_admin", "org_admin")
    
    if not owns_agent and not is_admin:
        raise HTTPException(status_code=403, detail="You don't own this agent")
    
    if not is_leader and not is_admin:
        raise HTTPException(status_code=403, detail="This agent is not a leader")
    
    members = await get_agents_reporting_to_me(db, agent_id)
    return {"members": members}


@router.get("/my-leader")
async def get_my_leader_agent(
    agent_id: uuid.UUID = Query(..., description="The member agent ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the leader that this agent reports to."""
    # Verify ownership
    owns_agent = await _user_owns_agent(db, current_user.id, agent_id)
    is_admin = current_user.role in ("platform_admin", "org_admin")
    
    if not owns_agent and not is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    leader = await get_my_leader(db, agent_id)
    return {"leader": leader}
