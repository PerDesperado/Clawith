# flake8: noqa: F401
"""Models package - exports all SQLAlchemy models."""

# Core models
from app.models.user import User, Department
from app.models.tenant import Tenant
from app.models.agent import Agent, AgentPermission, AgentTemplate

# Organization hierarchy models (new structure)
from app.models.org import (
    OrgDepartment,
    OrgCenter,
    OrgTeam,
    OrgMember,
    OrgManagementRelation,
    UserOrgMemberLink,
    AgentRelationship,
    AgentAgentRelationship,
)

# Tools & Skills
from app.models.tool import Tool, AgentTool
from app.models.skill import Skill, SkillFile
from app.models.llm import LLMModel

# Tasks
from app.models.task import Task, TaskLog
from app.models.team_task import TeamTask, TeamTaskLog, AgentDailyReport
from app.models.schedule import AgentSchedule
from app.models.trigger import AgentTrigger

# Communication
from app.models.notification import Notification
from app.models.channel_config import ChannelConfig
from app.models.gateway_message import GatewayMessage
from app.models.chat_session import ChatSession

# Participant (for chat sessions)
from app.models.participant import Participant

# Plaza (social features)
from app.models.plaza import PlazaPost, PlazaComment, PlazaLike

# User-Agent binding
from app.models.user_agent_binding import UserAgentBinding, DailySummary

# Opportunity tracking
from app.models.opportunity import Opportunity, OpportunityLog

# System
from app.models.invitation_code import InvitationCode
from app.models.activity_log import AgentActivityLog
from app.models.audit import AuditLog, ApprovalRequest, ChatMessage as AuditChatMessage, EnterpriseInfo
from app.models.system_settings import SystemSetting

__all__ = [
    # Core
    "User",
    "Department",
    "Tenant",
    "Agent",
    "AgentPermission",
    "AgentTemplate",
    # Organization hierarchy
    "OrgDepartment",
    "OrgCenter",
    "OrgTeam",
    "OrgMember",
    "OrgManagementRelation",
    "UserOrgMemberLink",
    "AgentRelationship",
    "AgentAgentRelationship",
    # Tools & Skills
    "Tool",
    "AgentTool",
    "Skill",
    "SkillFile",
    "LLMModel",
    # Tasks
    "Task",
    "TaskLog",
    "TeamTask",
    "TeamTaskLog",
    "AgentDailyReport",
    "AgentSchedule",
    "AgentTrigger",
    # Communication
    "Notification",
    "ChannelConfig",
    "GatewayMessage",
    "ChatSession",
    # Participant
    "Participant",
    # Plaza
    "PlazaPost",
    "PlazaComment",
    "PlazaLike",
    # User-Agent binding
    "UserAgentBinding",
    "DailySummary",
    # Opportunity
    "Opportunity",
    "OpportunityLog",
    # System
    "InvitationCode",
    "AgentActivityLog",
    "AuditLog",
    "ApprovalRequest",
    "AuditChatMessage",
    "EnterpriseInfo",
    "SystemSetting",
]
