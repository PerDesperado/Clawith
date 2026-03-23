"""Organization AI service — a system-level AI that can query all org data.

Provides tools for executives to ask questions about team status,
individual work, and organizational knowledge.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.agent import Agent
from app.models.audit import ChatMessage
from app.models.chat_session import ChatSession
from app.models.org import OrgDepartment, OrgMember, AgentRelationship
from app.models.task import Task, TaskLog
from app.models.team_task import TeamTask, AgentDailyReport
from app.models.user import User
from app.models.user_agent_binding import DailySummary, UserAgentBinding


async def query_team_status(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    department_id: Optional[str] = None,
) -> dict:
    """Query the work status of a team/department."""
    
    # Get department info
    dept_name = "全公司"
    if department_id:
        dept_r = await db.execute(select(OrgDepartment).where(OrgDepartment.id == uuid.UUID(department_id)))
        dept = dept_r.scalar_one_or_none()
        if dept:
            dept_name = dept.name

    # Get all agents in the tenant (optionally filtered by department)
    agent_query = select(Agent).where(Agent.tenant_id == tenant_id)
    
    # If department_id specified, filter agents by their bound members' department
    agent_ids_in_dept = None
    if department_id:
        binding_r = await db.execute(
            select(UserAgentBinding.agent_id).where(
                UserAgentBinding.department_id == uuid.UUID(department_id),
                UserAgentBinding.is_active == True,
            )
        )
        agent_ids_in_dept = [r[0] for r in binding_r.all()]
        if agent_ids_in_dept:
            agent_query = agent_query.where(Agent.id.in_(agent_ids_in_dept))
        else:
            agent_query = agent_query.where(Agent.id == None)  # no results

    result = await db.execute(agent_query)
    agents = result.scalars().all()

    # Get members in department
    member_query = select(OrgMember).where(OrgMember.tenant_id == tenant_id, OrgMember.status == "active")
    if department_id:
        member_query = member_query.where(OrgMember.department_id == uuid.UUID(department_id))
    member_r = await db.execute(member_query)
    members = member_r.scalars().all()

    # Aggregate stats
    running_agents = [a for a in agents if a.status == "running"]
    
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Tasks completed today
    agent_ids = [a.id for a in agents]
    tasks_today = 0
    tasks_in_progress = 0
    if agent_ids:
        done_r = await db.execute(
            select(func.count(Task.id)).where(
                Task.agent_id.in_(agent_ids),
                Task.status == "done",
                Task.completed_at >= today_start,
            )
        )
        tasks_today = done_r.scalar() or 0

        doing_r = await db.execute(
            select(func.count(Task.id)).where(
                Task.agent_id.in_(agent_ids),
                Task.status == "doing",
            )
        )
        tasks_in_progress = doing_r.scalar() or 0

    # Get recent agent daily reports
    recent_reports = []
    if agent_ids:
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
        report_r = await db.execute(
            select(AgentDailyReport).where(
                AgentDailyReport.agent_id.in_(agent_ids),
                func.date(AgentDailyReport.report_date) >= yesterday,
            ).order_by(AgentDailyReport.report_date.desc()).limit(20)
        )
        for report in report_r.scalars().all():
            agent_name = next((a.name for a in agents if a.id == report.agent_id), "Unknown")
            recent_reports.append({
                "agent_name": agent_name,
                "date": report.report_date.strftime("%Y-%m-%d") if report.report_date else "",
                "summary": report.summary or "",
                "tasks_completed": report.tasks_completed_count,
                "tasks_in_progress": report.tasks_in_progress_count,
            })

    agent_summaries = []
    for a in agents:
        agent_summaries.append({
            "name": a.name,
            "role": a.role_description or "",
            "status": a.status,
            "tokens_used_today": a.tokens_used_today,
        })

    return {
        "department": dept_name,
        "member_count": len(members),
        "total_agents": len(agents),
        "running_agents": len(running_agents),
        "tasks_completed_today": tasks_today,
        "tasks_in_progress": tasks_in_progress,
        "agents": agent_summaries,
        "recent_reports": recent_reports,
    }


async def query_person_work(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    member_id: Optional[str] = None,
    member_name: Optional[str] = None,
    period: str = "today",
) -> dict:
    """Query a specific person's work content."""
    
    # Find the member
    member = None
    if member_id:
        r = await db.execute(select(OrgMember).where(OrgMember.id == uuid.UUID(member_id)))
        member = r.scalar_one_or_none()
    elif member_name:
        r = await db.execute(
            select(OrgMember).where(
                OrgMember.tenant_id == tenant_id,
                OrgMember.name.ilike(f"%{member_name}%"),
                OrgMember.status == "active",
            )
        )
        member = r.scalar_one_or_none()
    
    if not member:
        return {"error": f"未找到成员: {member_name or member_id}"}

    # Find bound agents via AgentRelationship
    rel_r = await db.execute(
        select(AgentRelationship.agent_id).where(AgentRelationship.member_id == member.id)
    )
    agent_ids = [r[0] for r in rel_r.all()]

    # Also find via UserAgentBinding (by matching feishu_open_id -> user)
    if member.feishu_open_id:
        user_r = await db.execute(
            select(User.id).where(User.feishu_open_id == member.feishu_open_id)
        )
        user_id = user_r.scalar_one_or_none()
        if user_id:
            binding_r = await db.execute(
                select(UserAgentBinding.agent_id).where(
                    UserAgentBinding.user_id == user_id,
                    UserAgentBinding.is_active == True,
                )
            )
            agent_ids.extend([r[0] for r in binding_r.all()])
    
    agent_ids = list(set(agent_ids))

    # Determine time range
    now = datetime.now(timezone.utc)
    if period == "today":
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_label = "今日"
    elif period == "week":
        start_time = now - timedelta(days=7)
        period_label = "本周"
    elif period == "month":
        start_time = now - timedelta(days=30)
        period_label = "本月"
    else:
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_label = "今日"

    # Get agent details
    agents_data = []
    for aid in agent_ids:
        agent_r = await db.execute(select(Agent).where(Agent.id == aid))
        agent = agent_r.scalar_one_or_none()
        if not agent:
            continue

        # Tasks
        completed_r = await db.execute(
            select(Task).where(
                Task.agent_id == aid,
                Task.status == "done",
                Task.completed_at >= start_time,
            ).limit(20)
        )
        completed = completed_r.scalars().all()

        doing_r = await db.execute(
            select(Task).where(Task.agent_id == aid, Task.status == "doing")
        )
        doing = doing_r.scalars().all()

        agents_data.append({
            "name": agent.name,
            "role": agent.role_description or "",
            "status": agent.status,
            "completed_tasks": [{"title": t.title, "completed_at": t.completed_at.isoformat() if t.completed_at else ""} for t in completed],
            "in_progress_tasks": [{"title": t.title} for t in doing],
        })

    # Get daily summaries
    summaries = []
    if member.feishu_open_id:
        user_r = await db.execute(select(User.id).where(User.feishu_open_id == member.feishu_open_id))
        user_id = user_r.scalar_one_or_none()
        if user_id:
            sum_r = await db.execute(
                select(DailySummary).where(
                    DailySummary.user_id == user_id,
                    DailySummary.summary_date >= start_time.date(),
                ).order_by(DailySummary.summary_date.desc()).limit(7)
            )
            for s in sum_r.scalars().all():
                summaries.append({
                    "date": s.summary_date.isoformat(),
                    "content": s.content or "",
                })

    return {
        "member_name": member.name,
        "title": member.title,
        "department": member.department_path or "",
        "period": period_label,
        "bound_agents": agents_data,
        "daily_summaries": summaries,
    }


