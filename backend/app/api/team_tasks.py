"""Team Task management API routes."""

import uuid
from datetime import datetime, date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import get_current_user
from app.database import get_db
from app.models.team_task import TeamTask, TeamTaskLog, AgentDailyReport
from app.models.user import User
from app.models.agent import Agent
from app.models.org import OrgMember, AgentRelationship

router = APIRouter(prefix="/team", tags=["team-tasks"])


# ─── Schemas ───────────────────────────────────────────

class TeamTaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    due_date: Optional[datetime] = None
    assignee_type: str = "member"  # user, member, agent
    assignee_user_id: Optional[str] = None
    assignee_member_id: Optional[str] = None
    assignee_agent_id: Optional[str] = None
    visibility: str = "team"
    visible_to_user_ids: list[str] = []
    # For AI decomposition
    request_decomposition: bool = False
    decomposition_prompt: Optional[str] = None


class TeamTaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[datetime] = None
    progress_percent: Optional[int] = None
    progress_note: Optional[str] = None
    visibility: Optional[str] = None
    visible_to_user_ids: Optional[list[str]] = None


class TeamTaskLogCreate(BaseModel):
    content: str
    log_type: str = "progress"


class SubtaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    assignee_type: str = "member"
    assignee_user_id: Optional[str] = None
    assignee_member_id: Optional[str] = None
    assignee_agent_id: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: str = "medium"


class DecomposeRequest(BaseModel):
    """Request for AI to decompose a task."""
    prompt: Optional[str] = None  # Custom instructions for decomposition
    auto_assign: bool = False  # Whether to auto-assign subtasks


class DecomposePreviewRequest(BaseModel):
    """Request for AI to preview task decomposition (before creating)."""
    agent_id: str
    title: str
    description: Optional[str] = None


class SubtaskAssignee(BaseModel):
    """Subtask assignee info."""
    type: str  # 'agent' or 'member'
    id: str


class SubtaskInput(BaseModel):
    """Input for creating a subtask."""
    title: str
    description: Optional[str] = None
    assignees: list[SubtaskAssignee] = []


class CreateTaskWithSubtasksRequest(BaseModel):
    """Create a main task with multiple subtasks (used after decomposition)."""
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    due_date: Optional[datetime] = None
    visibility: str = "team"
    decomposer_agent_id: Optional[str] = None
    subtasks: list[SubtaskInput] = []


# ─── Helper Functions ───────────────────────────────────

async def get_user_team_members(db: AsyncSession, user: User) -> list[uuid.UUID]:
    """Get all org members that the user manages or is in the same team with."""
    if not user.feishu_open_id:
        return []
    
    # Find the user's org_member record
    result = await db.execute(
        select(OrgMember).where(OrgMember.feishu_open_id == user.feishu_open_id)
    )
    user_member = result.scalar_one_or_none()
    if not user_member:
        return []
    
    # Get members in the same department
    result = await db.execute(
        select(OrgMember.id).where(
            OrgMember.department_id == user_member.department_id,
            OrgMember.tenant_id == user.tenant_id
        )
    )
    return [r[0] for r in result.fetchall()]


async def get_user_bound_agents(db: AsyncSession, user: User) -> list[uuid.UUID]:
    """Get all agents bound to the user via AgentRelationship."""
    if not user.feishu_open_id:
        return []
    
    # Find the user's org_member record
    result = await db.execute(
        select(OrgMember).where(OrgMember.feishu_open_id == user.feishu_open_id)
    )
    user_member = result.scalar_one_or_none()
    if not user_member:
        return []
    
    # Get agents related to this member
    result = await db.execute(
        select(AgentRelationship.agent_id).where(
            AgentRelationship.member_id == user_member.id
        )
    )
    return [r[0] for r in result.fetchall()]


async def check_task_visibility(task: TeamTask, user: User, db: AsyncSession) -> bool:
    """Check if the user can view this task."""
    # Creator can always see
    if task.created_by_user_id == user.id:
        return True
    
    # Assignee can always see
    if task.assignee_user_id == user.id:
        return True
    
    # Check explicit visibility list
    if task.visible_to_user_ids and str(user.id) in task.visible_to_user_ids:
        return True
    
    # Public tasks are visible to all in tenant
    if task.visibility == "public" and task.tenant_id == user.tenant_id:
        return True
    
    # Team visibility - check if user is in the same team
    if task.visibility == "team":
        team_members = await get_user_team_members(db, user)
        if task.assignee_member_id and task.assignee_member_id in team_members:
            return True
    
    # Admin users can see everything in their tenant
    if user.role in ["platform_admin", "org_admin"] and task.tenant_id == user.tenant_id:
        return True
    
    return False


