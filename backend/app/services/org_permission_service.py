"""Organization Permission Service.

Implements permission checking based on the organization hierarchy using OrgDepartment table.

OrgDepartment uses self-referencing structure to represent hierarchy:
- Root nodes (parent_id=NULL): Top-level departments like 云产品一部, 测试部门
- Child nodes: Centers, Teams, etc. (any depth)

Permission Levels based on member_role:
- Level 5: platform_admin - Can view all tenants, departments, reports
- Level 4: gm - Can view managed departments/centers and all children
- Level 3: director - Can view managed teams and all members under them
- Level 2: leader/deputy_leader - Can view their department and all members in it
- Level 1: member - Can only view their own reports
"""

import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.agent import Agent
from app.models.org import (
    OrgDepartment,
    OrgMember,
    OrgManagementRelation,
    UserOrgMemberLink,
    AgentRelationship,
)
from app.models.user import User


@dataclass
class ViewableScope:
    """Defines what a user can view."""
    
    # If True, can view all data (platform_admin)
    view_all: bool = False
    
    # Viewable OrgDepartment node IDs (any level in hierarchy)
    department_ids: list[uuid.UUID] = None
    
    # Viewable agent IDs
    agent_ids: list[uuid.UUID] = None
    
    # User's role info
    user_role: str = "member"
    org_member_id: Optional[uuid.UUID] = None
    user_department_id: Optional[uuid.UUID] = None
    
    def __post_init__(self):
        if self.department_ids is None:
            self.department_ids = []
        if self.agent_ids is None:
            self.agent_ids = []


async def get_user_org_member(db: AsyncSession, user_id: uuid.UUID) -> OrgMember | None:
    """Get the OrgMember linked to a User."""
    result = await db.execute(
        select(UserOrgMemberLink)
        .options(selectinload(UserOrgMemberLink.org_member))
        .where(
            UserOrgMemberLink.user_id == user_id,
            UserOrgMemberLink.is_primary == True,
        )
    )
    link = result.scalar_one_or_none()
    return link.org_member if link else None


async def get_management_relations(
    db: AsyncSession, 
    manager_member_id: uuid.UUID
) -> list[OrgManagementRelation]:
    """Get all management relations for a manager."""
    result = await db.execute(
        select(OrgManagementRelation)
        .where(OrgManagementRelation.manager_member_id == manager_member_id)
    )
    return list(result.scalars().all())


async def get_department_descendants(
    db: AsyncSession, 
    department_id: uuid.UUID,
    tenant_id: Optional[uuid.UUID] = None
) -> list[uuid.UUID]:
    """Get all descendant department IDs for a given department node (using recursive traversal)."""
    all_ids = [department_id]
    
    # Get all departments for tenant
    query = select(OrgDepartment)
    if tenant_id:
        query = query.where(OrgDepartment.tenant_id == tenant_id)
    result = await db.execute(query)
    all_depts = {d.id: d for d in result.scalars().all()}
    
    # BFS to find all descendants
    to_process = [department_id]
    while to_process:
        current_id = to_process.pop(0)
        for dept_id, dept in all_depts.items():
            if dept.parent_id == current_id and dept_id not in all_ids:
                all_ids.append(dept_id)
                to_process.append(dept_id)
    
    return all_ids


async def get_members_in_departments(
    db: AsyncSession, 
    department_ids: list[uuid.UUID]
) -> list[OrgMember]:
    """Get all org members in the given department nodes."""
    if not department_ids:
        return []
    
    result = await db.execute(
        select(OrgMember).where(OrgMember.department_id.in_(department_ids))
    )
    return list(result.scalars().all())


async def get_agents_for_members(
    db: AsyncSession, 
    member_ids: list[uuid.UUID]
) -> list[uuid.UUID]:
    """Get all agent IDs associated with given org members."""
    if not member_ids:
        return []
    
    result = await db.execute(
        select(AgentRelationship.agent_id).where(
            AgentRelationship.member_id.in_(member_ids)
        )
    )
    return [a[0] for a in result.all()]


