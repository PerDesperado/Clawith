"""Team Task models for team collaboration and task management."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.org import OrgMember
    from app.models.user import User


class TeamTask(Base):
    """
    Team-level task that can be assigned to human members or digital employees.
    Supports hierarchical task decomposition by AI agents.
    """

    __tablename__ = "team_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Task content
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    
    # Task hierarchy
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("team_tasks.id"), nullable=True
    )
    root_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("team_tasks.id"), nullable=True
    )
    
    # Task type
    task_type: Mapped[str] = mapped_column(
        Enum("direct", "decomposed", "subtask", name="team_task_type_enum", create_constraint=False),
        default="direct",
        nullable=False,
    )  # direct: 直接下发, decomposed: 已拆解的父任务, subtask: 拆解后的子任务
    
    # Status
    status: Mapped[str] = mapped_column(
        Enum("pending", "in_progress", "completed", "cancelled", name="team_task_status_enum", create_constraint=False),
        default="pending",
        nullable=False,
    )
    
    # Priority
    priority: Mapped[str] = mapped_column(
        Enum("low", "medium", "high", "urgent", name="team_task_priority_enum", create_constraint=False),
        default="medium",
        nullable=False,
    )
    
    # Assignment - Creator (who created/assigned the task)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_by_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )
    
    # Assignment - Assignee (who should complete the task)
    assignee_type: Mapped[str] = mapped_column(
        Enum("user", "member", "agent", name="assignee_type_enum", create_constraint=False),
        default="member",
        nullable=False,
    )  # user: 平台用户, member: 组织成员, agent: 数字员工
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    assignee_member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("org_members.id"), nullable=True
    )
    assignee_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )
    
    # Dates
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    
    # Progress tracking
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    progress_note: Mapped[str | None] = mapped_column(Text)
    
    # Visibility/Permission control
    visibility: Mapped[str] = mapped_column(
        Enum("private", "team", "department", "public", name="task_visibility_enum", create_constraint=False),
        default="team",
        nullable=False,
    )  # private: 仅自己和组长, team: 团队可见, department: 部门可见, public: 全公司
    visible_to_user_ids: Mapped[list | None] = mapped_column(JSON, default=list)  # 额外可见的用户ID列表
    
    # Tenant isolation
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True
    )
    
    # AI processing metadata
    decomposition_prompt: Mapped[str | None] = mapped_column(Text)  # 用于拆解任务的提示词
    decomposition_result: Mapped[dict | None] = mapped_column(JSON)  # AI拆解结果
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    parent_task: Mapped["TeamTask | None"] = relationship(
        "TeamTask", remote_side="TeamTask.id", foreign_keys=[parent_task_id], back_populates="subtasks"
    )
    subtasks: Mapped[list["TeamTask"]] = relationship(
        "TeamTask", foreign_keys=[parent_task_id], back_populates="parent_task"
    )
    
    creator_user: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_user_id])
    creator_agent: Mapped["Agent | None"] = relationship("Agent", foreign_keys=[created_by_agent_id])
    
    assignee_user: Mapped["User | None"] = relationship("User", foreign_keys=[assignee_user_id])
    assignee_member: Mapped["OrgMember | None"] = relationship("OrgMember", foreign_keys=[assignee_member_id])
    assignee_agent: Mapped["Agent | None"] = relationship("Agent", foreign_keys=[assignee_agent_id])
    
    logs: Mapped[list["TeamTaskLog"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class TeamTaskLog(Base):
    """Progress log entry for a team task."""

    __tablename__ = "team_task_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("team_tasks.id"), nullable=False)
    
    # Who created this log
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_by_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )
    
    log_type: Mapped[str] = mapped_column(
        Enum("progress", "comment", "status_change", "assignment", name="task_log_type_enum", create_constraint=False),
        default="progress",
        nullable=False,
    )
    
    content: Mapped[str] = mapped_column(Text, nullable=False)
    extra_data: Mapped[dict | None] = mapped_column(JSON)  # 额外信息，如状态变更详情
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    task: Mapped["TeamTask"] = relationship(back_populates="logs")
    creator_user: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_user_id])
    creator_agent: Mapped["Agent | None"] = relationship("Agent", foreign_keys=[created_by_agent_id])


class AgentDailyReport(Base):
    """
    Daily work report for a digital employee (Agent).
    Automatically generated or manually created by the agent.
    """

    __tablename__ = "agent_daily_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    
    report_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # Report content
    summary: Mapped[str | None] = mapped_column(Text)  # 工作总结
    completed_tasks: Mapped[list | None] = mapped_column(JSON, default=list)  # 完成的任务列表
    in_progress_tasks: Mapped[list | None] = mapped_column(JSON, default=list)  # 进行中的任务
    planned_tasks: Mapped[list | None] = mapped_column(JSON, default=list)  # 计划中的任务
    blockers: Mapped[list | None] = mapped_column(JSON, default=list)  # 阻塞项
    highlights: Mapped[list | None] = mapped_column(JSON, default=list)  # 亮点/成就
    
    # Statistics
    tasks_completed_count: Mapped[int] = mapped_column(Integer, default=0)
    tasks_in_progress_count: Mapped[int] = mapped_column(Integer, default=0)
    messages_sent: Mapped[int] = mapped_column(Integer, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    
    # Visibility
    visibility: Mapped[str] = mapped_column(
        Enum("private", "leader", "team", "department", "public", name="report_visibility_enum", create_constraint=False),
        default="leader",
        nullable=False,
    )  # leader: 组长可见
    
    # Generation info
    is_auto_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    
    # Review / publish workflow
    report_status: Mapped[str] = mapped_column(
        String(20), default="draft", nullable=False, server_default="draft",
    )  # draft → pending_review → published
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewer_comment: Mapped[str | None] = mapped_column(Text)
    
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True
    )
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    agent: Mapped["Agent"] = relationship("Agent")
    confirmed_by: Mapped["User | None"] = relationship("User", foreign_keys=[confirmed_by_user_id])
