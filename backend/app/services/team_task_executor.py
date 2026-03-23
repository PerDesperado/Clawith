"""Team task executor — dispatches team tasks to digital employees for execution.

When a team task is assigned to an agent:
1. Creates a real Task (todo) for the agent → triggers execute_task automatically
2. Agent produces an execution plan
3. Notifies the human creator for review
4. After review/approval, agent executes the plan
5. Results are written back to TeamTask logs
6. If the agent has a channel configured, sends notifications via that channel
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.agent import Agent
from app.models.channel_config import ChannelConfig
from app.models.llm import LLMModel
from app.models.org import OrgMember
from app.models.team_task import TeamTask, TeamTaskLog
from app.models.user import User

logger = logging.getLogger(__name__)


async def dispatch_team_task(team_task_id: uuid.UUID) -> None:
    """Dispatch a single team task to its assigned agent for execution.

    This is the main entry point called after task creation.
    For agent-assigned tasks: creates an execution plan via LLM.
    For member-assigned tasks: sends notification to the human.
    """
    print(f"[TeamTaskExec] Dispatching team task {team_task_id}")

    async with async_session() as db:
        result = await db.execute(
            select(TeamTask)
            .where(TeamTask.id == team_task_id)
            .options(
                selectinload(TeamTask.assignee_agent),
                selectinload(TeamTask.assignee_member),
                selectinload(TeamTask.creator_user),
            )
        )
        task = result.scalar_one_or_none()
        if not task:
            print(f"[TeamTaskExec] Task {team_task_id} not found")
            return

        if task.assignee_type == "agent" and task.assignee_agent_id:
            await _dispatch_to_agent(db, task)
        elif task.assignee_type == "member" and task.assignee_member_id:
            await _notify_member(db, task)
        else:
            # No specific assignee — just log
            log = TeamTaskLog(
                task_id=task.id,
                log_type="progress",
                content="任务已创建，等待分配负责人",
            )
            db.add(log)
            await db.commit()


async def dispatch_all_subtasks(parent_task_id: uuid.UUID) -> None:
    """Dispatch all subtasks of a parent task."""
    async with async_session() as db:
        result = await db.execute(
            select(TeamTask).where(TeamTask.parent_task_id == parent_task_id)
        )
        subtasks = result.scalars().all()

    tasks = []
    for st in subtasks:
        tasks.append(dispatch_team_task(st.id))

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def _dispatch_to_agent(db: AsyncSession, task: TeamTask) -> None:
    """Create an execution plan for an agent-assigned task."""
    agent_id = task.assignee_agent_id

    # Load agent with model
    agent_result = await db.execute(
        select(Agent).where(Agent.id == agent_id)
    )
    agent = agent_result.scalar_one_or_none()
    if not agent:
        log = TeamTaskLog(
            task_id=task.id,
            log_type="progress",
            content="❌ 分配的数字员工不存在",
        )
        db.add(log)
        await db.commit()
        return

    model_id = agent.primary_model_id or agent.fallback_model_id
    if not model_id:
        log = TeamTaskLog(
            task_id=task.id,
            log_type="progress",
            content=f"❌ 数字员工 {agent.name} 未配置大模型，无法执行任务",
        )
        db.add(log)
        await db.commit()
        return

    model_result = await db.execute(select(LLMModel).where(LLMModel.id == model_id))
    model = model_result.scalar_one_or_none()
    if not model or not model.base_url:
        log = TeamTaskLog(
            task_id=task.id,
            log_type="progress",
            content=f"❌ 数字员工 {agent.name} 的大模型配置不完整",
        )
        db.add(log)
        await db.commit()
        return

    # Update task status to in_progress
    task.status = "in_progress"
    task.started_at = datetime.now(timezone.utc)

    # Add log: agent received the task
    log = TeamTaskLog(
        task_id=task.id,
        log_type="progress",
        content=f"🤖 数字员工 [{agent.name}] 已接收任务，正在制定执行计划...",
        created_by_agent_id=agent.id,
    )
    db.add(log)
    await db.commit()

    # Now call LLM to generate execution plan
    try:
        plan = await _generate_execution_plan(agent, model, task)

        # Save plan to task log
        async with async_session() as db2:
            plan_log = TeamTaskLog(
                task_id=task.id,
                log_type="progress",
                content=f"📋 执行计划\n\n{plan}",
                created_by_agent_id=agent.id,
            )
            db2.add(plan_log)

            # Save plan to decomposition_result for reference
            tt_result = await db2.execute(
                select(TeamTask).where(TeamTask.id == task.id)
            )
            tt = tt_result.scalar_one_or_none()
            if tt:
                tt.decomposition_result = {
                    "plan": plan,
                    "status": "pending_review",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "agent_name": agent.name,
                }
            await db2.commit()

        # Notify creator for review
        await _notify_creator_for_review(task, agent, plan)

        # Auto-execute the plan (agent starts working)
        asyncio.create_task(_execute_agent_task(task.id, agent.id))

    except Exception as e:
        logger.error(f"Failed to generate plan for task {task.id}: {e}")
        async with async_session() as db2:
            error_log = TeamTaskLog(
                task_id=task.id,
                log_type="progress",
                content=f"❌ 制定计划失败: {str(e)[:200]}",
                created_by_agent_id=agent.id,
            )
            db2.add(error_log)
            await db2.commit()


async def _generate_execution_plan(agent: Agent, model: LLMModel, task: TeamTask) -> str:
    """Use LLM to generate an execution plan for the task."""
    from app.services.llm_utils import create_llm_client, get_max_tokens, LLMMessage

    client = create_llm_client(
        provider=model.provider,
        api_key=model.api_key_encrypted,
        model=model.model,
        base_url=model.base_url,
        timeout=60.0,
    )

    system_prompt = f"""你是 {agent.name}，一位专业的数字员工。{agent.role_description or ''}