async def get_viewable_scope(
    db: AsyncSession,
    user: User,
    tenant_id: Optional[uuid.UUID] = None,
) -> ViewableScope:
    """
    Get the viewable scope for a user based on their role and department.
    
    Uses the OrgDepartment hierarchy (department_id on OrgMember) to determine
    what a user can view.
    """
    scope = ViewableScope()
    
    # Level 5: Platform admin can view all
    if user.role == "platform_admin":
        scope.view_all = True
        scope.user_role = "platform_admin"
        return scope
    
    # Get user's org_member
    org_member = await get_user_org_member(db, user.id)
    
    if not org_member:
        # User is not linked to any org_member, can only view their own bound agents
        from app.models.user_agent_binding import UserAgentBinding
        bindings_result = await db.execute(
            select(UserAgentBinding.agent_id).where(UserAgentBinding.user_id == user.id)
        )
        scope.agent_ids = [b[0] for b in bindings_result.all()]
        scope.user_role = "member"
        return scope
    
    scope.org_member_id = org_member.id
    scope.user_role = org_member.member_role
    scope.user_department_id = org_member.department_id
    
    viewable_dept_ids = set()
    
    # Get management relations
    relations = await get_management_relations(db, org_member.id)
    
    # Process based on member_role and relations
    if org_member.member_role in ("gm", "director"):
        # GM/Director: can view managed departments and all their descendants
        for rel in relations:
            if rel.managed_department_id:
                descendants = await get_department_descendants(
                    db, rel.managed_department_id, tenant_id
                )
                viewable_dept_ids.update(descendants)
    
    if org_member.member_role in ("leader", "deputy_leader"):
        # Leader/Deputy Leader: can view their own department and descendants
        for rel in relations:
            if rel.managed_department_id:
                descendants = await get_department_descendants(
                    db, rel.managed_department_id, tenant_id
                )
                viewable_dept_ids.update(descendants)
        
        # Also include own department if set
        if org_member.department_id:
            descendants = await get_department_descendants(
                db, org_member.department_id, tenant_id
            )
            viewable_dept_ids.update(descendants)
    
    if org_member.member_role == "member":
        # Member: can only view their own department
        if org_member.department_id:
            viewable_dept_ids.add(org_member.department_id)
    
    scope.department_ids = list(viewable_dept_ids)
    
    # Get viewable agents
    if scope.department_ids:
        members = await get_members_in_departments(db, scope.department_ids)
        member_ids = [m.id for m in members]
        
        if org_member.member_role == "member":
            # Members can only view their own agent
            scope.agent_ids = await get_agents_for_members(db, [org_member.id])
        else:
            # Managers can view all agents in viewable departments
            scope.agent_ids = await get_agents_for_members(db, member_ids)
    
    return scope


async def can_view_agent(
    db: AsyncSession,
    user: User,
    agent_id: uuid.UUID,
) -> bool:
    """Check if a user can view a specific agent's data."""
    scope = await get_viewable_scope(db, user)
    
    if scope.view_all:
        return True
    
    return agent_id in scope.agent_ids


async def can_view_department(
    db: AsyncSession,
    user: User,
    department_id: uuid.UUID,
) -> bool:
    """Check if a user can view a specific department's data."""
    scope = await get_viewable_scope(db, user)
    
    if scope.view_all:
        return True
    
    return department_id in scope.department_ids