async def query_department_list(
    db: AsyncSession,
    tenant_id: uuid.UUID,
) -> list[dict]:
    """List all departments with member counts."""
    r = await db.execute(
        select(OrgDepartment).where(OrgDepartment.tenant_id == tenant_id).order_by(OrgDepartment.name)
    )
    depts = r.scalars().all()
    return [
        {
            "id": str(d.id),
            "name": d.name,
            "parent_id": str(d.parent_id) if d.parent_id else None,
            "member_count": d.member_count or 0,
        }
        for d in depts
    ]


async def search_org_members(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    query: str,
) -> list[dict]:
    """Search org members by name, title, or department."""
    r = await db.execute(
        select(OrgMember).where(
            OrgMember.tenant_id == tenant_id,
            OrgMember.status == "active",
            or_(
                OrgMember.name.ilike(f"%{query}%"),
                OrgMember.title.ilike(f"%{query}%"),
                OrgMember.department_path.ilike(f"%{query}%"),
            ),
        ).limit(20)
    )
    members = r.scalars().all()
    return [
        {
            "id": str(m.id),
            "name": m.name,
            "title": m.title or "",
            "department": m.department_path or "",
            "email": m.email or "",
        }
        for m in members
    ]


async def get_org_overview(
    db: AsyncSession,
    tenant_id: uuid.UUID,
) -> dict:
    """Get a high-level overview of the entire organization."""
    
    # Department count
    dept_count_r = await db.execute(
        select(func.count(OrgDepartment.id)).where(OrgDepartment.tenant_id == tenant_id)
    )
    dept_count = dept_count_r.scalar() or 0

    # Member count
    member_count_r = await db.execute(
        select(func.count(OrgMember.id)).where(
            OrgMember.tenant_id == tenant_id,
            OrgMember.status == "active",
        )
    )
    member_count = member_count_r.scalar() or 0

    # Agent stats
    agent_total_r = await db.execute(
        select(func.count(Agent.id)).where(Agent.tenant_id == tenant_id)
    )
    agent_total = agent_total_r.scalar() or 0

    agent_running_r = await db.execute(
        select(func.count(Agent.id)).where(Agent.tenant_id == tenant_id, Agent.status == "running")
    )
    agent_running = agent_running_r.scalar() or 0

    # Today's tasks
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    tenant_agent_ids = select(Agent.id).where(Agent.tenant_id == tenant_id)
    tasks_done_r = await db.execute(
        select(func.count(Task.id)).where(
            Task.agent_id.in_(tenant_agent_ids),
            Task.status == "done",
            Task.completed_at >= today_start,
        )
    )
    tasks_done_today = tasks_done_r.scalar() or 0

    # Departments with details
    dept_r = await db.execute(
        select(OrgDepartment).where(OrgDepartment.tenant_id == tenant_id).order_by(OrgDepartment.name)
    )
    departments = [
        {"name": d.name, "member_count": d.member_count or 0}
        for d in dept_r.scalars().all()
    ]

    return {
        "total_departments": dept_count,
        "total_members": member_count,
        "total_agents": agent_total,
        "running_agents": agent_running,
        "tasks_completed_today": tasks_done_today,
        "departments": departments,
    }


