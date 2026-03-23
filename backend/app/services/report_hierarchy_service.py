"""Report Hierarchy Service.

Implements the hierarchical report flow based on human organization structure:
1. Digital employees (Agents) inherit hierarchy from their linked human employees (OrgMembers)
2. If an agent's linked OrgMember has title="leader", the agent is a leader
3. Leaders can view their team members' reports
4. Reports flow up the hierarchy: member -> leader -> upper leader
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.agent import Agent
from app.models.org import OrgDepartment, OrgMember, AgentRelationship
from app.models.team_task import AgentDailyReport
from app.models.user_agent_binding import UserAgentBinding


async def get_team_hierarchy(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    department_id: Optional[uuid.UUID] = None,
) -> dict:
    """
    Get the team hierarchy based on org_members' structure.
    
    Logic:
    1. Find all agents that have AgentRelationship with OrgMembers
    2. Group by OrgMember's department
    3. Agents linked to OrgMembers with title="leader" become leaders
    4. Agents linked to OrgMembers with title="member" become members
    
    Returns structure:
    {
        "departments": [
            {
                "id": "...",
                "name": "部门名",
                "leaders": [
                    {
                        "binding_id": "...",
                        "agent_id": "...",
                        "agent_name": "scut4号",
                        "org_member_name": "1号员工",
                        "org_role": "leader",
                        "members": [
                            {"agent_id": "...", "agent_name": "scut2号", "org_member_name": "3号员工"},
                            {"agent_id": "...", "agent_name": "scut3号", "org_member_name": "2号员工"},
                        ]
                    }
                ]
            }
        ]
    }
    """
    # Get all agent relationships with their linked org members
    query = (
        select(AgentRelationship)
        .options(
            selectinload(AgentRelationship.member).selectinload(OrgMember.department),
        )
        .join(OrgMember, AgentRelationship.member_id == OrgMember.id)
    )
    
    if tenant_id:
        query = query.where(OrgMember.tenant_id == tenant_id)
    
    if department_id:
        query = query.where(OrgMember.department_id == department_id)
    
    result = await db.execute(query)
    relationships = result.scalars().all()
    
    # Get agent info for each relationship
    agent_ids = [r.agent_id for r in relationships]
    if not agent_ids:
        return {"departments": []}
    
    agents_result = await db.execute(
        select(Agent).where(Agent.id.in_(agent_ids))
    )
    agents_map = {a.id: a for a in agents_result.scalars().all()}
    
    # Group by department
    dept_map: dict[str, dict] = {}
    
    for rel in relationships:
        member = rel.member
        if not member or not member.department:
            continue
        
        agent = agents_map.get(rel.agent_id)
        if not agent:
            continue
        
        dept_id = str(member.department_id)
        dept_name = member.department.name
        
        if dept_id not in dept_map:
            dept_map[dept_id] = {
                "id": dept_id,
                "name": dept_name,
                "leaders": [],
                "members": [],
            }
        
        # Determine role from org member's title
        is_leader = member.title.lower() in ("leader", "组长", "主管", "经理", "总监")
        
        agent_info = {
            "agent_id": str(agent.id),
            "agent_name": agent.name,
            "agent_avatar": agent.avatar_url,
            "agent_status": agent.status,
            "org_member_id": str(member.id),
            "org_member_name": member.name,
            "org_role": "leader" if is_leader else "member",
        }
        
        if is_leader:
            dept_map[dept_id]["leaders"].append({**agent_info, "members": []})
        else:
            dept_map[dept_id]["members"].append(agent_info)
    
    # Assign members to their department's leaders
    for dept_id, dept_data in dept_map.items():
        if dept_data["leaders"] and dept_data["members"]:
            # Assign all members to the first leader in department
            dept_data["leaders"][0]["members"] = dept_data["members"]
        # Keep members in response for non-leader departments
        if not dept_data["leaders"] and dept_data["members"]:
            # Create a "virtual" leader entry for display
            pass
        del dept_data["members"]  # Remove top-level members list
    
    # Filter out departments with no leaders
    departments_with_leaders = [d for d in dept_map.values() if d["leaders"]]
    
    return {"departments": departments_with_leaders}


async def get_leader_with_members(
    db: AsyncSession,
    leader_agent_id: uuid.UUID,
) -> dict | None:
    """
    Get a leader and their team members based on org structure.
    
    Returns:
    {
        "leader": {...},
        "members": [...]
    }
    """
    # Get the leader's relationship and org member
    leader_rel_result = await db.execute(
        select(AgentRelationship)
        .options(
            selectinload(AgentRelationship.member).selectinload(OrgMember.department),
        )
        .where(AgentRelationship.agent_id == leader_agent_id)
    )
    leader_rel = leader_rel_result.scalar_one_or_none()
    
    if not leader_rel or not leader_rel.member:
        return None
    
    leader_member = leader_rel.member
    
    # Verify this person is a leader
    if leader_member.title.lower() not in ("leader", "组长", "主管", "经理", "总监"):
        return None
    
    # Get leader agent info
    leader_agent_result = await db.execute(
        select(Agent).where(Agent.id == leader_agent_id)
    )
    leader_agent = leader_agent_result.scalar_one_or_none()
    
    if not leader_agent:
        return None
    
    # Find all members in the same department (excluding the leader)
    members_result = await db.execute(
        select(AgentRelationship)
        .options(selectinload(AgentRelationship.member))
        .join(OrgMember, AgentRelationship.member_id == OrgMember.id)
        .where(
            OrgMember.department_id == leader_member.department_id,
            OrgMember.id != leader_member.id,  # Exclude the leader
        )
    )
    member_relationships = members_result.scalars().all()
    
    # Get agent info for members
    member_agent_ids = [r.agent_id for r in member_relationships]
    if member_agent_ids:
        member_agents_result = await db.execute(
            select(Agent).where(Agent.id.in_(member_agent_ids))
        )
        member_agents_map = {a.id: a for a in member_agents_result.scalars().all()}
    else:
        member_agents_map = {}
    
    members = []
    for rel in member_relationships:
        agent = member_agents_map.get(rel.agent_id)
        if agent:
            members.append({
                "agent_id": str(rel.agent_id),
                "agent_name": agent.name,
                "org_member_name": rel.member.name if rel.member else None,
            })
    
    return {
        "leader": {
            "agent_id": str(leader_agent_id),
            "agent_name": leader_agent.name,
            "org_member_name": leader_member.name,
            "department_id": str(leader_member.department_id) if leader_member.department_id else None,
            "department_name": leader_member.department.name if leader_member.department else None,
        },
        "members": members,
    }


async def get_agent_report(
    db: AsyncSession,
    agent_id: uuid.UUID,
    report_date: date,
) -> AgentDailyReport | None:
    """Get a specific agent's daily report."""
    result = await db.execute(
        select(AgentDailyReport)
        .options(selectinload(AgentDailyReport.agent))
        .where(
            AgentDailyReport.agent_id == agent_id,
            func.date(AgentDailyReport.report_date) == report_date,
        )
    )
    return result.scalar_one_or_none()