async def get_filtered_hierarchy(
    db: AsyncSession,
    user: User,
    tenant_id: Optional[uuid.UUID] = None,
) -> dict:
    """
    Get the organization hierarchy filtered by user's permissions.
    
    Uses OrgDepartment table with self-referencing parent_id.
    Builds a 3-level structure for backward compatibility:
    - departments (root nodes, parent_id=NULL)
    - centers (children of root nodes)
    - teams (children of centers)
    
    Returns:
    {
        "departments": [
            {
                "id": "...",
                "name": "云产品一部",
                "centers": [
                    {
                        "id": "...",
                        "name": "计算产品中心",
                        "teams": [
                            {
                                "id": "...",
                                "name": "分布式云产品组",
                                "leaders": [...],
                                "members": [...]
                            }
                        ]
                    }
                ]
            }
        ]
    }
    """
    scope = await get_viewable_scope(db, user, tenant_id)
    
    # Get all OrgDepartment nodes for this tenant
    query = select(OrgDepartment)
    if tenant_id:
        query = query.where(OrgDepartment.tenant_id == tenant_id)
    
    result = await db.execute(query)
    all_depts = list(result.scalars().all())
    
    # Build lookup maps
    dept_map = {d.id: d for d in all_depts}
    children_map: dict[uuid.UUID | None, list] = {None: []}
    for d in all_depts:
        if d.parent_id not in children_map:
            children_map[d.parent_id] = []
        children_map[d.parent_id].append(d)
        if d.id not in children_map:
            children_map[d.id] = []
    
    # Filter based on scope
    if not scope.view_all:
        # Only include departments the user can view
        viewable_set = set(scope.department_ids)
        
        # Also include ancestors of viewable departments (for tree structure)
        for dept_id in list(viewable_set):
            current = dept_map.get(dept_id)
            while current and current.parent_id:
                viewable_set.add(current.parent_id)
                current = dept_map.get(current.parent_id)
        
        scope.department_ids = list(viewable_set)
    
    # Build hierarchy (up to 3 levels: dept -> center -> team)
    result_depts = []
    
    # Get root departments
    root_depts = children_map.get(None, [])
    
    for root in root_depts:
        if not scope.view_all and root.id not in scope.department_ids:
            continue
        
        # Get centers (children of root)
        centers = children_map.get(root.id, [])
        result_centers = []
        
        for center in centers:
            if not scope.view_all and center.id not in scope.department_ids:
                continue
            
            # Get teams (children of center)
            teams = children_map.get(center.id, [])
            result_teams = []
            
            for team in teams:
                if not scope.view_all and team.id not in scope.department_ids:
                    continue
                
                # Get team members
                team_data = await get_department_with_members(db, team.id, scope)
                if team_data:
                    result_teams.append(team_data)
            
            # If center has no teams but has members, treat it as a team itself
            if not teams:
                center_as_team = await get_department_with_members(db, center.id, scope)
                if center_as_team and (center_as_team["leaders"] or center_as_team["members"]):
                    result_teams.append(center_as_team)
            
            if result_teams:
                result_centers.append({
                    "id": str(center.id),
                    "name": center.name,
                    "description": center.description,
                    "teams": result_teams,
                })
        
        # If dept has no centers but has members, treat it as having a virtual center
        if not centers:
            dept_as_team = await get_department_with_members(db, root.id, scope)
            if dept_as_team and (dept_as_team["leaders"] or dept_as_team["members"]):
                result_centers.append({
                    "id": str(root.id),
                    "name": root.name,
                    "description": root.description,
                    "teams": [dept_as_team],
                })
        
        if result_centers:
            result_depts.append({
                "id": str(root.id),
                "name": root.name,
                "description": root.description,
                "centers": result_centers,
            })
    
    return {"departments": result_depts}


async def get_department_with_members(
    db: AsyncSession,
    department_id: uuid.UUID,
    scope: Optional[ViewableScope] = None,
) -> dict | None:
    """
    Get a department node with its leaders and members.
    
    Leaders are determined by:
    1. OrgManagementRelation where managed_department_id = this department
    2. Or member_role in ('leader', 'deputy_leader') and department_id = this department
    """
    # Get department info
    dept_result = await db.execute(
        select(OrgDepartment).where(OrgDepartment.id == department_id)
    )
    dept = dept_result.scalar_one_or_none()
    
    if not dept:
        return None
    
    # Get all members in this department
    members_result = await db.execute(
        select(OrgMember).where(OrgMember.department_id == department_id)
    )
    all_members = list(members_result.scalars().all())
    
    # Get management relations for this department
    mgmt_result = await db.execute(
        select(OrgManagementRelation)
        .options(selectinload(OrgManagementRelation.manager))
        .where(
            OrgManagementRelation.managed_department_id == department_id,
            OrgManagementRelation.manager_role.in_(["leader", "deputy_leader", "director"])
        )
    )
    leader_relations = list(mgmt_result.scalars().all())
    
    leaders = []
    leader_member_ids = set()
    
    # Add leaders from management relations
    for rel in leader_relations:
        if rel.manager:
            leader_member_ids.add(rel.manager.id)
            agent_info = await get_agent_for_member(db, rel.manager.id)
            leaders.append({
                "org_member_id": str(rel.manager.id),
                "name": rel.manager.name,
                "title": rel.manager.title,
                "is_primary": rel.is_primary,
                "role": rel.manager_role,
                "agent": agent_info,
            })
    
    # Also check members with leader/deputy_leader role
    for member in all_members:
        if member.id in leader_member_ids:
            continue
        if member.member_role in ("leader", "deputy_leader"):
            leader_member_ids.add(member.id)
            agent_info = await get_agent_for_member(db, member.id)
            leaders.append({
                "org_member_id": str(member.id),
                "name": member.name,
                "title": member.title,
                "is_primary": member.member_role == "leader",
                "role": member.member_role,
                "agent": agent_info,
            })
    
    # Build members list (excluding leaders)
    members = []
    for member in all_members:
        if member.id in leader_member_ids:
            continue
        
        # For regular members, only include if scope allows
        if scope and not scope.view_all and scope.user_role == "member":
            if scope.org_member_id != member.id:
                continue
        
        agent_info = await get_agent_for_member(db, member.id)
        members.append({
            "org_member_id": str(member.id),
            "name": member.name,
            "title": member.title,
            "role": member.member_role,
            "agent": agent_info,
        })
    
    return {
        "id": str(dept.id),
        "name": dept.name,
        "description": dept.description,
        "leaders": leaders,
        "members": members,
    }