async def query_team_hierarchy(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    department_id: Optional[str] = None,
) -> dict:
    """Query digital employee team hierarchy: leaders and their team members.
    
    This shows the organization structure of digital employees based on their org_role.
    Leaders (组长) can see and summarize work from members (组员) in the same department.
    """
    from sqlalchemy.orm import selectinload
    
    # Get department info
    dept_name = "全公司"
    dept_filter = None
    if department_id:
        dept_r = await db.execute(select(OrgDepartment).where(OrgDepartment.id == uuid.UUID(department_id)))
        dept = dept_r.scalar_one_or_none()
        if dept:
            dept_name = dept.name
            dept_filter = uuid.UUID(department_id)

    # Get all bindings with agents, filtering by department if specified
    binding_query = (
        select(UserAgentBinding)
        .options(selectinload(UserAgentBinding.agent), selectinload(UserAgentBinding.user))
        .where(UserAgentBinding.is_active == True)
    )
    if dept_filter:
        binding_query = binding_query.where(UserAgentBinding.department_id == dept_filter)
    else:
        # Only include bindings from this tenant's users
        binding_query = binding_query.join(User).where(User.tenant_id == tenant_id)

    bindings_r = await db.execute(binding_query)
    bindings = bindings_r.scalars().all()

    # Separate leaders and members
    leaders: list[dict] = []
    members: list[dict] = []
    
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    
    for b in bindings:
        agent = b.agent
        if not agent:
            continue
            
        # Get recent tasks for this agent
        done_r = await db.execute(
            select(func.count(Task.id)).where(
                Task.agent_id == agent.id,
                Task.status == "done",
                Task.completed_at >= today_start,
            )
        )
        tasks_done = done_r.scalar() or 0
        
        doing_r = await db.execute(
            select(func.count(Task.id)).where(Task.agent_id == agent.id, Task.status == "doing")
        )
        tasks_doing = doing_r.scalar() or 0
        
        # Get latest daily report
        report_r = await db.execute(
            select(AgentDailyReport).where(AgentDailyReport.agent_id == agent.id)
            .order_by(AgentDailyReport.report_date.desc()).limit(1)
        )
        latest_report = report_r.scalar_one_or_none()
        
        agent_data = {
            "agent_id": str(agent.id),
            "agent_name": agent.name,
            "user_name": b.user.display_name if b.user else None,
            "status": agent.status,
            "tasks_completed_today": tasks_done,
            "tasks_in_progress": tasks_doing,
            "latest_report_summary": latest_report.summary[:200] if latest_report and latest_report.summary else None,
            "latest_report_date": latest_report.report_date.strftime("%Y-%m-%d") if latest_report else None,
        }
        
        if b.org_role == "leader":
            agent_data["department_id"] = str(b.department_id) if b.department_id else None
            leaders.append(agent_data)
        else:
            agent_data["department_id"] = str(b.department_id) if b.department_id else None
            members.append(agent_data)

    # Group members by department for leaders to see
    dept_members: dict[str, list[dict]] = {}
    for m in members:
        dept_id = m.get("department_id") or "unassigned"
        if dept_id not in dept_members:
            dept_members[dept_id] = []
        dept_members[dept_id].append(m)

    # Attach team members to each leader
    for leader in leaders:
        leader_dept = leader.get("department_id") or "unassigned"
        team = dept_members.get(leader_dept, [])
        leader["team_members"] = team
        leader["team_size"] = len(team)
        leader["team_total_tasks_today"] = sum(m["tasks_completed_today"] for m in team) + leader["tasks_completed_today"]

    return {
        "department": dept_name,
        "leaders": leaders,
        "unassigned_members": [m for m in members if not any(m in l.get("team_members", []) for l in leaders)],
        "total_leaders": len(leaders),
        "total_members": len(members),
    }