你刚收到一个工作任务，需要制定一个清晰、可执行的计划。

请以简洁的 Markdown 格式输出你的执行计划，包括：
1. 对任务的理解
2. 执行步骤（3-7步）
3. 每步的预期产出
4. 预计完成时间

不要输出多余的寒暄，直接输出计划。"""

    user_prompt = f"""## 任务信息

**标题**: {task.title}
**描述**: {task.description or '无详细描述'}
**优先级**: {task.priority}
**截止日期**: {task.due_date.strftime('%Y-%m-%d') if task.due_date else '无'}

请制定执行计划。"""

    messages = [
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(role="user", content=user_prompt),
    ]

    response = await client.complete(
        messages=messages,
        temperature=0.7,
        max_tokens=min(get_max_tokens(model.provider, model.model, getattr(model, 'max_output_tokens', None)), 2000),
    )
    await client.close()

    return response.content or "（未能生成计划）"


async def _execute_agent_task(team_task_id: uuid.UUID, agent_id: uuid.UUID) -> None:
    """Execute the team task using the agent's full tool suite.

    This creates a real Task in the agent's task list and triggers execute_task.
    Results are written back to the TeamTask logs.
    """
    from app.models.task import Task
    from app.services.task_executor import execute_task

    print(f"[TeamTaskExec] Starting execution for team task {team_task_id} with agent {agent_id}")

    async with async_session() as db:
        # Load the team task
        tt_result = await db.execute(
            select(TeamTask).where(TeamTask.id == team_task_id)
        )
        team_task = tt_result.scalar_one_or_none()
        if not team_task:
            return

        # Load agent to get creator_id
        agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = agent_result.scalar_one_or_none()
        if not agent:
            return

        # Create a real Task for the agent
        agent_task = Task(
            agent_id=agent_id,
            title=f"[团队任务] {team_task.title}",
            description=(
                f"{team_task.description or ''}\n\n"
                f"---\n"
                f"这是一个团队下发的任务。请认真执行并给出详细的结果报告。\n"
                f"**重要要求**：\n"
                f"1. 完成任务后，必须将工作成果和总结报告写入 workspace/ 目录下的文件中（例如 workspace/report_{str(team_task.id)[:8]}.md）。\n"
                f"2. 报告应包含：任务目标、执行过程、关键发现/成果、总结。\n"
                f"3. 如果任务涉及数据收集或分析，请将结果整理成结构化文档保存。\n"
                f"4. 即使部分步骤失败，也要将已完成的内容写入文件。\n"
            ),
            type="todo",
            priority=team_task.priority or "medium",
            created_by=agent.creator_id,
            assignee="self",
            due_date=team_task.due_date,
        )
        db.add(agent_task)
        await db.flush()
        agent_task_id = agent_task.id
        await db.commit()

    # Execute the task (this triggers the full LLM tool-calling loop)
    try:
        await execute_task(agent_task_id, agent_id)
    except Exception as e:
        logger.error(f"Agent task execution failed: {e}")

    # After execution, write results back to TeamTask
    await _sync_results_to_team_task(team_task_id, agent_task_id, agent_id)


async def _sync_results_to_team_task(
    team_task_id: uuid.UUID,
    agent_task_id: uuid.UUID,
    agent_id: uuid.UUID,
) -> None:
    """Read the agent task results and write them back to the TeamTask."""
    from app.models.task import Task, TaskLog

    async with async_session() as db:
        # Load agent task and its logs
        task_result = await db.execute(
            select(Task)
            .where(Task.id == agent_task_id)
            .options(selectinload(Task.logs))
        )
        agent_task = task_result.scalar_one_or_none()

        # Load agent name
        agent_result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = agent_result.scalar_one_or_none()
        agent_name = agent.name if agent else "数字员工"

        if agent_task:
            # Collect execution logs
            log_contents = []
            for tl in sorted(agent_task.logs, key=lambda x: x.created_at):
                log_contents.append(tl.content)

            execution_summary = "\n\n".join(log_contents) if log_contents else "（无执行日志）"

            # Check workspace for output files
            workspace_files_info = ""
            try:
                from app.config import get_settings
                from pathlib import Path
                settings = get_settings()
                ws_dir = Path(settings.AGENT_DATA_DIR) / str(agent_id) / "workspace"
                if ws_dir.exists():
                    recent_files = []
                    for f in ws_dir.rglob("*"):
                        if f.is_file() and not f.name.startswith('.'):
                            recent_files.append(f"  - {f.relative_to(ws_dir)} ({f.stat().st_size} bytes)")
                    if recent_files:
                        workspace_files_info = f"\n\n📁 Workspace 文件:\n" + "\n".join(recent_files[:20])
            except Exception as e:
                logger.warning(f"Failed to scan workspace files: {e}")

            # Write result to team task
            result_log = TeamTaskLog(
                task_id=team_task_id,
                log_type="progress",
                content=f"📊 [{agent_name}] 执行结果\n\n{execution_summary}{workspace_files_info}",
                created_by_agent_id=agent_id,
            )
            db.add(result_log)

            # Update team task status based on agent task status
            tt_result = await db.execute(
                select(TeamTask).where(TeamTask.id == team_task_id)
            )
            team_task = tt_result.scalar_one_or_none()
            if team_task:
                if agent_task.status == "done":
                    # Mark as completed but needs review
                    team_task.decomposition_result = team_task.decomposition_result or {}
                    team_task.decomposition_result["execution_result"] = execution_summary[:2000]
                    team_task.decomposition_result["status"] = "completed_pending_review"
                    team_task.decomposition_result["completed_at"] = datetime.now(timezone.utc).isoformat()
                    team_task.progress_percent = 90  # 90% = done but pending human review
                    team_task.progress_note = "执行完成，等待人工检阅"

                    # Add review request log
                    review_log = TeamTaskLog(
                        task_id=team_task_id,
                        log_type="progress",
                        content=f"✅ [{agent_name}] 已完成任务执行，请检阅结果并确认",
                        created_by_agent_id=agent_id,
                    )
                    db.add(review_log)
                else:
                    team_task.progress_note = f"执行状态: {agent_task.status}"

            await db.commit()

        # Send channel notification about completion
        await _send_channel_notification(
            agent_id,
            team_task_id,
            "task_completed",
        )


async def _notify_creator_for_review(task: TeamTask, agent: Agent, plan: str) -> None:
    """Notify the task creator that a plan is ready for review."""
    if not task.created_by_user_id:
        return

    async with async_session() as db:
        # Web notification
        from app.services.notification_service import send_notification
        await send_notification(
            db,
            user_id=task.created_by_user_id,
            type="task_plan_ready",
            title=f"[{agent.name}] 已制定执行计划: {task.title}",
            body=plan[:200] + "..." if len(plan) > 200 else plan,
            link=f"/team-dashboard",
            ref_id=task.id,
        )
        await db.commit()

    # Also send via channel if configured
    await _send_channel_notification(
        agent.id,
        task.id,
        "plan_ready",
    )


async def _notify_member(db: AsyncSession, task: TeamTask) -> None:
    """Notify a human member about their assigned task."""
    member_id = task.assignee_member_id
    member_result = await db.execute(
        select(OrgMember).where(OrgMember.id == member_id)
    )
    member = member_result.scalar_one_or_none()
    if not member:
        return

    member_name = member.name

    # Add log
    log = TeamTaskLog(
        task_id=task.id,
        log_type="assignment",
        content=f"📩 任务已分配给 {member_name}，等待处理",
    )
    db.add(log)
    await db.commit()

    # Try to find a user account linked to this member (via feishu_open_id)
    if member.feishu_open_id:
        user_result = await db.execute(
            select(User).where(User.feishu_open_id == member.feishu_open_id)
        )
        user = user_result.scalar_one_or_none()
        if user:
            from app.services.notification_service import send_notification
            await send_notification(
                db,
                user_id=user.id,
                type="task_assigned",
                title=f"你有新的团队任务: {task.title}",
                body=task.description[:200] if task.description else "",
                link=f"/team-dashboard",
                ref_id=task.id,
            )
            await db.commit()

    # Send feishu notification to the member if possible
    await _send_feishu_to_member(task, member)


async def _send_feishu_to_member(task: TeamTask, member: OrgMember) -> None:
    """Send a Feishu message to a member about their task, using any available channel config."""
    if not member.feishu_open_id:
        return

    # Find a channel config that can send feishu messages
    # Try to use the creator's bound agents' channel configs
    async with async_session() as db:
        # Find any feishu channel config in the same tenant
        channel_result = await db.execute(
            select(ChannelConfig).where(
                ChannelConfig.channel_type == "feishu",
                ChannelConfig.is_configured == True,
            )
        )
        channel = channel_result.scalars().first()

        if channel and channel.app_id and channel.app_secret:
            from app.services.feishu_service import feishu_service
            try:
                content = json.dumps({
                    "text": (
                        f"📋 你收到一个新的团队任务\n\n"
                        f"标题: {task.title}\n"
                        f"描述: {(task.description or '无')[:200]}\n"
                        f"优先级: {task.priority}\n"
                        f"截止日期: {task.due_date.strftime('%Y-%m-%d') if task.due_date else '无'}\n\n"
                        f"请登录 Clawith 查看详情并开始处理。"
                    )
                })
                await feishu_service.send_message(
                    channel.app_id, channel.app_secret,
                    member.feishu_open_id, "text", content,
                )
                logger.info(f"Sent feishu notification to member {member.name} for task {task.title}")
            except Exception as e:
                logger.warning(f"Failed to send feishu to member {member.name}: {e}")


async def _send_channel_notification(
    agent_id: uuid.UUID,
    team_task_id: uuid.UUID,
    event_type: str,
) -> None:
    """Send a notification via the agent's configured channel (feishu/wecom/dingtalk etc.)."""
    async with async_session() as db:
        # Load agent and its channel config
        agent_result = await db.execute(
            select(Agent)
            .where(Agent.id == agent_id)
            .options(selectinload(Agent.channel_config))
        )
        agent = agent_result.scalar_one_or_none()
        if not agent:
            return

        # Load team task
        tt_result = await db.execute(
            select(TeamTask)
            .where(TeamTask.id == team_task_id)
            .options(selectinload(TeamTask.creator_user))
        )
        team_task = tt_result.scalar_one_or_none()
        if not team_task:
            return

        # Get channel config
        channel_result = await db.execute(
            select(ChannelConfig).where(ChannelConfig.agent_id == agent_id)
        )
        channels = channel_result.scalars().all()

        if not channels:
            return

        # Find the creator's feishu open_id
        creator = None
        if team_task.created_by_user_id:
            creator_result = await db.execute(
                select(User).where(User.id == team_task.created_by_user_id)
            )
            creator = creator_result.scalar_one_or_none()

        for channel in channels:
            if channel.channel_type == "feishu" and channel.app_id and channel.app_secret:
                if creator and creator.feishu_open_id:
                    try:
                        from app.services.feishu_service import feishu_service
                        if event_type == "plan_ready":
                            msg = (
                                f"📋 [{agent.name}] 已制定执行计划\n\n"
                                f"任务: {team_task.title}\n"
                                f"请登录 Clawith 查看计划并确认。"
                            )
                        elif event_type == "task_completed":
                            msg = (
                                f"✅ [{agent.name}] 已完成任务\n\n"
                                f"任务: {team_task.title}\n"
                                f"请登录 Clawith 检阅执行结果。"
                            )
                        else:
                            msg = f"[{agent.name}] 任务更新: {team_task.title}"

                        content = json.dumps({"text": msg})
                        await feishu_service.send_message(
                            channel.app_id, channel.app_secret,
                            creator.feishu_open_id, "text", content,
                        )
                        logger.info(f"Sent {event_type} notification via feishu for task {team_task.title}")
                    except Exception as e:
                        logger.warning(f"Failed to send feishu notification: {e}")

            elif channel.channel_type == "wecom":
                # WeChat Work notification
                extra = channel.extra_config or {}
                corp_id = extra.get("corp_id")
                agent_id_wecom = extra.get("agent_id")
                secret = extra.get("secret")
                if corp_id and secret and creator:
                    try:
                        await _send_wecom_notification(
                            corp_id, secret, agent_id_wecom,
                            creator, agent.name, team_task, event_type,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send wecom notification: {e}")

            elif channel.channel_type == "dingtalk":
                extra = channel.extra_config or {}
                app_key = extra.get("app_key")
                app_secret = extra.get("app_secret")
                if app_key and app_secret:
                    try:
                        await _send_dingtalk_notification(
                            app_key, app_secret,
                            agent.name, team_task, event_type,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send dingtalk notification: {e}")


async def _send_wecom_notification(
    corp_id: str, secret: str, agent_id_wecom: str | None,
    creator: User, agent_name: str, task: TeamTask, event_type: str,
) -> None:
    """Send a WeCom (企业微信) notification."""
    import httpx

    # Get access token
    async with httpx.AsyncClient() as client:
        token_resp = await client.get(
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
            params={"corpid": corp_id, "corpsecret": secret},
        )
        access_token = token_resp.json().get("access_token")
        if not access_token:
            return

        if event_type == "plan_ready":
            content = f"📋 [{agent_name}] 已制定执行计划\n任务: {task.title}\n请登录 Clawith 查看。"
        elif event_type == "task_completed":
            content = f"✅ [{agent_name}] 已完成任务\n任务: {task.title}\n请登录 Clawith 检阅结果。"
        else:
            content = f"[{agent_name}] 任务更新: {task.title}"

        msg_data = {
            "touser": creator.email or "@all",
            "msgtype": "text",
            "agentid": int(agent_id_wecom) if agent_id_wecom else 0,
            "text": {"content": content},
        }

        await client.post(
            f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}",
            json=msg_data,
        )


async def _send_dingtalk_notification(
    app_key: str, app_secret: str,
    agent_name: str, task: TeamTask, event_type: str,
) -> None:
    """Send a DingTalk notification."""
    import httpx

    async with httpx.AsyncClient() as client:
        # Get access token
        token_resp = await client.post(
            "https://oapi.dingtalk.com/gettoken",
            params={"appkey": app_key, "appsecret": app_secret},
        )
        access_token = token_resp.json().get("access_token")
        if not access_token:
            return

        if event_type == "plan_ready":
            content = f"📋 [{agent_name}] 已制定执行计划\n任务: {task.title}\n请登录 Clawith 查看。"
        elif event_type == "task_completed":
            content = f"✅ [{agent_name}] 已完成任务\n任务: {task.title}\n请登录 Clawith 检阅结果。"
        else:
            content = f"[{agent_name}] 任务更新: {task.title}"

        # Send work notification (requires user_id, simplified here)
        logger.info(f"DingTalk notification: {content}")