async def get_team_reports_for_leader(
    db: AsyncSession,
    leader_agent_id: uuid.UUID,
    report_date: date,
) -> dict:
    """
    Get all team member reports for a leader.
    
    Returns:
    {
        "leader": {
            "agent_id": "...",
            "agent_name": "scut4号",
            "org_member_name": "1号员工",
            "report": {...} or null
        },
        "members": [
            {
                "agent_id": "...",
                "agent_name": "scut2号",
                "org_member_name": "3号员工",
                "report": {...} or null
            },
            ...
        ],
        "report_date": "2026-03-19"
    }
    """
    team_data = await get_leader_with_members(db, leader_agent_id)
    if not team_data:
        return {"error": "Leader not found or has no team"}
    
    # Get leader's own report
    leader_report = await get_agent_report(db, leader_agent_id, report_date)
    
    # Get all member reports
    member_reports = []
    for member in team_data["members"]:
        m_id = uuid.UUID(member["agent_id"])
        report = await get_agent_report(db, m_id, report_date)
        member_reports.append({
            "agent_id": member["agent_id"],
            "agent_name": member["agent_name"],
            "org_member_name": member.get("org_member_name"),
            "report": _serialize_report(report) if report else None,
        })
    
    return {
        "leader": {
            "agent_id": team_data["leader"]["agent_id"],
            "agent_name": team_data["leader"]["agent_name"],
            "org_member_name": team_data["leader"].get("org_member_name"),
            "report": _serialize_report(leader_report) if leader_report else None,
        },
        "members": member_reports,
        "report_date": report_date.isoformat(),
    }


