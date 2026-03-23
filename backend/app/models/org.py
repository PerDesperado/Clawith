"""Organization structure models — Department -> Center -> Team -> Member hierarchy.

Hierarchy:
- Department (部门): 按产品线划分，如云产品一部、云产品二部
- Center (中心): 部门下的中心，如计算中心、存储中心  
- Team (组): 最小管理单位，有正组长和副组长
- Member (员工): 属于某个组

Management Relations (多对多):
- GM 分管多个中心
- 总监 分管多个组
- 组长/副组长 管理组
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class OrgDepartment(Base):
    """Department - 部门 (最高层级，按产品线划分).
    
    Example: 云产品一部、云产品二部、AI产品部
    """

    __tablename__ = "org_departments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feishu_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("org_departments.id"))
    path: Mapped[str] = mapped_column(String(500), default="")
    member_count: Mapped[int] = mapped_column(Integer, default=0)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), index=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    members: Mapped[list["OrgMember"]] = relationship(back_populates="department")
    centers: Mapped[list["OrgCenter"]] = relationship(back_populates="department", cascade="all, delete-orphan")


class OrgCenter(Base):
    """Center - 中心 (中间层级).
    
    Example: IaaS中心、PaaS中心、SaaS中心
    A center belongs to one department.
    One or more Directors can manage teams within a center.
    """

    __tablename__ = "org_centers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org_departments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    department: Mapped["OrgDepartment"] = relationship(back_populates="centers")
    teams: Mapped[list["OrgTeam"]] = relationship(back_populates="center", cascade="all, delete-orphan")


class OrgTeam(Base):
    """Team - 组 (最小管理单位).
    
    Example: CVM组、CBS组、VPC组
    A team belongs to one center.
    Each team has one primary leader (正组长) and zero or more deputy leaders (副组长).
    """

    __tablename__ = "org_teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    center_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org_centers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    center: Mapped["OrgCenter"] = relationship(back_populates="teams")
    members: Mapped[list["OrgMember"]] = relationship(back_populates="team")


class OrgMember(Base):
    """Member - 组织成员/员工.
    
    Roles (member_role):
    - 'member': 普通组员
    - 'deputy_leader': 副组长
    - 'leader': 正组长
    - 'director': 总监
    - 'gm': GM
    - 'platform_admin': 平台管理员
    """

    __tablename__ = "org_members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feishu_open_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    feishu_user_id: Mapped[str | None] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(200))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(200), default="")  # 职位名称
    
    # Legacy department_id (kept for backward compatibility with Feishu sync)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("org_departments.id"))
    department_path: Mapped[str] = mapped_column(String(500), default="")
    
    # New: Team affiliation (组归属)
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org_teams.id", ondelete="SET NULL"), index=True
    )
    
    # Member role in the organization
    member_role: Mapped[str] = mapped_column(String(50), default="member", nullable=False)
    # Values: 'member', 'deputy_leader', 'leader', 'director', 'gm', 'platform_admin'
    
    phone: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="active")
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), index=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    department: Mapped["OrgDepartment | None"] = relationship(back_populates="members")
    team: Mapped["OrgTeam | None"] = relationship(back_populates="members")
    
    # Management relations (what this member manages)
    management_relations: Mapped[list["OrgManagementRelation"]] = relationship(
        back_populates="manager", foreign_keys="OrgManagementRelation.manager_member_id"
    )


class OrgManagementRelation(Base):
    """Management relation - 多对多管理关系.
    
    Defines who manages what:
    - GM manages Centers (GM 分管中心)
    - Director manages Teams (总监 分管组)
    - Leader/Deputy Leader manages Team (组长/副组长 管理组)
    
    manager_role values: 'gm', 'director', 'leader', 'deputy_leader'
    
    One of managed_department_id, managed_center_id, managed_team_id must be set.
    is_primary distinguishes 正组长 (True) from 副组长 (False).
    """

    __tablename__ = "org_management_relations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Manager info
    manager_member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org_members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    manager_role: Mapped[str] = mapped_column(String(50), nullable=False)
    # Values: 'gm', 'director', 'leader', 'deputy_leader'
    
    # Managed entity (one of these must be set)
    managed_department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org_departments.id", ondelete="CASCADE"), index=True
    )
    managed_center_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org_centers.id", ondelete="CASCADE"), index=True
    )
    managed_team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org_teams.id", ondelete="CASCADE"), index=True
    )
    
    # Is this the primary manager? (正组长 vs 副组长)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    manager: Mapped["OrgMember"] = relationship(back_populates="management_relations", foreign_keys=[manager_member_id])
    managed_department: Mapped["OrgDepartment | None"] = relationship(foreign_keys=[managed_department_id])
    managed_center: Mapped["OrgCenter | None"] = relationship(foreign_keys=[managed_center_id])
    managed_team: Mapped["OrgTeam | None"] = relationship(foreign_keys=[managed_team_id])


class UserOrgMemberLink(Base):
    """Link between platform User and OrgMember.
    
    Allows a platform user to be associated with one or more org members.
    This is used for permission checking.
    """

    __tablename__ = "user_org_member_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    org_member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org_members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    org_member: Mapped["OrgMember"] = relationship(foreign_keys=[org_member_id])


# ─── Legacy Models (kept for backward compatibility) ───────────────────────

class AgentRelationship(Base):
    """Relationship between an agent and an org member."""

    __tablename__ = "agent_relationships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("org_members.id"), nullable=False)
    relation: Mapped[str] = mapped_column(String(50), nullable=False, default="collaborator")
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    member: Mapped["OrgMember"] = relationship()


class AgentAgentRelationship(Base):
    """Relationship between two agents (digital employees)."""

    __tablename__ = "agent_agent_relationships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    target_agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    relation: Mapped[str] = mapped_column(String(50), nullable=False, default="collaborator")
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    target_agent = relationship("Agent", foreign_keys=[target_agent_id])
