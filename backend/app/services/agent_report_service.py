"""Agent Daily Report generation service.

This service generates comprehensive daily reports by aggregating data from:
1. agent_activity_logs - All actions taken by the agent
2. chat_messages - Conversations and tool calls
3. tasks - Formal task assignments
4. team_tasks - Team-level tasks
"""

import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.task import Task
from app.models.team_task import TeamTask, AgentDailyReport
from app.models.activity_log import AgentActivityLog as ActivityLog
from app.models.audit import ChatMessage


async def generate_agent_report(
    db: AsyncSession,
    agent_id: uuid.UUID,
    report_date: datetime,
    tenant_id: Optional[uuid.UUID] = None,
) -> AgentDailyReport:
    """
    Generate a comprehensive daily report for a digital employee.
    
    This aggregates data from multiple sources:
    - Activity logs (tool calls, messages sent, etc.)
    - Chat messages (including tool_call messages with task details)
    - Formal tasks from tasks table
    - Team tasks assigned to this agent
    """
    
    # Get agent info
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise ValueError(f"Agent {agent_id} not found")
    
    # Calculate date range for "today"
    start_of_day = report_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)
    
    # Check if report already exists
    existing_result = await db.execute(
        select(AgentDailyReport).where(
            AgentDailyReport.agent_id == agent_id,
            func.date(AgentDailyReport.report_date) == report_date.date(),
        )
    )
    existing_report = existing_result.scalar_one_or_none()
    
    # ═══════════════════════════════════════════════════════════════════
    # 1. Get activity logs for today
    # ═══════════════════════════════════════════════════════════════════
    activities_result = await db.execute(
        select(ActivityLog).where(
            ActivityLog.agent_id == agent_id,
            ActivityLog.created_at >= start_of_day,
            ActivityLog.created_at < end_of_day,
        ).order_by(ActivityLog.created_at)
    )
    activities = activities_result.scalars().all()
    
    # ═══════════════════════════════════════════════════════════════════
    # 2. Get chat messages (especially tool_call messages)
    # ═══════════════════════════════════════════════════════════════════
    chat_result = await db.execute(
        select(ChatMessage).where(
            ChatMessage.agent_id == agent_id,
            ChatMessage.created_at >= start_of_day,
            ChatMessage.created_at < end_of_day,
        ).order_by(ChatMessage.created_at)
    )
    chat_messages = chat_result.scalars().all()
    
    # ═══════════════════════════════════════════════════════════════════
    # 3. Get formal tasks from tasks table
    # ═══════════════════════════════════════════════════════════════════
    completed_tasks_result = await db.execute(
        select(Task).where(
            Task.agent_id == agent_id,
            Task.status == "done",
            Task.completed_at >= start_of_day,
            Task.completed_at < end_of_day,
        )
    )
    formal_completed_tasks = completed_tasks_result.scalars().all()
    
    in_progress_result = await db.execute(
        select(Task).where(
            Task.agent_id == agent_id,
            Task.status == "doing",
        )
    )
    formal_in_progress_tasks = in_progress_result.scalars().all()
    
    # ═══════════════════════════════════════════════════════════════════
    # 4. Get team tasks
    # ═══════════════════════════════════════════════════════════════════
    team_tasks_result = await db.execute(
        select(TeamTask).where(
            TeamTask.assignee_agent_id == agent_id,
        )
    )
    team_tasks = team_tasks_result.scalars().all()
    
    # ═══════════════════════════════════════════════════════════════════
    # Process and extract work items from activity logs
    # ═══════════════════════════════════════════════════════════════════
    
    # Extract completed work items from activities and chat
    completed_items = []
    in_progress_items = []
    tool_calls_summary = {
        "web_search": 0,
        "write_file": 0,
        "read_file": 0,
        "send_message": 0,
        "other": 0,
    }
    messages_sent_count = 0
    files_written = []
    tasks_from_focus = []  # Tasks extracted from focus.md updates
    
    # Process activity logs
    for activity in activities:
        action = activity.action_type
        summary = activity.summary
        
        if action == "tool_call":
            # Count tool calls by type
            if "web_search" in summary.lower():
                tool_calls_summary["web_search"] += 1
            elif "write_file" in summary.lower():
                tool_calls_summary["write_file"] += 1
                # Extract file name
                match = re.search(r'Written to ([^\s\(]+)', summary)
                if match:
                    files_written.append(match.group(1))
            elif "read_file" in summary.lower():
                tool_calls_summary["read_file"] += 1
            elif "send_message" in summary.lower() or "send_channel" in summary.lower():
                tool_calls_summary["send_message"] += 1
            else:
                tool_calls_summary["other"] += 1
                
        elif action in ("agent_msg_sent", "feishu_msg_sent", "web_msg_sent", "chat_reply"):
            messages_sent_count += 1
    
    # Process chat messages to extract task information
    for msg in chat_messages:
        if msg.role == "tool_call":
            try:
                content = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                tool_name = content.get("name", "")
                tool_args = content.get("args", {})
                tool_result = content.get("result", "")
                
                # Extract task info from focus.md updates
                if tool_name == "write_file" and "focus.md" in tool_args.get("path", ""):
                    focus_content = tool_args.get("content", "")
                    # Parse focus.md to find task status
                    task_lines = focus_content.split("\n")
                    for line in task_lines:
                        if line.strip().startswith("- [x]") or line.strip().startswith("- [X]"):
                            # Completed task
                            task_name = re.sub(r'^- \[[xX]\]\s*', '', line.strip())
                            task_name = re.sub(r'^[a-z_]+:\s*', '', task_name)  # Remove task id prefix
                            if task_name and task_name not in [t["title"] for t in completed_items]:
                                completed_items.append({
                                    "id": str(uuid.uuid4()),
                                    "title": task_name[:200],
                                    "source": "focus.md",
                                    "completed_at": msg.created_at.isoformat(),
                                })
                        elif line.strip().startswith("- [/]") or line.strip().startswith("- [ ]"):
                            # In progress or pending task
                            task_name = re.sub(r'^- \[[/\s]\]\s*', '', line.strip())
                            task_name = re.sub(r'^[a-z_]+:\s*', '', task_name)
                            if task_name and task_name not in [t["title"] for t in in_progress_items]:
                                in_progress_items.append({
                                    "id": str(uuid.uuid4()),
                                    "title": task_name[:200],
                                    "source": "focus.md",
                                    "type": "agent_task",
                                })
                
                # Extract task info from agent messages
                elif tool_name == "send_message_to_agent":
                    message_content = tool_args.get("message", "")
                    msg_type = tool_args.get("msg_type", "")
                    
                    # Check for task completion reports
                    if "✅" in message_content or "完成" in message_content or msg_type == "task_update":
                        # Extract task title from message
                        lines = message_content.split("\n")
                        for line in lines:
                            if "【" in line and "】" in line:
                                match = re.search(r'【[^】]*】(.+?)(?:\n|$)', line)
                                if match:
                                    task_title = match.group(1).strip()
                                    if task_title and len(task_title) > 5:
                                        if task_title not in [t["title"] for t in completed_items]:
                                            completed_items.append({
                                                "id": str(uuid.uuid4()),
                                                "title": task_title[:200],
                                                "source": "agent_message",
                                                "completed_at": msg.created_at.isoformat(),
                                            })
                                        break
                            
            except (json.JSONDecodeError, TypeError):
                continue
    
    # Add formal tasks
    for task in formal_completed_tasks:
        if task.title not in [t["title"] for t in completed_items]:
            completed_items.append({
                "id": str(task.id),
                "title": task.title,
                "source": "tasks",
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            })
    
    for task in formal_in_progress_tasks:
        if task.title not in [t["title"] for t in in_progress_items]:
            in_progress_items.append({
                "id": str(task.id),
                "title": task.title,
                "source": "tasks",
                "type": "agent_task",
            })
    
    # Add team tasks
    for task in team_tasks:
        task_info = {
            "id": str(task.id),
            "title": task.title,
            "source": "team_tasks",
            "type": "team_task",
        }
        if task.status == "completed":
            if task.title not in [t["title"] for t in completed_items]:
                task_info["completed_at"] = task.completed_at.isoformat() if task.completed_at else None
                completed_items.append(task_info)
        elif task.status == "in_progress":
            if task.title not in [t["title"] for t in in_progress_items]:
                in_progress_items.append(task_info)
    
    # ═══════════════════════════════════════════════════════════════════
    # Generate summary text
    # ═══════════════════════════════════════════════════════════════════
    summary_parts = []
    
    # Task completion summary
    if completed_items:
        summary_parts.append(f"今日完成了 {len(completed_items)} 项任务。")
        # List top 3 completed tasks
        for i, task in enumerate(completed_items[:3]):
            summary_parts.append(f"  {i+1}. {task['title'][:50]}{'...' if len(task['title']) > 50 else ''}")
    else:
        summary_parts.append("今日暂无完成的任务。")
    
    # In progress tasks
    if in_progress_items:
        summary_parts.append(f"当前有 {len(in_progress_items)} 项任务正在进行中。")
    
    # Work activity summary
    total_tool_calls = sum(tool_calls_summary.values())
    if total_tool_calls > 0:
        activity_summary = []
        if tool_calls_summary["web_search"] > 0:
            activity_summary.append(f"网络搜索 {tool_calls_summary['web_search']} 次")
        if tool_calls_summary["write_file"] > 0:
            activity_summary.append(f"编写文件 {tool_calls_summary['write_file']} 个")
        if tool_calls_summary["send_message"] > 0:
            activity_summary.append(f"发送消息 {tool_calls_summary['send_message']} 条")
        
        if activity_summary:
            summary_parts.append("工作活动：" + "、".join(activity_summary) + "。")
    
    if messages_sent_count > 0:
        summary_parts.append(f"共发送 {messages_sent_count} 条消息。")
    
    summary = "\n".join(summary_parts)
    
    # ═══════════════════════════════════════════════════════════════════
    # Generate highlights
    # ═══════════════════════════════════════════════════════════════════
    highlights = []
    if len(completed_items) >= 3:
        highlights.append(f"高效工作日：完成了 {len(completed_items)} 项任务")
    if files_written:
        # List notable files
        notable_files = [f for f in files_written if not f.endswith("focus.md")][:3]
        if notable_files:
            highlights.append(f"产出文档：{', '.join([f.split('/')[-1] for f in notable_files])}")
    if tool_calls_summary["web_search"] >= 5:
        highlights.append(f"深度调研：进行了 {tool_calls_summary['web_search']} 次信息搜索")
    
    # ═══════════════════════════════════════════════════════════════════
    # Create or update report
    # ═══════════════════════════════════════════════════════════════════
    if existing_report:
        report = existing_report
        report.summary = summary
        report.completed_tasks = completed_items
        report.in_progress_tasks = in_progress_items
        report.planned_tasks = []  # TODO: Extract from focus.md
        report.highlights = highlights
        report.tasks_completed_count = len(completed_items)
        report.tasks_in_progress_count = len(in_progress_items)
        report.messages_sent = messages_sent_count
        report.tokens_used = agent.tokens_used_today or 0
        report.generated_at = datetime.utcnow()
    else:
        report = AgentDailyReport(
            agent_id=agent_id,
            report_date=report_date,
            summary=summary,
            completed_tasks=completed_items,
            in_progress_tasks=in_progress_items,
            planned_tasks=[],
            blockers=[],
            highlights=highlights,
            tasks_completed_count=len(completed_items),
            tasks_in_progress_count=len(in_progress_items),
            messages_sent=messages_sent_count,
            tokens_used=agent.tokens_used_today or 0,
            visibility="leader",
            is_auto_generated=True,
            generated_at=datetime.utcnow(),
            report_status="draft",
            tenant_id=tenant_id or agent.tenant_id,
        )
        db.add(report)
    
    await db.flush()
    return report


async def generate_all_agent_reports(db: AsyncSession, tenant_id: Optional[uuid.UUID] = None):
    """Generate daily reports for all active agents."""
    
    query = select(Agent).where(Agent.status.in_(["running", "idle"]))
    if tenant_id:
        query = query.where(Agent.tenant_id == tenant_id)
    
    result = await db.execute(query)
    agents = result.scalars().all()
    
    report_date = datetime.utcnow()
    reports = []
    
    for agent in agents:
        try:
            report = await generate_agent_report(db, agent.id, report_date, tenant_id)
            reports.append(report)
        except Exception as e:
            print(f"Failed to generate report for agent {agent.id}: {e}")
            continue
    
    await db.commit()
    return reports