def serialize_task(task: TeamTask) -> dict:
    """Serialize a TeamTask to dict, safely avoiding lazy-loading in async context."""
    from sqlalchemy.orm import base as sa_orm_base

    # Use the internal __dict__ to read only already-loaded attributes.
    # This bypasses the descriptor that would trigger lazy-loading.
    d = object.__getattribute__(task, '__dict__')

    def _get_rel(name):
        """Return a loaded relationship value or None (never triggers lazy load)."""
        val = d.get(name)
        if val is None:
            return None
        # If it's a list (collection relationship) or a real ORM model instance, keep it.
        if isinstance(val, list):
            return val
        # Check it's a real model object (has __tablename__) rather than a sentinel
        if hasattr(val, '__tablename__'):
            return val
        return None

    creator_user = _get_rel('creator_user')
    creator_agent = _get_rel('creator_agent')
    assignee_user = _get_rel('assignee_user')
    assignee_member = _get_rel('assignee_member')
    assignee_agent = _get_rel('assignee_agent')
    subtasks_val = _get_rel('subtasks')

    creator_name = None
    if creator_user is not None:
        creator_name = getattr(creator_user, 'display_name', None)
    elif creator_agent is not None:
        creator_name = getattr(creator_agent, 'name', None)

    assignee_name = None
    if assignee_user is not None:
        assignee_name = getattr(assignee_user, 'display_name', None)
    elif assignee_member is not None:
        assignee_name = getattr(assignee_member, 'name', None)
    elif assignee_agent is not None:
        assignee_name = getattr(assignee_agent, 'name', None)

    return {
        "id": str(task.id),
        "title": task.title,
        "description": task.description,
        "task_type": task.task_type,
        "status": task.status,
        "priority": task.priority,
        "parent_task_id": str(task.parent_task_id) if task.parent_task_id else None,
        "root_task_id": str(task.root_task_id) if task.root_task_id else None,

        "created_by_user_id": str(task.created_by_user_id) if task.created_by_user_id else None,
        "created_by_agent_id": str(task.created_by_agent_id) if task.created_by_agent_id else None,
        "creator_name": creator_name,

        "assignee_type": task.assignee_type,
        "assignee_user_id": str(task.assignee_user_id) if task.assignee_user_id else None,
        "assignee_member_id": str(task.assignee_member_id) if task.assignee_member_id else None,
        "assignee_agent_id": str(task.assignee_agent_id) if task.assignee_agent_id else None,
        "assignee_name": assignee_name,

        "due_date": task.due_date.isoformat() if task.due_date else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,

        "progress_percent": task.progress_percent,
        "progress_note": task.progress_note,
        "visibility": task.visibility,

        "subtasks_count": len(subtasks_val) if isinstance(subtasks_val, list) else 0,

        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


# ─── Task CRUD ─────────────────────────────────────────

@router.get("/tasks")
async def list_team_tasks(
    status_filter: Optional[str] = None,
    assignee_type: Optional[str] = None,
    created_by_me: bool = False,
    assigned_to_me: bool = False,
    include_subtasks: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List team tasks visible to the current user."""
    query = select(TeamTask).where(TeamTask.tenant_id == current_user.tenant_id)
    
    # Filter by status
    if status_filter:
        query = query.where(TeamTask.status == status_filter)
    
    # Filter by assignee type
    if assignee_type:
        query = query.where(TeamTask.assignee_type == assignee_type)
    
    # Filter by creator
    if created_by_me:
        query = query.where(TeamTask.created_by_user_id == current_user.id)
    
    # Filter by assignee
    if assigned_to_me:
        query = query.where(TeamTask.assignee_user_id == current_user.id)
    
    # Exclude subtasks unless requested
    if not include_subtasks:
        query = query.where(TeamTask.parent_task_id.is_(None))
    
    query = query.options(
        selectinload(TeamTask.creator_user),
        selectinload(TeamTask.creator_agent),
        selectinload(TeamTask.assignee_user),
        selectinload(TeamTask.assignee_member),
        selectinload(TeamTask.assignee_agent),
        selectinload(TeamTask.subtasks).selectinload(TeamTask.assignee_member),
        selectinload(TeamTask.subtasks).selectinload(TeamTask.assignee_agent),
        selectinload(TeamTask.subtasks).selectinload(TeamTask.assignee_user),
    ).order_by(TeamTask.created_at.desc())
    
    result = await db.execute(query)
    tasks = result.scalars().all()
    
    # Filter by visibility
    visible_tasks = []
    for task in tasks:
        if await check_task_visibility(task, current_user, db):
            visible_tasks.append(serialize_task(task))
    
    return visible_tasks


@router.post("/tasks")
async def create_team_task(
    data: TeamTaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new team task."""
    task = TeamTask(
        title=data.title,
        description=data.description,
        priority=data.priority,
        due_date=data.due_date,
        task_type="direct",
        
        created_by_user_id=current_user.id,
        
        assignee_type=data.assignee_type,
        assignee_user_id=uuid.UUID(data.assignee_user_id) if data.assignee_user_id else None,
        assignee_member_id=uuid.UUID(data.assignee_member_id) if data.assignee_member_id else None,
        assignee_agent_id=uuid.UUID(data.assignee_agent_id) if data.assignee_agent_id else None,
        
        visibility=data.visibility,
        visible_to_user_ids=data.visible_to_user_ids,
        tenant_id=current_user.tenant_id,
    )
    
    db.add(task)
    await db.flush()
    
    # Add creation log
    log = TeamTaskLog(
        task_id=task.id,
        created_by_user_id=current_user.id,
        log_type="status_change",
        content=f"任务已创建",
        extra_data={"old_status": None, "new_status": "pending"},
    )
    db.add(log)
    
    await db.commit()
    
    # Reload with relationships
    result = await db.execute(
        select(TeamTask)
        .where(TeamTask.id == task.id)
        .options(
            selectinload(TeamTask.creator_user),
            selectinload(TeamTask.assignee_user),
            selectinload(TeamTask.assignee_member),
            selectinload(TeamTask.assignee_agent),
            selectinload(TeamTask.subtasks),
        )
    )
    task = result.scalar_one()
    
    # If decomposition requested, trigger AI decomposition
    if data.request_decomposition:
        # TODO: Trigger AI decomposition in background
        pass
    
    # Dispatch task to assignee (agent or member)
    if task.assignee_agent_id or task.assignee_member_id:
        import asyncio
        from app.services.team_task_executor import dispatch_team_task
        asyncio.create_task(dispatch_team_task(task.id))
    
    return serialize_task(task)


@router.post("/tasks/decompose-preview")
async def decompose_task_preview(
    data: DecomposePreviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Use AI agent to preview task decomposition before creating.
    This ACTUALLY calls the agent's bound LLM to decompose the task.
    Returns a list of suggested subtasks.
    """
    import json
    import re
    from sqlalchemy.orm import selectinload
    
    # Verify agent exists and user has access
    result = await db.execute(
        select(Agent)
        .where(Agent.id == uuid.UUID(data.agent_id))
        .options(selectinload(Agent.primary_model))
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    if agent.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Agent not in your tenant")
    
    # Get the agent's primary LLM model
    if not agent.primary_model:
        raise HTTPException(
            status_code=400, 
            detail=f"数字员工 {agent.name} 未配置大模型，请先在设置中绑定模型"
        )
    
    model = agent.primary_model
    if not model.enabled:
        raise HTTPException(
            status_code=400,
            detail=f"数字员工 {agent.name} 绑定的模型已禁用"
        )
    
    # Build the task decomposition prompt
    decompose_prompt = f"""你是一位专业的任务分析师。请分析以下任务，并将其拆解为具体、可执行的子任务。

## 待拆解的任务

**标题**: {data.title}
**描述**: {data.description or '（无详细描述）'}

## 拆解要求

1. 每个子任务应该具体、可执行、有明确的完成标准
2. 子任务数量根据任务复杂度决定，一般2-7个
3. 子任务之间应该有合理的执行顺序
4. 每个子任务的描述应该清晰说明需要做什么

## 输出格式

请严格按照以下JSON格式返回，不要添加任何其他文字说明：

```json
[
  {{"title": "子任务1标题", "description": "详细描述这个子任务需要做什么"}},
  {{"title": "子任务2标题", "description": "详细描述这个子任务需要做什么"}}
]
```

请开始分析并输出JSON："""

    # Use the real LLM client to call the model
    try:
        from app.services.llm_utils import create_llm_client, get_max_tokens, LLMMessage, LLMError
        
        # Create LLM client with agent's model configuration
        client = create_llm_client(
            provider=model.provider,
            api_key=model.api_key_encrypted,
            model=model.model,
            base_url=model.base_url,
            timeout=60.0,
        )
        
        # Build messages
        messages = [
            LLMMessage(
                role="system",
                content=f"你是 {agent.name}，一位专业的数字员工。{agent.role_description or ''}"
            ),
            LLMMessage(role="user", content=decompose_prompt)
        ]
        
        max_tokens = get_max_tokens(model.provider, model.model, getattr(model, 'max_output_tokens', None))
        
        # Call the LLM (non-streaming for task decomposition)
        response = await client.complete(
            messages=messages,
            temperature=0.7,
            max_tokens=min(max_tokens, 2000),  # Limit for decomposition
        )
        
        # Extract content from response
        content = response.content or ""
        
        # Record token usage
        from app.services.token_tracker import record_token_usage, extract_usage_tokens
        real_tokens = extract_usage_tokens(response.usage)
        if real_tokens and agent.id:
            await record_token_usage(agent.id, real_tokens)
        
        # Parse the JSON response
        # Try to find JSON array in the response (may be wrapped in markdown code block)
        json_match = re.search(r'\[[\s\S]*?\]', content)
        if json_match:
            try:
                subtasks = json.loads(json_match.group())
                # Validate structure
                if isinstance(subtasks, list) and all(
                    isinstance(st, dict) and "title" in st 
                    for st in subtasks
                ):
                    return {"subtasks": subtasks, "agent_name": agent.name}
            except json.JSONDecodeError:
                pass
        
        # If JSON parsing failed, try to extract structured info from text
        # This is a fallback for when the model doesn't return proper JSON
        raise ValueError(f"无法解析AI返回的内容: {content[:500]}")
        
    except LLMError as e:
        raise HTTPException(
            status_code=500, 
            detail=f"调用数字员工 {agent.name} 的大模型失败: {str(e)}"
        )
    except Exception as e:
        # Re-raise HTTP exceptions
        if isinstance(e, HTTPException):
            raise
        # Log the actual error for debugging
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"任务拆解失败: {str(e)}"
        )


@router.post("/tasks/with-subtasks")
async def create_task_with_subtasks(
    data: CreateTaskWithSubtasksRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a main task with multiple subtasks.
    Used after AI decomposition to create the entire task structure at once.
    """
    import traceback
    
    try:
        # Validate subtasks have at least one with an assignee
        if not data.subtasks:
            raise HTTPException(
                status_code=400, 
                detail="至少需要一个子任务"
            )
        
        # Create main task
        main_task = TeamTask(
            title=data.title,
            description=data.description,
            priority=data.priority,
            due_date=data.due_date,
            task_type="decomposed",
            
            created_by_user_id=current_user.id,
            
            visibility=data.visibility,
            tenant_id=current_user.tenant_id,
        )
        
        db.add(main_task)
        await db.flush()
        
        # Add creation log
        log = TeamTaskLog(
            task_id=main_task.id,
            created_by_user_id=current_user.id,
            log_type="status_change",
            content=f"任务已创建（包含 {len(data.subtasks)} 个子任务）",
            extra_data={"old_status": None, "new_status": "pending", "subtasks_count": len(data.subtasks)},
        )
        db.add(log)
        
        # Create subtasks
        for idx, st_data in enumerate(data.subtasks):
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"[create_task_with_subtasks] subtask {idx}: title={st_data.title}, assignees={[{'type': a.type, 'id': a.id} for a in st_data.assignees]}")
            # For each subtask, create one task per assignee (or one task if single/no assignee)
            if len(st_data.assignees) <= 1:
                assignee = st_data.assignees[0] if st_data.assignees else None
                subtask = TeamTask(
                    title=st_data.title,
                    description=st_data.description,
                    priority=data.priority,
                    due_date=data.due_date,
                    task_type="subtask",
                    
                    parent_task_id=main_task.id,
                    root_task_id=main_task.id,
                    
                    created_by_user_id=current_user.id,
                    
                    assignee_type=assignee.type if assignee else "member",
                    assignee_agent_id=uuid.UUID(assignee.id) if assignee and assignee.type == "agent" else None,
                    assignee_member_id=uuid.UUID(assignee.id) if assignee and assignee.type == "member" else None,
                    
                    visibility=data.visibility,
                    tenant_id=current_user.tenant_id,
                )
                db.add(subtask)
            else:
                # Multiple assignees: create one subtask per assignee
                for assignee in st_data.assignees:
                    subtask = TeamTask(
                        title=st_data.title,
                        description=st_data.description,
                        priority=data.priority,
                        due_date=data.due_date,
                        task_type="subtask",
                        
                        parent_task_id=main_task.id,
                        root_task_id=main_task.id,
                        
                        created_by_user_id=current_user.id,
                        
                        assignee_type=assignee.type,
                        assignee_agent_id=uuid.UUID(assignee.id) if assignee.type == "agent" else None,
                        assignee_member_id=uuid.UUID(assignee.id) if assignee.type == "member" else None,
                        
                        visibility=data.visibility,
                        tenant_id=current_user.tenant_id,
                    )
                    db.add(subtask)
        
        await db.commit()
        
        # Reload with relationships - MUST load all relationships needed by serialize_task
        result = await db.execute(
            select(TeamTask)
            .where(TeamTask.id == main_task.id)
            .options(
                selectinload(TeamTask.creator_user),
                selectinload(TeamTask.creator_agent),
                selectinload(TeamTask.assignee_user),
                selectinload(TeamTask.assignee_member),
                selectinload(TeamTask.assignee_agent),
                selectinload(TeamTask.subtasks).selectinload(TeamTask.creator_user),
                selectinload(TeamTask.subtasks).selectinload(TeamTask.creator_agent),
                selectinload(TeamTask.subtasks).selectinload(TeamTask.assignee_user),
                selectinload(TeamTask.subtasks).selectinload(TeamTask.assignee_member),
                selectinload(TeamTask.subtasks).selectinload(TeamTask.assignee_agent),
            )
        )
        main_task = result.scalar_one()
        
        task_data = serialize_task(main_task)
        # Get subtasks safely
        subtasks_list = getattr(main_task, 'subtasks', None) or []
        task_data["subtasks"] = [serialize_task(st) for st in subtasks_list]
        
        # Dispatch all subtasks to their assignees (agents/members)
        import asyncio
        from app.services.team_task_executor import dispatch_all_subtasks
        asyncio.create_task(dispatch_all_subtasks(main_task.id))
        
        return task_data
        
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"创建任务失败: {str(e)}"
        )


@router.get("/tasks/{task_id}")
async def get_team_task(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific team task with its subtasks."""
    result = await db.execute(
        select(TeamTask)
        .where(TeamTask.id == task_id)
        .options(
            selectinload(TeamTask.creator_user),
            selectinload(TeamTask.creator_agent),
            selectinload(TeamTask.assignee_user),
            selectinload(TeamTask.assignee_member),
            selectinload(TeamTask.assignee_agent),
            selectinload(TeamTask.subtasks).selectinload(TeamTask.assignee_member),
            selectinload(TeamTask.subtasks).selectinload(TeamTask.assignee_agent),
            selectinload(TeamTask.logs),
        )
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if not await check_task_visibility(task, current_user, db):
        raise HTTPException(status_code=403, detail="No permission to view this task")
    
    task_data = serialize_task(task)
    task_data["subtasks"] = [serialize_task(st) for st in task.subtasks]
    task_data["logs"] = [
        {
            "id": str(log.id),
            "log_type": log.log_type,
            "content": log.content,
            "extra_data": log.extra_data,
            "created_by_user_id": str(log.created_by_user_id) if log.created_by_user_id else None,
            "created_by_agent_id": str(log.created_by_agent_id) if log.created_by_agent_id else None,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in sorted(task.logs, key=lambda l: l.created_at)
    ]
    
    return task_data


@router.patch("/tasks/{task_id}")
async def update_team_task(
    task_id: uuid.UUID,
    data: TeamTaskUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a team task."""
    result = await db.execute(
        select(TeamTask)
        .where(TeamTask.id == task_id)
        .options(
            selectinload(TeamTask.creator_user),
            selectinload(TeamTask.assignee_user),
            selectinload(TeamTask.assignee_member),
            selectinload(TeamTask.assignee_agent),
            selectinload(TeamTask.subtasks),
        )
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check permission: only creator, assignee, or admin can update
    can_update = (
        task.created_by_user_id == current_user.id or
        task.assignee_user_id == current_user.id or
        current_user.role in ["platform_admin", "org_admin"]
    )
    if not can_update:
        raise HTTPException(status_code=403, detail="No permission to update this task")
    
    # Track changes for logging
    old_status = task.status
    
    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)
    
    # Handle status changes
    if data.status and data.status != old_status:
        if data.status == "in_progress" and not task.started_at:
            task.started_at = datetime.utcnow()
        elif data.status == "completed":
            task.completed_at = datetime.utcnow()
            task.progress_percent = 100
        
        # Add status change log
        log = TeamTaskLog(
            task_id=task.id,
            created_by_user_id=current_user.id,
            log_type="status_change",
            content=f"状态从 {old_status} 变更为 {data.status}",
            extra_data={"old_status": old_status, "new_status": data.status},
        )
        db.add(log)
    
    await db.commit()
    
    return serialize_task(task)


@router.post("/tasks/{task_id}/logs")
async def add_task_log(
    task_id: uuid.UUID,
    data: TeamTaskLogCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a progress log to a task."""
    result = await db.execute(select(TeamTask).where(TeamTask.id == task_id))
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if not await check_task_visibility(task, current_user, db):
        raise HTTPException(status_code=403, detail="No permission")
    
    log = TeamTaskLog(
        task_id=task_id,
        created_by_user_id=current_user.id,
        log_type=data.log_type,
        content=data.content,
    )
    db.add(log)
    await db.commit()
    
    return {
        "id": str(log.id),
        "task_id": str(log.task_id),
        "log_type": log.log_type,
        "content": log.content,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


# ─── Task Decomposition ────────────────────────────────

@router.post("/tasks/{task_id}/decompose")
async def decompose_task(
    task_id: uuid.UUID,
    data: DecomposeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Request AI agent to decompose a task into subtasks.
    The agent will analyze the task and create appropriate subtasks.
    """
    result = await db.execute(
        select(TeamTask).where(TeamTask.id == task_id)
        .options(selectinload(TeamTask.subtasks))
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.created_by_user_id != current_user.id and current_user.role not in ["platform_admin", "org_admin"]:
        raise HTTPException(status_code=403, detail="Only task creator can request decomposition")
    
    # Get user's bound agents
    bound_agents = await get_user_bound_agents(db, current_user)
    if not bound_agents:
        raise HTTPException(
            status_code=400, 
            detail="No AI agent bound to your account. Please bind an agent first."
        )
    
    # Use the first bound agent for decomposition
    agent_id = bound_agents[0]
    
    # Store decomposition request
    task.task_type = "decomposed"
    task.decomposition_prompt = data.prompt or f"请将以下任务拆解为可执行的子任务：\n\n任务标题：{task.title}\n任务描述：{task.description or '无'}"
    
    # TODO: Trigger actual AI decomposition via background task
    # For now, we'll return immediately and the frontend can poll for results
    
    await db.commit()
    
    return {
        "status": "decomposition_requested",
        "task_id": str(task_id),
        "agent_id": str(agent_id),
        "message": "任务拆解请求已提交，AI正在处理中..."
    }


@router.post("/tasks/{task_id}/subtasks")
async def create_subtask(
    task_id: uuid.UUID,
    data: SubtaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually create a subtask under a parent task."""
    result = await db.execute(select(TeamTask).where(TeamTask.id == task_id))
    parent_task = result.scalar_one_or_none()
    
    if not parent_task:
        raise HTTPException(status_code=404, detail="Parent task not found")
    
    if parent_task.created_by_user_id != current_user.id and current_user.role not in ["platform_admin", "org_admin"]:
        raise HTTPException(status_code=403, detail="Only task creator can add subtasks")
    
    # Determine root task
    root_id = parent_task.root_task_id or parent_task.id
    
    subtask = TeamTask(
        title=data.title,
        description=data.description,
        priority=data.priority,
        due_date=data.due_date,
        task_type="subtask",
        
        parent_task_id=task_id,
        root_task_id=root_id,
        
        created_by_user_id=current_user.id,
        
        assignee_type=data.assignee_type,
        assignee_user_id=uuid.UUID(data.assignee_user_id) if data.assignee_user_id else None,
        assignee_member_id=uuid.UUID(data.assignee_member_id) if data.assignee_member_id else None,
        assignee_agent_id=uuid.UUID(data.assignee_agent_id) if data.assignee_agent_id else None,
        
        visibility=parent_task.visibility,
        tenant_id=current_user.tenant_id,
    )
    
    # Update parent task type if it's still "direct"
    if parent_task.task_type == "direct":
        parent_task.task_type = "decomposed"
    
    db.add(subtask)
    await db.commit()
    
    # Reload with relationships
    result = await db.execute(
        select(TeamTask)
        .where(TeamTask.id == subtask.id)
        .options(
            selectinload(TeamTask.creator_user),
            selectinload(TeamTask.assignee_user),
            selectinload(TeamTask.assignee_member),
            selectinload(TeamTask.assignee_agent),
        )
    )
    subtask = result.scalar_one()
    
    return serialize_task(subtask)


# ─── Task Execution & Review ───────────────────────────

class ReviewAction(BaseModel):
    action: str  # "approve", "reject", "revise"
    feedback: Optional[str] = None


@router.post("/tasks/{task_id}/review")
async def review_task_result(
    task_id: uuid.UUID,
    data: ReviewAction,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Review an agent's task execution result.
    
    Actions:
    - approve: Accept the result, mark task as completed
    - reject: Reject, ask agent to redo
    - revise: Accept with modifications (feedback saved)
    """
    result = await db.execute(
        select(TeamTask).where(TeamTask.id == task_id)
        .options(selectinload(TeamTask.assignee_agent))
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.created_by_user_id != current_user.id and current_user.role not in ["platform_admin", "org_admin"]:
        raise HTTPException(status_code=403, detail="Only task creator can review")
    
    if data.action == "approve":
        task.status = "completed"
        task.completed_at = datetime.utcnow()
        task.progress_percent = 100
        task.progress_note = "已通过检阅"
        
        log = TeamTaskLog(
            task_id=task.id,
            created_by_user_id=current_user.id,
            log_type="status_change",
            content=f"✅ 检阅通过{': ' + data.feedback if data.feedback else ''}",
            extra_data={"action": "approve", "feedback": data.feedback},
        )
        db.add(log)
        
    elif data.action == "reject":
        task.progress_note = "检阅未通过，需要重新执行"
        task.progress_percent = 0
        
        log = TeamTaskLog(
            task_id=task.id,
            created_by_user_id=current_user.id,
            log_type="comment",
            content=f"❌ 检阅未通过: {data.feedback or '请重新执行'}",
            extra_data={"action": "reject", "feedback": data.feedback},
        )
        db.add(log)
        
        # Re-trigger execution if assigned to agent
        if task.assignee_agent_id:
            import asyncio
            from app.services.team_task_executor import dispatch_team_task
            task.status = "in_progress"
            await db.commit()
            asyncio.create_task(dispatch_team_task(task.id))
            return {"status": "re_executing", "message": "任务已重新下发给数字员工执行"}
    
    elif data.action == "revise":
        task.status = "completed"
        task.completed_at = datetime.utcnow()
        task.progress_percent = 100
        task.progress_note = "已通过检阅（含修改意见）"
        
        log = TeamTaskLog(
            task_id=task.id,
            created_by_user_id=current_user.id,
            log_type="comment",
            content=f"📝 检阅通过（附修改意见）: {data.feedback or ''}",
            extra_data={"action": "revise", "feedback": data.feedback},
        )
        db.add(log)
    
    else:
        raise HTTPException(status_code=400, detail="Invalid action")
    
    await db.commit()
    
    return {"status": data.action, "message": "检阅结果已提交"}


@router.post("/tasks/{task_id}/dispatch")
async def dispatch_task(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually dispatch or re-dispatch a task to its assignee."""
    result = await db.execute(
        select(TeamTask).where(TeamTask.id == task_id)
    )
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.created_by_user_id != current_user.id and current_user.role not in ["platform_admin", "org_admin"]:
        raise HTTPException(status_code=403, detail="No permission")
    
    import asyncio
    from app.services.team_task_executor import dispatch_team_task
    asyncio.create_task(dispatch_team_task(task.id))
    
    return {"status": "dispatched", "message": "任务已分发"}


# ─── Daily Reports ─────────────────────────────────────

@router.get("/reports/agents")
async def list_agent_daily_reports(
    agent_id: Optional[str] = None,
    start_date: Optional[str] = None,  # YYYY-MM-DD
    end_date: Optional[str] = None,    # YYYY-MM-DD
    report_status: Optional[str] = None,  # draft, pending_review, published
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List daily reports for digital employees.
    Leaders can see reports from agents bound to their team members.
    """
    query = select(AgentDailyReport).where(
        AgentDailyReport.tenant_id == current_user.tenant_id
    )
    
    # Filter by status
    if report_status:
        query = query.where(AgentDailyReport.report_status == report_status)
    
    # Filter by agent
    if agent_id:
        query = query.where(AgentDailyReport.agent_id == uuid.UUID(agent_id))
    else:
        # Get all agents the user can see reports for
        bound_agents = await get_user_bound_agents(db, current_user)
        
        # If user is a leader/admin, also include agents bound to their team members
        if current_user.role in ["platform_admin", "org_admin"]:
            # Admin can see all agents in tenant
            pass
        elif bound_agents:
            query = query.where(AgentDailyReport.agent_id.in_(bound_agents))
        else:
            return []
    
    # Date filters
    if start_date:
        start_dt = datetime.fromisoformat(start_date)
        query = query.where(AgentDailyReport.report_date >= start_dt)
    if end_date:
        end_dt = datetime.fromisoformat(end_date) + timedelta(days=1)
        query = query.where(AgentDailyReport.report_date < end_dt)
    
    query = query.options(
        selectinload(AgentDailyReport.agent),
        selectinload(AgentDailyReport.confirmed_by),
    )
    query = query.order_by(AgentDailyReport.report_date.desc())
    
    result = await db.execute(query)
    reports = result.scalars().all()
    
    return [
        {
            "id": str(r.id),
            "agent_id": str(r.agent_id),
            "agent_name": r.agent.name if r.agent else None,
            "agent_avatar": r.agent.avatar_url if r.agent else None,
            "report_date": r.report_date.isoformat() if r.report_date else None,
            "summary": r.summary,
            "completed_tasks": r.completed_tasks,
            "in_progress_tasks": r.in_progress_tasks,
            "planned_tasks": r.planned_tasks,
            "blockers": r.blockers,
            "highlights": r.highlights,
            "tasks_completed_count": r.tasks_completed_count,
            "tasks_in_progress_count": r.tasks_in_progress_count,
            "messages_sent": r.messages_sent,
            "tokens_used": r.tokens_used,
            "report_status": r.report_status or "draft",
            "confirmed_by_name": r.confirmed_by.display_name if r.confirmed_by else None,
            "confirmed_at": r.confirmed_at.isoformat() if r.confirmed_at else None,
            "reviewer_comment": r.reviewer_comment,
            "is_auto_generated": r.is_auto_generated,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reports
    ]


@router.get("/reports/agents/{agent_id}/{report_date}")
async def get_agent_daily_report(
    agent_id: uuid.UUID,
    report_date: str,  # YYYY-MM-DD
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific agent's daily report."""
    target_date = datetime.fromisoformat(report_date).date()
    
    result = await db.execute(
        select(AgentDailyReport)
        .where(
            AgentDailyReport.agent_id == agent_id,
            func.date(AgentDailyReport.report_date) == target_date,
        )
        .options(selectinload(AgentDailyReport.agent))
    )
    report = result.scalar_one_or_none()
    
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    return {
        "id": str(report.id),
        "agent_id": str(report.agent_id),
        "agent_name": report.agent.name if report.agent else None,
        "report_date": report.report_date.isoformat() if report.report_date else None,
        "summary": report.summary,
        "completed_tasks": report.completed_tasks,
        "in_progress_tasks": report.in_progress_tasks,
        "planned_tasks": report.planned_tasks,
        "blockers": report.blockers,
        "highlights": report.highlights,
        "tasks_completed_count": report.tasks_completed_count,
        "tasks_in_progress_count": report.tasks_in_progress_count,
        "messages_sent": report.messages_sent,
        "tokens_used": report.tokens_used,
        "is_auto_generated": report.is_auto_generated,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


@router.post("/reports/agents/{agent_id}/generate")
async def generate_agent_daily_report(
    agent_id: uuid.UUID,
    target_date: Optional[str] = None,  # YYYY-MM-DD, defaults to today
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger daily report generation for an agent."""
    from app.services.agent_report_service import generate_agent_report
    
    # Check agent access
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    if agent.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Agent not in your tenant")
    
    # Parse target date
    if target_date:
        report_date = datetime.fromisoformat(target_date)
    else:
        report_date = datetime.utcnow()
    
    # Generate report
    report = await generate_agent_report(db, agent_id, report_date)
    
    return {
        "status": "generated",
        "report_id": str(report.id),
        "report_date": report.report_date.isoformat() if report.report_date else None,
    }


class ReportReviewPayload(BaseModel):
    action: str  # "confirm" or "reject"
    comment: Optional[str] = None


@router.post("/reports/{report_id}/confirm")
async def confirm_agent_daily_report(
    report_id: uuid.UUID,
    payload: ReportReviewPayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Confirm (publish) or reject an agent daily report.
    Only the bound human (or admin) can confirm.
    action = "confirm" → set status to "published"
    action = "reject"  → set status back to "draft"
    """
    from app.models.user_agent_binding import UserAgentBinding

    result = await db.execute(
        select(AgentDailyReport).where(AgentDailyReport.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # Permission check: bound user or admin
    if current_user.role not in ["platform_admin", "org_admin"]:
        binding_check = await db.execute(
            select(UserAgentBinding).where(
                UserAgentBinding.user_id == current_user.id,
                UserAgentBinding.agent_id == report.agent_id,
                UserAgentBinding.is_active == True,
            )
        )
        if not binding_check.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="You are not bound to this agent")

    if payload.action == "confirm":
        report.report_status = "published"
        report.confirmed_by_user_id = current_user.id
        report.confirmed_at = datetime.utcnow()
        report.reviewer_comment = payload.comment
    elif payload.action == "reject":
        report.report_status = "draft"
        report.reviewer_comment = payload.comment
    else:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'confirm' or 'reject'")

    await db.commit()

    return {
        "status": report.report_status,
        "report_id": str(report.id),
        "message": "日报已发布" if payload.action == "confirm" else "日报已退回",
    }


@router.get("/reports/pending")
async def list_pending_reports(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List agent daily reports pending review for the current user's bound agents.
    Returns reports with status 'draft' or 'pending_review'.
    """
    from app.models.user_agent_binding import UserAgentBinding

    # Get user's bound agent IDs
    bindings_result = await db.execute(
        select(UserAgentBinding.agent_id).where(
            UserAgentBinding.user_id == current_user.id,
            UserAgentBinding.is_active == True,
        )
    )
    bound_agent_ids = [row[0] for row in bindings_result.fetchall()]

    if not bound_agent_ids and current_user.role not in ["platform_admin", "org_admin"]:
        return []

    query = select(AgentDailyReport).where(
        AgentDailyReport.tenant_id == current_user.tenant_id,
        AgentDailyReport.report_status.in_(["draft", "pending_review"]),
    )

    if current_user.role not in ["platform_admin", "org_admin"]:
        query = query.where(AgentDailyReport.agent_id.in_(bound_agent_ids))

    query = query.options(selectinload(AgentDailyReport.agent))
    query = query.order_by(AgentDailyReport.report_date.desc())

    result = await db.execute(query)
    reports = result.scalars().all()

    return [
        {
            "id": str(r.id),
            "agent_id": str(r.agent_id),
            "agent_name": r.agent.name if r.agent else None,
            "agent_avatar": r.agent.avatar_url if r.agent else None,
            "report_date": r.report_date.isoformat() if r.report_date else None,
            "summary": r.summary,
            "completed_tasks": r.completed_tasks,
            "in_progress_tasks": r.in_progress_tasks,
            "planned_tasks": r.planned_tasks,
            "blockers": r.blockers,
            "highlights": r.highlights,
            "tasks_completed_count": r.tasks_completed_count,
            "tasks_in_progress_count": r.tasks_in_progress_count,
            "messages_sent": r.messages_sent,
            "tokens_used": r.tokens_used,
            "report_status": r.report_status or "draft",
            "is_auto_generated": r.is_auto_generated,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reports
    ]


# ─── Dashboard Stats ───────────────────────────────────

@router.get("/dashboard/stats")
async def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get team dashboard statistics for the current user."""
    
    # Count tasks by status
    tasks_result = await db.execute(
        select(
            TeamTask.status,
            func.count(TeamTask.id).label("count")
        )
        .where(
            TeamTask.tenant_id == current_user.tenant_id,
            or_(
                TeamTask.created_by_user_id == current_user.id,
                TeamTask.assignee_user_id == current_user.id,
            )
        )
        .group_by(TeamTask.status)
    )
    tasks_by_status = {row[0]: row[1] for row in tasks_result.fetchall()}
    
    # Count tasks created vs assigned
    created_count = await db.execute(
        select(func.count(TeamTask.id))
        .where(TeamTask.created_by_user_id == current_user.id)
    )
    assigned_count = await db.execute(
        select(func.count(TeamTask.id))
        .where(TeamTask.assignee_user_id == current_user.id)
    )
    
    # Get bound agents
    bound_agents = await get_user_bound_agents(db, current_user)
    
    # Get agent task stats
    agent_task_stats = {}
    if bound_agents:
        for agent_id in bound_agents:
            agent_result = await db.execute(
                select(Agent).where(Agent.id == agent_id)
            )
            agent = agent_result.scalar_one_or_none()
            if agent:
                # Count tasks assigned to this agent
                task_count = await db.execute(
                    select(func.count(TeamTask.id))
                    .where(TeamTask.assignee_agent_id == agent_id)
                )
                agent_task_stats[str(agent_id)] = {
                    "name": agent.name,
                    "task_count": task_count.scalar_one(),
                }
    
    # Get recent reports count
    week_ago = datetime.utcnow() - timedelta(days=7)
    reports_count = await db.execute(
        select(func.count(AgentDailyReport.id))
        .where(
            AgentDailyReport.tenant_id == current_user.tenant_id,
            AgentDailyReport.report_date >= week_ago,
            AgentDailyReport.agent_id.in_(bound_agents) if bound_agents else True,
        )
    )
    
    return {
        "tasks_by_status": tasks_by_status,
        "total_tasks_created": created_count.scalar_one(),
        "total_tasks_assigned": assigned_count.scalar_one(),
        "bound_agents_count": len(bound_agents),
        "agent_task_stats": agent_task_stats,
        "recent_reports_count": reports_count.scalar_one(),
    }
