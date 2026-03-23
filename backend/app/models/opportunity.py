"""Business Opportunity (商机) model — shared across all digital employees."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.user import User


class Opportunity(Base):
    """
    Business opportunity record.

    All digital employees share this single table.
    An agent can create entries via the ``record_opportunity`` tool,
    and the dedicated "opportunity analyst" agent can read & analyse them.
    """

    __tablename__ = "opportunities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )

    # ── Core fields ──────────────────────────────────────
    customer_name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    visit_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    solution: Mapped[str | None] = mapped_column(Text)            # 讨论方案
    project_duration: Mapped[str | None] = mapped_column(String(200))  # e.g. "6个月"
    project_scale: Mapped[str | None] = mapped_column(String(200))     # e.g. "1000~2000万"
    visit_summary: Mapped[str | None] = mapped_column(Text)       # 拜访纪要
    contact_person: Mapped[str | None] = mapped_column(String(200))    # 客户联系人
    contact_info: Mapped[str | None] = mapped_column(String(300))      # 联系方式

    # ── Pipeline management ──────────────────────────────
    stage: Mapped[str] = mapped_column(
        String(50), default="initial_contact", nullable=False,
    )  # initial_contact → demand_confirmed → proposal → negotiation → won → lost
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    estimated_amount: Mapped[float | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(10), default="CNY", nullable=False)
    win_probability: Mapped[int | None] = mapped_column(Integer)  # 0-100

    # ── Follow-up / risk ─────────────────────────────────
    next_action: Mapped[str | None] = mapped_column(Text)         # 下一步行动
    next_action_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    risk_flag: Mapped[str | None] = mapped_column(String(50))     # none / low / medium / high
    risk_note: Mapped[str | None] = mapped_column(Text)

    # ── Extra / free-form ────────────────────────────────
    tags: Mapped[list | None] = mapped_column(JSON, default=list)
    extra_data: Mapped[dict | None] = mapped_column(JSON, default=dict)
    raw_input: Mapped[str | None] = mapped_column(Text)  # 原始用户输入

    # ── Ownership ────────────────────────────────────────
    created_by_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True,
    )

    # ── Timestamps ───────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    # ── Relationships ────────────────────────────────────
    created_by_agent: Mapped["Agent | None"] = relationship(
        "Agent", foreign_keys=[created_by_agent_id],
    )
    created_by_user: Mapped["User | None"] = relationship(
        "User", foreign_keys=[created_by_user_id],
    )


class OpportunityLog(Base):
    """Audit trail for opportunity changes (stage transitions, follow-ups, etc.)."""

    __tablename__ = "opportunity_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    log_type: Mapped[str] = mapped_column(String(50), nullable=False)  # stage_change / follow_up / risk_alert / note
    content: Mapped[str] = mapped_column(Text, nullable=False)
    extra_data: Mapped[dict | None] = mapped_column(JSON, default=dict)

    created_by_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    opportunity: Mapped["Opportunity"] = relationship("Opportunity")