async def query_leader_summary(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    leader_name: Optional[str] = None,
    leader_id: Optional[str] = None,
) -> dict:
    """Query a specific leader's summary including their team's work.
    
    A leader (组长) can view and summarize their team members' (组员) work reports.
    """
    from sqlalchemy.orm import selectinload
    
    # Find the leader
    binding_query = (
        select(UserAgentBinding)
        .options(selectinload(UserAgentBinding.agent), selectinload(UserAgentBinding.user))
        .where(
            UserAgentBinding.is_active == True,
            UserAgentBinding.org_role == "leader",
        )
    )
    
    if leader_id:
        binding_query = binding_query.where(UserAgentBinding.agent_id == uuid.UUID(leader_id))
    elif leader_name:
        binding_query = binding_query.join(Agent).where(Agent.name.ilike(f"%{leader_name}%"))
    else:
        return {"error": "请提供组长名称或ID"}
    
    binding_r = await db.execute(binding_query)
    leader_binding = binding_r.scalar_one_or_none()
    
    if not leader_binding:
        return {"error": f"未找到组长: {leader_name or leader_id}"}
    
    leader_agent = leader_binding.agent
    dept_id = leader_binding.department_id
    
    # Get team members (same department, role=member)
    team_query = (
        select(UserAgentBinding)
        .options(selectinload(UserAgentBinding.agent))
        .where(
            UserAgentBinding.department_id == dept_id,
            UserAgentBinding.org_role == "member",
            UserAgentBinding.is_active == True,
        )
    )
    team_r = await db.execute(team_query)
    team_bindings = team_r.scalars().all()
    
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    
    # Leader's own work
    leader_report_r = await db.execute(
        select(AgentDailyReport).where(
            AgentDailyReport.agent_id == leader_agent.id,
            func.date(AgentDailyReport.report_date) >= yesterday,
        ).order_by(AgentDailyReport.report_date.desc()).limit(1)
    )
    leader_report = leader_report_r.scalar_one_or_none()
    
    leader_tasks_r = await db.execute(
        select(Task).where(
            Task.agent_id == leader_agent.id,
            Task.status == "done",
            Task.completed_at >= today_start,
        ).limit(10)
    )
    leader_tasks = leader_tasks_r.scalars().all()
    
    # Team members' work
    team_data = []
    total_team_tasks = 0
    for tb in team_bindings:
        agent = tb.agent
        if not agent:
            continue
        
        # Get recent report
        report_r = await db.execute(
            select(AgentDailyReport).where(
                AgentDailyReport.agent_id == agent.id,
                func.date(AgentDailyReport.report_date) >= yesterday,
            ).order_by(AgentDailyReport.report_date.desc()).limit(1)
        )
        report = report_r.scalar_one_or_none()
        
        # Get today's completed tasks
        tasks_r = await db.execute(
            select(func.count(Task.id)).where(
                Task.agent_id == agent.id,
                Task.status == "done",
                Task.completed_at >= today_start,
            )
        )
        tasks_done = tasks_r.scalar() or 0
        total_team_tasks += tasks_done
        
        team_data.append({
            "agent_name": agent.name,
            "status": agent.status,
            "tasks_completed_today": tasks_done,
            "latest_report": report.summary[:300] if report and report.summary else None,
            "report_date": report.report_date.strftime("%Y-%m-%d") if report else None,
        })
    
    # Get department name
    dept_name = "未分配"
    if dept_id:
        dept_r = await db.execute(select(OrgDepartment).where(OrgDepartment.id == dept_id))
        dept = dept_r.scalar_one_or_none()
        if dept:
            dept_name = dept.name
    
    return {
        "leader": {
            "name": leader_agent.name,
            "status": leader_agent.status,
            "tasks_completed_today": len(leader_tasks),
            "recent_tasks": [{"title": t.title} for t in leader_tasks],
            "latest_report": leader_report.summary[:500] if leader_report and leader_report.summary else None,
        },
        "department": dept_name,
        "team_size": len(team_data),
        "team_total_tasks_today": total_team_tasks + len(leader_tasks),
        "team_members": team_data,
    }
