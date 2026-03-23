"""Daily summary generation service.

Aggregates all bound agents' activities for a user into a daily summary.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.agent import Agent
from app.models.audit import ChatMessage
from app.models.chat_session import ChatSession
from app.models.task import Task, TaskLog
from app.models.user import User
from app.models.user_agent_binding import DailySummary, UserAgentBinding


async def generate_summary_for_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    summary_date: date,
) -> DailySummary:
    """Generate or update a daily summary for a user based on their bound agents' activity."""

    # Get the date range (start of day to end of day in UTC)
    day_start = datetime(summary_date.year, summary_date.month, summary_date.day, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    # Get all active bindings for this user
    bindings_result = await db.execute(
        select(UserAgentBinding)
        .where(
            UserAgentBinding.user_id == user_id,
            UserAgentBinding.is_active == True,
        )
    )
    bindings = bindings_result.scalars().all()
    agent_ids = [b.agent_id for b in bindings]

    if not agent_ids:
        # No bindings — create empty summary
        return await _upsert_summary(db, user_id, summary_date, {
            "content": "今日没有绑定的数字员工活动。",
            "agent_details": {},
            "total_tasks_completed": 0,
            "total_messages": 0,
            "total_tokens_used": 0,
        })

    # Collect per-agent data
    agent_details = {}
    total_tasks_completed = 0
    total_messages = 0
    total_tokens_used = 0

    for agent_id in agent_ids:
        # Get agent info
        agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = agent_result.scalar_one_or_none()
        if not agent:
            continue

        # Count tasks completed today
        tasks_result = await db.execute(
            select(func.count(Task.id)).where(
                Task.agent_id == agent_id,
                Task.completed_at >= day_start,
                Task.completed_at < day_end,
            )
        )
        tasks_done = tasks_result.scalar() or 0

        # Count tasks in progress
        tasks_doing_result = await db.execute(
            select(func.count(Task.id)).where(
                Task.agent_id == agent_id,
                Task.status == "doing",
            )
        )
        tasks_doing = tasks_doing_result.scalar() or 0

        # Get task titles completed today
        completed_tasks_result = await db.execute(
            select(Task.title).where(
                Task.agent_id == agent_id,
                Task.completed_at >= day_start,
                Task.completed_at < day_end,
            ).limit(20)
        )
        completed_task_titles = [row[0] for row in completed_tasks_result.all()]

        # Count messages today (from sessions)
        sessions_result = await db.execute(
            select(ChatSession.id).where(ChatSession.agent_id == agent_id)
        )
        session_ids = [row[0] for row in sessions_result.all()]

        messages_count = 0
        if session_ids:
            msg_result = await db.execute(
                select(func.count(ChatMessage.id)).where(
                    ChatMessage.session_id.in_(session_ids),
                    ChatMessage.created_at >= day_start,
                    ChatMessage.created_at < day_end,
                )
            )
            messages_count = msg_result.scalar() or 0

        agent_detail = {
            "name": agent.name,
            "role": agent.role_description or "",
            "status": agent.status,
            "tasks_completed": tasks_done,
            "tasks_in_progress": tasks_doing,
            "completed_task_titles": completed_task_titles,
            "messages_count": messages_count,
            "tokens_used_today": agent.tokens_used_today,
        }

        agent_details[str(agent_id)] = agent_detail
        total_tasks_completed += tasks_done
        total_messages += messages_count
        total_tokens_used += agent.tokens_used_today

    # Generate summary text
    content_lines = [f"## {summary_date.strftime('%Y年%m月%d日')} 工作总结\n"]

    if agent_details:
        content_lines.append(f"今日共有 **{len(agent_details)}** 个数字员工为您工作。\n")
        content_lines.append(f"- 完成任务：**{total_tasks_completed}** 个")
        content_lines.append(f"- 交互消息：**{total_messages}** 条")
        content_lines.append(f"- Token 消耗：**{total_tokens_used}**\n")

        for aid, detail in agent_details.items():
            content_lines.append(f"### {detail['name']}")
            content_lines.append(f"- 角色：{detail['role']}")
            content_lines.append(f"- 状态：{detail['status']}")
            content_lines.append(f"- 完成任务 {detail['tasks_completed']} 个，进行中 {detail['tasks_in_progress']} 个")
            if detail['completed_task_titles']:
                content_lines.append("- 完成的任务：")
                for t in detail['completed_task_titles']:
                    content_lines.append(f"  - {t}")
            content_lines.append(f"- 交互消息 {detail['messages_count']} 条")
            content_lines.append("")
    else:
        content_lines.append("今日暂无数字员工活动记录。")

    content = "\n".join(content_lines)

    # Get user's tenant_id
    user_result = await db.execute(select(User.tenant_id).where(User.id == user_id))
    tenant_id = user_result.scalar()

    return await _upsert_summary(db, user_id, summary_date, {
        "content": content,
        "agent_details": agent_details,
        "total_tasks_completed": total_tasks_completed,
        "total_messages": total_messages,
        "total_tokens_used": total_tokens_used,
        "tenant_id": tenant_id,
    })


async def _upsert_summary(
    db: AsyncSession,
    user_id: uuid.UUID,
    summary_date: date,
    data: dict,
) -> DailySummary:
    """Insert or update daily summary."""
    result = await db.execute(
        select(DailySummary).where(
            DailySummary.user_id == user_id,
            DailySummary.summary_date == summary_date,
        )
    )
    summary = result.scalar_one_or_none()

    if summary:
        summary.content = data["content"]
        summary.agent_details = data["agent_details"]
        summary.total_tasks_completed = data["total_tasks_completed"]
        summary.total_messages = data["total_messages"]
        summary.total_tokens_used = data["total_tokens_used"]
    else:
        summary = DailySummary(
            user_id=user_id,
            summary_date=summary_date,
            content=data["content"],
            agent_details=data["agent_details"],
            total_tasks_completed=data["total_tasks_completed"],
            total_messages=data["total_messages"],
            total_tokens_used=data["total_tokens_used"],
            tenant_id=data.get("tenant_id"),
        )
        db.add(summary)

    await db.flush()
    return summary


async def generate_all_daily_summaries():
    """Generate daily summaries for all users with active bindings. Called by scheduler."""
    async with async_session() as db:
        try:
            today = date.today()
            # Find all users with active bindings
            result = await db.execute(
                select(UserAgentBinding.user_id)
                .where(UserAgentBinding.is_active == True)
                .distinct()
            )
            user_ids = [row[0] for row in result.all()]

            for user_id in user_ids:
                try:
                    await generate_summary_for_user(db, user_id, today)
                except Exception as e:
                    print(f"[DailySummary] Failed for user {user_id}: {e}", flush=True)

            await db.commit()
            print(f"[DailySummary] Generated summaries for {len(user_ids)} users", flush=True)
        except Exception as e:
            await db.rollback()
            print(f"[DailySummary] Batch generation failed: {e}", flush=True)