async def generate_consolidated_report(
    db: AsyncSession,
    leader_agent_id: uuid.UUID,
    report_date: date,
) -> dict:
    """
    Generate a consolidated report for a leader, combining:
    - Leader's own work
    - All team members' reports
    
    This is what the leader would send to their upper-level leader.
    """
    team_reports = await get_team_reports_for_leader(db, leader_agent_id, report_date)
    
    if "error" in team_reports:
        return team_reports
    
    # Aggregate statistics
    total_tasks_completed = 0
    total_tasks_in_progress = 0
    total_tokens_used = 0
    
    # Collect all highlights
    all_highlights = []
    all_blockers = []
    
    # Process leader's report
    leader_report = team_reports["leader"]["report"]
    if leader_report:
        total_tasks_completed += leader_report.get("tasks_completed_count", 0)
        total_tasks_in_progress += leader_report.get("tasks_in_progress_count", 0)
        total_tokens_used += leader_report.get("tokens_used", 0)
        all_highlights.extend(leader_report.get("highlights", []))
        all_blockers.extend(leader_report.get("blockers", []))
    
    # Process member reports
    member_summaries = []
    for m in team_reports["members"]:
        r = m["report"]
        if r:
            total_tasks_completed += r.get("tasks_completed_count", 0)
            total_tasks_in_progress += r.get("tasks_in_progress_count", 0)
            total_tokens_used += r.get("tokens_used", 0)
            all_highlights.extend(r.get("highlights", []))
            all_blockers.extend(r.get("blockers", []))
            
            member_summaries.append({
                "name": m["agent_name"],
                "org_member_name": m.get("org_member_name"),
                "summary": r.get("summary", "无报告"),
                "tasks_completed": r.get("tasks_completed_count", 0),
            })
        else:
            member_summaries.append({
                "name": m["agent_name"],
                "org_member_name": m.get("org_member_name"),
                "summary": "暂无日报",
                "tasks_completed": 0,
            })
    
    # Generate consolidated summary text
    leader_name = team_reports["leader"]["agent_name"]
    leader_org_name = team_reports["leader"].get("org_member_name", "")
    summary_parts = [
        f"## {leader_name} ({leader_org_name}) 团队日报汇总 ({report_date.strftime('%Y-%m-%d')})\n",
        f"### 团队概况",
        f"- 团队成员数：{len(team_reports['members'])} 人",
        f"- 今日完成任务：**{total_tasks_completed}** 项",
        f"- 进行中任务：**{total_tasks_in_progress}** 项",
        f"- Token 消耗：**{total_tokens_used}**\n",
    ]
    
    # Leader's own work
    if leader_report:
        summary_parts.append(f"### 组长 {leader_name} 工作")
        summary_parts.append(leader_report.get("summary", "无详细报告"))
        summary_parts.append("")
    
    # Member summaries
    if member_summaries:
        summary_parts.append("### 组员工作汇总")
        for ms in member_summaries:
            org_name = f" ({ms['org_member_name']})" if ms.get('org_member_name') else ""
            summary_parts.append(f"**{ms['name']}{org_name}**：{ms['summary']} (完成 {ms['tasks_completed']} 项)")
        summary_parts.append("")
    
    # Highlights
    if all_highlights:
        summary_parts.append("### 亮点")
        for h in all_highlights:
            summary_parts.append(f"- {h}")
        summary_parts.append("")
    
    # Blockers
    if all_blockers:
        summary_parts.append("### 阻塞项")
        for b in all_blockers:
            summary_parts.append(f"- {b}")
    
    consolidated_content = "\n".join(summary_parts)
    
    return {
        "leader_agent_id": str(leader_agent_id),
        "leader_name": leader_name,
        "leader_org_member_name": leader_org_name,
        "report_date": report_date.isoformat(),
        "consolidated_summary": consolidated_content,
        "statistics": {
            "team_size": len(team_reports["members"]),
            "total_tasks_completed": total_tasks_completed,
            "total_tasks_in_progress": total_tasks_in_progress,
            "total_tokens_used": total_tokens_used,
        },
        "member_summaries": member_summaries,
        "highlights": all_highlights,
        "blockers": all_blockers,
        "raw_reports": team_reports,
    }


