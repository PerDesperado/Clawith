"""User Management API — Admin creates users with org structure assignment.

Flow:
1. Admin creates user → sets username, initial password, org assignment (team + role)
2. User logs in with initial credentials → must_change_password = True
3. User changes password → must_change_password = False
"""

import secrets
import string
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, hash_password
from app.database import get_db
from app.models.user import User
from app.models.org import OrgMember, OrgDepartment, OrgManagementRelation, UserOrgMemberLink

router = APIRouter(prefix="/user-management", tags=["user-management"])


# ─── Request/Response Schemas ───────────────────────────

class AdminCreateUserRequest(BaseModel):
    """Admin creates a new user account."""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    display_name: str = Field(..., min_length=1, max_length=100)
    
    # Optional: auto-generate password if not provided
    password: str | None = Field(None, min_length=6, max_length=100)
    
    # Organization structure assignment
    team_id: str | None = None  # Which team the user belongs to
    member_role: str = "member"  # member, deputy_leader, leader, director, gm
    title: str = ""  # Job title
    phone: str | None = None
    
    # Platform role
    platform_role: str = "member"  # platform_admin, org_admin, agent_admin, member


class AdminUpdateUserRequest(BaseModel):
    """Admin updates a user account."""
    display_name: str | None = None
    email: EmailStr | None = None
    title: str | None = None
    phone: str | None = None
    
    # Organization structure
    team_id: str | None = None
    member_role: str | None = None
    
    # Platform role
    platform_role: str | None = None
    
    # Account status
    is_active: bool | None = None


class ResetPasswordRequest(BaseModel):
    """Admin resets a user's password."""
    new_password: str | None = None  # If None, generate random password


class UserDetailOut(BaseModel):
    """Detailed user info including org structure."""
    id: str
    username: str
    email: str
    display_name: str
    avatar_url: str | None
    
    # Platform role
    platform_role: str
    is_active: bool
    must_change_password: bool
    
    # Organization info
    org_member_id: str | None
    team_id: str | None
    team_name: str | None
    center_id: str | None
    center_name: str | None
    department_id: str | None
    department_name: str | None
    member_role: str | None
    title: str | None
    phone: str | None
    
    # Timestamps
    created_at: str | None
    last_login_at: str | None


class CreateUserResponse(BaseModel):
    """Response after creating a user."""
    user: UserDetailOut
    initial_password: str  # Only shown once after creation


# ─── Helper Functions ───────────────────────────────────

def _require_admin(current_user: User) -> None:
    """Check that the user is admin."""
    if current_user.role not in ("platform_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Requires admin privileges")