async def get_agent_for_member(db: AsyncSession, member_id: uuid.UUID) -> dict | None:
    """Get the agent linked to an org member."""
    rel_result = await db.execute(
        select(AgentRelationship)
        .where(AgentRelationship.member_id == member_id)
    )
    rel = rel_result.scalar_one_or_none()
    
    if not rel:
        return None
    
    agent_result = await db.execute(
        select(Agent).where(Agent.id == rel.agent_id)
    )
    agent = agent_result.scalar_one_or_none()
    
    if not agent:
        return None
    
    return {
        "id": str(agent.id),
        "name": agent.name,
        "avatar_url": agent.avatar_url,
        "status": agent.status,
    }


# ─── Utility functions for setting up management relations ───────────────────

async def assign_department_leader(
    db: AsyncSession,
    manager_member_id: uuid.UUID,
    department_id: uuid.UUID,
    is_primary: bool = True,
    tenant_id: Optional[uuid.UUID] = None,
) -> OrgManagementRelation:
    """Assign a member as leader (or deputy leader) of a department node."""
    # Check if relation already exists
    existing_result = await db.execute(
        select(OrgManagementRelation).where(
            OrgManagementRelation.manager_member_id == manager_member_id,
            OrgManagementRelation.managed_department_id == department_id,
        )
    )
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        existing.is_primary = is_primary
        existing.manager_role = "leader" if is_primary else "deputy_leader"
        return existing
    
    relation = OrgManagementRelation(
        manager_member_id=manager_member_id,
        manager_role="leader" if is_primary else "deputy_leader",
        managed_department_id=department_id,
        is_primary=is_primary,
        tenant_id=tenant_id,
    )
    db.add(relation)
    
    # Update member role
    member_result = await db.execute(
        select(OrgMember).where(OrgMember.id == manager_member_id)
    )
    member = member_result.scalar_one_or_none()
    if member:
        member.member_role = "leader" if is_primary else "deputy_leader"
        member.department_id = department_id
    
    return relation


async def assign_director(
    db: AsyncSession,
    manager_member_id: uuid.UUID,
    department_ids: list[uuid.UUID],
    tenant_id: Optional[uuid.UUID] = None,
) -> list[OrgManagementRelation]:
    """Assign a member as director managing multiple department nodes."""
    relations = []
    for dept_id in department_ids:
        relation = OrgManagementRelation(
            manager_member_id=manager_member_id,
            manager_role="director",
            managed_department_id=dept_id,
            is_primary=False,
            tenant_id=tenant_id,
        )
        db.add(relation)
        relations.append(relation)
    
    # Update member role
    member_result = await db.execute(
        select(OrgMember).where(OrgMember.id == manager_member_id)
    )
    member = member_result.scalar_one_or_none()
    if member:
        member.member_role = "director"
    
    return relations


async def link_user_to_org_member(
    db: AsyncSession,
    user_id: uuid.UUID,
    org_member_id: uuid.UUID,
    is_primary: bool = True,
) -> UserOrgMemberLink:
    """Link a platform user to an org member."""
    link = UserOrgMemberLink(
        user_id=user_id,
        org_member_id=org_member_id,
        is_primary=is_primary,
    )
    db.add(link)
    return link