async def get_agents_reporting_to_me(
    db: AsyncSession,
    leader_agent_id: uuid.UUID,
) -> list[dict]:
    """Get list of agents that report to this leader."""
    team_data = await get_leader_with_members(db, leader_agent_id)
    if not team_data:
        return []
    return team_data["members"]


async def can_view_report(
    db: AsyncSession,
    viewer_agent_id: uuid.UUID,
    target_agent_id: uuid.UUID,
) -> bool:
    """
    Check if viewer_agent can view target_agent's report.
    
    Rules:
    1. An agent can always view their own report
    2. A leader can view their team members' reports
    3. Upper-level leaders can view consolidated reports (handled separately)
    """
    if viewer_agent_id == target_agent_id:
        return True
    
    # Check if viewer is a leader in the same department
    viewer_rel_result = await db.execute(
        select(AgentRelationship)
        .options(selectinload(AgentRelationship.member))
        .where(AgentRelationship.agent_id == viewer_agent_id)
    )
    viewer_rel = viewer_rel_result.scalar_one_or_none()
    
    if not viewer_rel or not viewer_rel.member:
        return False
    
    # Check if viewer is a leader
    if viewer_rel.member.title.lower() not in ("leader", "组长", "主管", "经理", "总监"):
        return False
    
    # Check if target is in the same department
    target_rel_result = await db.execute(
        select(AgentRelationship)
        .options(selectinload(AgentRelationship.member))
        .where(AgentRelationship.agent_id == target_agent_id)
    )
    target_rel = target_rel_result.scalar_one_or_none()
    
    if not target_rel or not target_rel.member:
        return False
    
    return target_rel.member.department_id == viewer_rel.member.department_id


def _serialize_report(report: AgentDailyReport) -> dict:
    """Serialize a report to dict."""
    return {
        "id": str(report.id),
        "agent_id": str(report.agent_id),
        "report_date": report.report_date.date().isoformat() if report.report_date else None,
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
        "visibility": report.visibility,
        "report_status": report.report_status,
        "is_auto_generated": report.is_auto_generated,
        "generated_at": report.generated_at.isoformat() if report.generated_at else None,
    }


async def get_my_leader(
    db: AsyncSession,
    agent_id: uuid.UUID,
) -> dict | None:
    """Get the leader of an agent (if any)."""
    # Get this agent's relationship
    agent_rel_result = await db.execute(
        select(AgentRelationship)
        .options(selectinload(AgentRelationship.member).selectinload(OrgMember.department))
        .where(AgentRelationship.agent_id == agent_id)
    )
    agent_rel = agent_rel_result.scalar_one_or_none()
    
    if not agent_rel or not agent_rel.member:
        return None
    
    # If this agent's org member is already a leader, they don't have an upper leader
    if agent_rel.member.title.lower() in ("leader", "组长", "主管", "经理", "总监"):
        return None
    
    # Find the leader in the same department
    leader_result = await db.execute(
        select(AgentRelationship)
        .options(selectinload(AgentRelationship.member))
        .join(OrgMember, AgentRelationship.member_id == OrgMember.id)
        .where(
            OrgMember.department_id == agent_rel.member.department_id,
            OrgMember.title.in_(["leader", "组长", "主管", "经理", "总监"]),
        )
    )
    leader_rel = leader_result.scalar_one_or_none()
    
    if not leader_rel:
        return None
    
    # Get leader agent info
    leader_agent_result = await db.execute(
        select(Agent).where(Agent.id == leader_rel.agent_id)
    )
    leader_agent = leader_agent_result.scalar_one_or_none()
    
    return {
        "agent_id": str(leader_rel.agent_id),
        "agent_name": leader_agent.name if leader_agent else None,
        "org_member_name": leader_rel.member.name if leader_rel.member else None,
    }