def _generate_password(length: int = 12) -> str:
    """Generate a random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


async def _get_user_detail(
    db: AsyncSession, user: User, tenant_id: uuid.UUID | None
) -> UserDetailOut:
    """Build detailed user info including org structure."""
    # Find linked org member
    link_result = await db.execute(
        select(UserOrgMemberLink)
        .where(UserOrgMemberLink.user_id == user.id, UserOrgMemberLink.is_primary == True)
    )
    link = link_result.scalar_one_or_none()
    
    org_member = None
    department = None
    
    if link:
        member_result = await db.execute(
            select(OrgMember).where(OrgMember.id == link.org_member_id)
        )
        org_member = member_result.scalar_one_or_none()
        
        # Get department info (using OrgDepartment hierarchy)
        if org_member and org_member.department_id:
            dept_result = await db.execute(
                select(OrgDepartment).where(OrgDepartment.id == org_member.department_id)
            )
            department = dept_result.scalar_one_or_none()
    
    return UserDetailOut(
        id=str(user.id),
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        platform_role=user.role,
        is_active=user.is_active,
        must_change_password=getattr(user, 'must_change_password', False),
        org_member_id=str(org_member.id) if org_member else None,
        # For backward compatibility, use department as "team" in output
        team_id=str(department.id) if department else None,
        team_name=department.name if department else None,
        center_id=None,  # No longer using separate center table
        center_name=None,
        department_id=str(department.id) if department else None,
        department_name=org_member.department_path if org_member else None,
        member_role=org_member.member_role if org_member else None,
        title=org_member.title if org_member else user.title,
        phone=org_member.phone if org_member else None,
        created_at=user.created_at.isoformat() if user.created_at else None,
        last_login_at=None,  # TODO: track last login
    )


# ─── API Endpoints ──────────────────────────────────────

@router.post("/users", response_model=CreateUserResponse, status_code=status.HTTP_201_CREATED)
async def admin_create_user(
    data: AdminCreateUserRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin creates a new user account.
    
    Flow:
    1. Creates User record with must_change_password=True
    2. Creates OrgMember record
    3. Links User to OrgMember
    4. Returns user info + initial password (only shown once)
    
    The user must change their password on first login.
    """
    _require_admin(current_user)
    
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="Admin has no company assigned")
    
    # Check username/email uniqueness
    existing = await db.execute(
        select(User).where((User.username == data.username) | (User.email == data.email))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username or email already exists")
    
    # Generate password if not provided
    initial_password = data.password or _generate_password()
    
    # Validate platform role
    valid_roles = {"platform_admin", "org_admin", "agent_admin", "member"}
    if data.platform_role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid platform_role. Must be one of: {valid_roles}")
    
    # Only platform_admin can create other platform_admins
    if data.platform_role == "platform_admin" and current_user.role != "platform_admin":
        raise HTTPException(status_code=403, detail="Only platform admin can create other platform admins")
    
    # Validate member role
    valid_member_roles = {"member", "deputy_leader", "leader", "director", "gm", "platform_admin"}
    if data.member_role not in valid_member_roles:
        raise HTTPException(status_code=400, detail=f"Invalid member_role. Must be one of: {valid_member_roles}")
    
    # Validate org node exists if provided (now using OrgDepartment hierarchy)
    org_node = None
    dept_path = ""
    if data.team_id:
        # team_id now actually refers to an OrgDepartment node (any level in hierarchy)
        node_result = await db.execute(
            select(OrgDepartment).where(OrgDepartment.id == uuid.UUID(data.team_id))
        )
        org_node = node_result.scalar_one_or_none()
        if not org_node:
            raise HTTPException(status_code=404, detail="Organization node not found")
        # Build the department path
        dept_path = org_node.path or org_node.name
    
    # Create User
    user = User(
        username=data.username,
        email=data.email,
        password_hash=hash_password(initial_password),
        display_name=data.display_name,
        role=data.platform_role,
        tenant_id=current_user.tenant_id,
        title=data.title,
        must_change_password=True,  # Force password change on first login
    )
    db.add(user)
    await db.flush()
    
    # Create OrgMember (use department_id instead of team_id for OrgDepartment hierarchy)
    org_member = OrgMember(
        name=data.display_name,
        email=data.email,
        title=data.title,
        phone=data.phone,
        department_id=org_node.id if org_node else None,
        department_path=dept_path,
        member_role=data.member_role,
        tenant_id=current_user.tenant_id,
        status="active",
    )
    db.add(org_member)
    await db.flush()
    
    # Link User to OrgMember
    link = UserOrgMemberLink(
        user_id=user.id,
        org_member_id=org_member.id,
        is_primary=True,
    )
    db.add(link)
    
    # If member is a leader/deputy_leader/director, create management relation
    if data.member_role in ("leader", "deputy_leader", "director") and org_node:
        mgmt_relation = OrgManagementRelation(
            manager_member_id=org_member.id,
            manager_role=data.member_role,
            managed_department_id=org_node.id,  # Use department instead of team
            is_primary=(data.member_role == "leader"),
            tenant_id=current_user.tenant_id,
        )
        db.add(mgmt_relation)
    
    # Create Participant identity
    from app.models.participant import Participant
    db.add(Participant(
        type="user", ref_id=user.id,
        display_name=user.display_name, avatar_url=user.avatar_url,
    ))
    
    await db.commit()
    
    # Get full user detail
    user_detail = await _get_user_detail(db, user, current_user.tenant_id)
    
    return CreateUserResponse(
        user=user_detail,
        initial_password=initial_password,
    )


@router.get("/users", response_model=list[UserDetailOut])
async def list_users_with_org(
    search: str | None = None,
    team_id: str | None = None,
    member_role: str | None = None,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all users with their organization info.
    
    Supports filtering by:
    - search: Search in username, email, display_name
    - team_id: Filter by team
    - member_role: Filter by org role (member, leader, etc.)
    """
    _require_admin(current_user)
    
    query = select(User).where(User.tenant_id == current_user.tenant_id)
    
    if search:
        search_filter = f"%{search}%"
        query = query.where(
            (User.username.ilike(search_filter)) |
            (User.email.ilike(search_filter)) |
            (User.display_name.ilike(search_filter))
        )
    
    # Get all users first
    query = query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    users = result.scalars().all()
    
    # Build detailed response
    user_details = []
    for user in users:
        detail = await _get_user_detail(db, user, current_user.tenant_id)
        
        # Apply team/role filters (post-fetch filtering since it requires joins)
        if team_id and detail.team_id != team_id:
            continue
        if member_role and detail.member_role != member_role:
            continue
        
        user_details.append(detail)
    
    return user_details


@router.get("/users/{user_id}", response_model=UserDetailOut)
async def get_user_detail(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed info for a specific user."""
    _require_admin(current_user)
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Cannot view users outside your organization")
    
    return await _get_user_detail(db, user, current_user.tenant_id)


@router.patch("/users/{user_id}", response_model=UserDetailOut)
async def update_user(
    user_id: uuid.UUID,
    data: AdminUpdateUserRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin updates a user's profile and organization assignment.
    """
    _require_admin(current_user)
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Cannot modify users outside your organization")
    
    # Cannot demote platform_admin unless you're also platform_admin
    if user.role == "platform_admin" and data.platform_role and data.platform_role != "platform_admin":
        if current_user.role != "platform_admin":
            raise HTTPException(status_code=403, detail="Only platform admin can demote other platform admins")
    
    # Update User fields
    if data.display_name is not None:
        user.display_name = data.display_name
    if data.email is not None:
        # Check email uniqueness
        existing = await db.execute(
            select(User).where(User.email == data.email, User.id != user_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Email already in use")
        user.email = data.email
    if data.title is not None:
        user.title = data.title
    if data.platform_role is not None:
        user.role = data.platform_role
    if data.is_active is not None:
        user.is_active = data.is_active
    
    # Update OrgMember
    link_result = await db.execute(
        select(UserOrgMemberLink)
        .where(UserOrgMemberLink.user_id == user_id, UserOrgMemberLink.is_primary == True)
    )
    link = link_result.scalar_one_or_none()
    
    if link:
        member_result = await db.execute(
            select(OrgMember).where(OrgMember.id == link.org_member_id)
        )
        org_member = member_result.scalar_one_or_none()
        
        if org_member:
            if data.display_name is not None:
                org_member.name = data.display_name
            if data.email is not None:
                org_member.email = data.email
            if data.title is not None:
                org_member.title = data.title
            if data.phone is not None:
                org_member.phone = data.phone
            
            old_team_id = org_member.team_id
            old_role = org_member.member_role
            
            if data.team_id is not None:
                if data.team_id:
                    team_result = await db.execute(
                        select(OrgTeam).where(OrgTeam.id == uuid.UUID(data.team_id))
                    )
                    team = team_result.scalar_one_or_none()
                    if not team:
                        raise HTTPException(status_code=404, detail="Team not found")
                    org_member.team_id = team.id
                else:
                    org_member.team_id = None
            
            if data.member_role is not None:
                org_member.member_role = data.member_role
            
            # Update management relations if role/team changed
            new_team_id = org_member.team_id
            new_role = org_member.member_role
            
            if (old_team_id != new_team_id or old_role != new_role):
                # Remove old management relations
                from sqlalchemy import delete as sa_delete
                await db.execute(
                    sa_delete(OrgManagementRelation)
                    .where(OrgManagementRelation.manager_member_id == org_member.id)
                )
                
                # Add new management relation if applicable
                if new_role in ("leader", "deputy_leader") and new_team_id:
                    mgmt_relation = OrgManagementRelation(
                        manager_member_id=org_member.id,
                        manager_role=new_role,
                        managed_team_id=new_team_id,
                        is_primary=(new_role == "leader"),
                        tenant_id=current_user.tenant_id,
                    )
                    db.add(mgmt_relation)
    
    await db.commit()
    
    return await _get_user_detail(db, user, current_user.tenant_id)


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: uuid.UUID,
    data: ResetPasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin resets a user's password.
    
    Returns the new password (only shown once).
    Sets must_change_password=True so user must change it on next login.
    """
    _require_admin(current_user)
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Cannot modify users outside your organization")
    
    # Cannot reset platform_admin password unless you're also platform_admin
    if user.role == "platform_admin" and current_user.role != "platform_admin":
        raise HTTPException(status_code=403, detail="Only platform admin can reset other platform admin passwords")
    
    # Generate or use provided password
    new_password = data.new_password or _generate_password()
    
    user.password_hash = hash_password(new_password)
    user.must_change_password = True
    
    await db.commit()
    
    return {
        "message": "Password reset successfully",
        "new_password": new_password,
        "must_change_password": True,
    }


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin deletes a user account.
    
    This also removes the linked OrgMember and any management relations.
    """
    _require_admin(current_user)
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Cannot delete users outside your organization")
    
    # Cannot delete yourself
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    
    # Cannot delete platform_admin unless you're also platform_admin
    if user.role == "platform_admin" and current_user.role != "platform_admin":
        raise HTTPException(status_code=403, detail="Only platform admin can delete other platform admins")
    
    # Delete linked OrgMember and relations
    link_result = await db.execute(
        select(UserOrgMemberLink).where(UserOrgMemberLink.user_id == user_id)
    )
    links = link_result.scalars().all()
    
    from sqlalchemy import delete as sa_delete
    
    for link in links:
        # Delete management relations for this member
        await db.execute(
            sa_delete(OrgManagementRelation)
            .where(OrgManagementRelation.manager_member_id == link.org_member_id)
        )
        # Delete the org member
        await db.execute(
            sa_delete(OrgMember).where(OrgMember.id == link.org_member_id)
        )
    
    # Delete all user-org links
    await db.execute(
        sa_delete(UserOrgMemberLink).where(UserOrgMemberLink.user_id == user_id)
    )
    
    # Delete participant
    from app.models.participant import Participant
    await db.execute(
        sa_delete(Participant).where(Participant.ref_id == user_id, Participant.type == "user")
    )
    
    # Delete user
    await db.delete(user)
    await db.commit()


# ─── Organization Structure Endpoints ───────────────────

@router.get("/org/teams")
async def list_teams_for_assignment(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all org nodes available for user assignment.
    
    Uses OrgDepartment table which is a hierarchical self-referencing tree structure.
    Returns flat list of nodes with their full paths for easy selection.
    """
    _require_admin(current_user)
    
    # Get all org departments (nodes) for this tenant
    dept_result = await db.execute(
        select(OrgDepartment)
        .where(OrgDepartment.tenant_id == current_user.tenant_id)
        .order_by(OrgDepartment.name)
    )
    departments = list(dept_result.scalars().all())
    
    # Build a lookup dict for constructing paths
    dept_map = {d.id: d for d in departments}
    
    def build_path(dept):
        """Build full path for a department (e.g., '云产品一部 / 计算产品中心 / 分布式云产品组')"""
        path_parts = [dept.name]
        parent_id = dept.parent_id
        while parent_id and parent_id in dept_map:
            parent = dept_map[parent_id]
            path_parts.insert(0, parent.name)
            parent_id = parent.parent_id
        return " / ".join(path_parts)
    
    # Build hierarchical structure for frontend dropdown
    # The frontend expects: departments -> centers -> teams
    # But we have a flat tree, so we'll reorganize:
    # - Level 0 (no parent) = Department
    # - Level 1 (parent is root) = Center
    # - Level 2+ = Team/Sub-unit
    
    root_depts = [d for d in departments if d.parent_id is None]
    
    result = []
    for root in root_depts:
        # Find children of this root (centers)
        children = [d for d in departments if d.parent_id == root.id]
        
        center_list = []
        for child in children:
            # Find children of this child (teams)
            grandchildren = [d for d in departments if d.parent_id == child.id]
            
            if grandchildren:
                # This is a center with teams
                center_list.append({
                    "id": str(child.id),
                    "name": child.name,
                    "teams": [
                        {"id": str(gc.id), "name": gc.name}
                        for gc in grandchildren
                    ],
                })
            else:
                # This is a leaf node (treat as a team under a virtual "默认中心")
                # Or it could be a center with no teams yet
                center_list.append({
                    "id": str(child.id),
                    "name": child.name,
                    "teams": [],
                })
        
        # If root has no children, it's a standalone department
        # Add it as a selectable item with empty centers
        result.append({
            "id": str(root.id),
            "name": root.name,
            "centers": center_list,
        })
    
    return result


@router.get("/org/roles")
async def list_available_roles(
    current_user: User = Depends(get_current_user),
):
    """List available organization roles."""
    return {
        "platform_roles": [
            {"value": "platform_admin", "label": "平台管理员", "description": "最高权限，管理所有租户"},
            {"value": "org_admin", "label": "组织管理员", "description": "管理本公司用户和配置"},
            {"value": "agent_admin", "label": "Agent管理员", "description": "创建和管理Agent"},
            {"value": "member", "label": "普通成员", "description": "使用Agent"},
        ],
        "member_roles": [
            {"value": "platform_admin", "label": "平台管理员", "description": "可查看所有数据"},
            {"value": "gm", "label": "GM", "description": "分管多个中心"},
            {"value": "director", "label": "总监", "description": "分管多个组"},
            {"value": "leader", "label": "正组长", "description": "管理一个组"},
            {"value": "deputy_leader", "label": "副组长", "description": "协助组长管理"},
            {"value": "member", "label": "组员", "description": "普通组员"},
        ],
    }
