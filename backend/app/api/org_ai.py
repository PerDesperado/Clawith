"""Organization AI chat API — a system-level AI for executives to query org data."""

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token, get_current_user
from app.database import async_session, get_db
from app.models.agent import Agent
from app.models.llm import LLMModel
from app.models.user import User
from app.services.org_ai_service import (
    get_org_overview,
    query_department_list,
    query_leader_summary,
    query_person_work,
    query_team_hierarchy,
    query_team_status,
    search_org_members,
)

router = APIRouter(prefix="/org-ai", tags=["org-ai"])

# ─── Tool definitions for the Organization AI ────────

ORG_AI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_team_status",
            "description": "查询某个团队/部门的工作状态，包括正在运行的数字员工数量、今日完成的任务、进行中的任务等。不传 department_id 则查询全公司。",
            "parameters": {
                "type": "object",
                "properties": {
                    "department_id": {
                        "type": "string",
                        "description": "部门ID，不传则查询全公司",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_person_work",
            "description": "查询某个人的工作内容，包括其绑定的数字员工的任务完成情况、进行中的任务等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "member_name": {
                        "type": "string",
                        "description": "成员姓名（模糊匹配）",
                    },
                    "member_id": {
                        "type": "string",
                        "description": "成员ID（精确匹配）",
                    },
                    "period": {
                        "type": "string",
                        "enum": ["today", "week", "month"],
                        "description": "查询时间范围：today=今天, week=本周, month=本月",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_org_overview",
            "description": "获取组织的整体概览，包括部门数量、成员数量、数字员工数量、今日任务完成数等。",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_departments",
            "description": "列出所有部门及其成员数量。",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_members",
            "description": "按姓名、职位或部门搜索组织成员。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_team_hierarchy",
            "description": "查询数字员工的组织层级结构。显示各部门的组长和组员关系，组长可以查看和汇总组员的工作。",
            "parameters": {
                "type": "object",
                "properties": {
                    "department_id": {
                        "type": "string",
                        "description": "部门ID，不传则查询全公司",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_leader_summary",
            "description": "查询某个组长数字员工的工作汇总，包括其团队成员的工作报告。组长有权限查看同组组员的工作内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "leader_name": {
                        "type": "string",
                        "description": "组长数字员工的名称（模糊匹配）",
                    },
                    "leader_id": {
                        "type": "string",
                        "description": "组长数字员工的ID（精确匹配）",
                    },
                },
            },
        },
    },
]


def _build_org_ai_system_prompt() -> str:
    """Build the system prompt for the Organization AI."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"""你是一个组织管理 AI 助手。你的职责是帮助管理者了解组织的运作情况。

## 当前时间
{now_str}

## 你的能力
你可以通过工具查询以下信息：
1. **团队状态** — 查询某个部门或全公司的工作状态（数字员工运行情况、任务完成情况）
2. **个人工作** — 查询某个成员的工作内容（通过其绑定的数字员工了解）
3. **组织概览** — 获取整个组织的高层级统计信息
4. **部门列表** — 列出所有部门
5. **成员搜索** — 按姓名、职位、部门搜索成员
6. **团队层级** — 查询数字员工的组长/组员结构（组长可查看组员工作）
7. **组长汇总** — 查询某个组长及其团队的工作汇总

## 组织结构说明
- 数字员工有两种角色：**组长**（Leader）和 **组员**（Member）
- 同一部门内，组长数字员工有权限查看组员的工作报告并汇总
- 每个部门可以有多个组长和组员

## 回答原则
- 用简洁、结构化的方式回答
- 如果用户问的是某个人的工作情况，先调用 query_person_work 获取数据
- 如果用户问的是某个部门的情况，先调用 query_team_status 或 query_team_hierarchy
- 如果用户问某个组长的团队汇总，调用 query_leader_summary
- 如果用户问的是整体概况，先调用 get_org_overview
- 使用 Markdown 格式组织回答
- 用中文回答（除非用户使用英文提问）
- 如果查询结果为空，诚实说明暂无数据
- 不要编造不存在的数据

## 注意事项
- 这里的"数字员工"是指 AI Agent，不是真人
- 每个真人员工可能绑定了一个或多个数字员工
- 任务完成情况来自数字员工的工作记录
"""


async def _execute_org_tool(
    tool_name: str,
    arguments: dict,
    tenant_id: uuid.UUID,
    db: AsyncSession,
) -> str:
    """Execute an organization AI tool and return the result as a string."""
    try:
        if tool_name == "query_team_status":
            result = await query_team_status(db, tenant_id, arguments.get("department_id"))
        elif tool_name == "query_person_work":
            result = await query_person_work(
                db, tenant_id,
                member_id=arguments.get("member_id"),
                member_name=arguments.get("member_name"),
                period=arguments.get("period", "today"),
            )
        elif tool_name == "get_org_overview":
            result = await get_org_overview(db, tenant_id)
        elif tool_name == "list_departments":
            result = await query_department_list(db, tenant_id)
        elif tool_name == "search_members":
            result = await search_org_members(db, tenant_id, arguments.get("query", ""))
        elif tool_name == "query_team_hierarchy":
            result = await query_team_hierarchy(db, tenant_id, arguments.get("department_id"))
        elif tool_name == "query_leader_summary":
            result = await query_leader_summary(
                db, tenant_id,
                leader_name=arguments.get("leader_name"),
                leader_id=arguments.get("leader_id"),
            )
        else:
            result = {"error": f"Unknown tool: {tool_name}"}
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


async def _get_llm_for_tenant(db: AsyncSession, tenant_id: uuid.UUID):
    """Get the first available LLM model for the tenant."""
    result = await db.execute(
        select(LLMModel).where(
            LLMModel.tenant_id == tenant_id,
            LLMModel.enabled == True,
        ).order_by(LLMModel.created_at.asc()).limit(1)
    )
    return result.scalar_one_or_none()


# ─── WebSocket Chat ─────────────────────────────────

@router.websocket("/ws")
async def org_ai_chat(
    websocket: WebSocket,
    token: str = Query(None),
):
    """WebSocket endpoint for Organization AI chat."""
    # Auth
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return
    payload = decode_access_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Invalid token")
        return
    
    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()

    # Get user and tenant
    async with async_session() as db:
        user_r = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
        user = user_r.scalar_one_or_none()
        if not user or not user.tenant_id:
            await websocket.send_json({"type": "error", "content": "用户未关联公司"})
            await websocket.close()
            return
        tenant_id = user.tenant_id

    # Conversation history (in-memory for session)
    conversation: list[dict] = []
    system_prompt = _build_org_ai_system_prompt()

    try:
        while True:
            data = await websocket.receive_json()
            user_message = data.get("content", "").strip()
            if not user_message:
                continue

            conversation.append({"role": "user", "content": user_message})

            async with async_session() as db:
                # Get LLM
                llm_model = await _get_llm_for_tenant(db, tenant_id)
                if not llm_model:
                    await websocket.send_json({"type": "error", "content": "未配置 LLM 模型，请在公司设置中添加"})
                    continue

                from app.services.llm_client import create_llm_client, LLMMessage

                client = create_llm_client(
                    provider=llm_model.provider,
                    model=llm_model.model,
                    api_key=llm_model.api_key_encrypted,
                    base_url=llm_model.base_url or None,
                )

                # Build messages
                messages = [LLMMessage(role="system", content=system_prompt)]
                for msg in conversation[-20:]:  # Keep last 20 messages
                    messages.append(LLMMessage(role=msg["role"], content=msg["content"]))

                # LLM loop with tool calling
                max_iterations = 5
                for _ in range(max_iterations):
                    try:
                        response = await client.complete(
                            messages=messages,
                            tools=ORG_AI_TOOLS,
                            max_tokens=4096,
                        )
                    except Exception as e:
                        await websocket.send_json({"type": "error", "content": f"LLM 调用失败: {str(e)[:200]}"})
                        break

                    # Check for tool calls
                    if response.tool_calls:
                        # Send tool call info to client
                        for tc in response.tool_calls:
                            func = tc.get("function", {})
                            tc_name = func.get("name", "")
                            tc_args_raw = func.get("arguments", "{}")
                            try:
                                tc_args = json.loads(tc_args_raw) if isinstance(tc_args_raw, str) else tc_args_raw
                            except (json.JSONDecodeError, TypeError):
                                tc_args = {}
                            await websocket.send_json({
                                "type": "tool_call",
                                "name": tc_name,
                                "args": tc_args,
                            })

                        # Add assistant message with tool calls
                        messages.append(LLMMessage(
                            role="assistant",
                            content=response.content or "",
                            tool_calls=response.tool_calls,
                        ))

                        # Execute tools
                        for tc in response.tool_calls:
                            func = tc.get("function", {})
                            tc_name = func.get("name", "")
                            tc_args_raw = func.get("arguments", "{}")
                            try:
                                tc_args = json.loads(tc_args_raw) if isinstance(tc_args_raw, str) else tc_args_raw
                            except (json.JSONDecodeError, TypeError):
                                tc_args = {}
                            
                            tool_result = await _execute_org_tool(
                                tc_name, tc_args, tenant_id, db
                            )
                            
                            await websocket.send_json({
                                "type": "tool_result",
                                "name": tc_name,
                                "result": tool_result[:500],
                            })

                            messages.append(LLMMessage(
                                role="tool",
                                content=tool_result,
                                tool_call_id=tc.get("id", ""),
                            ))
                        continue  # Re-call LLM with tool results
                    
                    # No tool calls — final response
                    reply = response.content or ""
                    conversation.append({"role": "assistant", "content": reply})
                    await websocket.send_json({
                        "type": "message",
                        "role": "assistant",
                        "content": reply,
                    })
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "content": f"连接错误: {str(e)[:200]}"})
        except Exception:
            pass


# ─── REST endpoint for simple queries ────────────────

class OrgAIQuery(BaseModel):
    question: str


@router.post("/query")
async def org_ai_query(
    data: OrgAIQuery,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Simple REST endpoint for Organization AI queries (non-streaming)."""
    if not current_user.tenant_id:
        return {"error": "用户未关联公司"}

    llm_model = await _get_llm_for_tenant(db, current_user.tenant_id)
    if not llm_model:
        return {"error": "未配置 LLM 模型"}

    from app.services.llm_client import create_llm_client, LLMMessage

    client = create_llm_client(
        provider=llm_model.provider,
        model=llm_model.model,
        api_key=llm_model.api_key_encrypted,
        base_url=llm_model.base_url or None,
    )

    system_prompt = _build_org_ai_system_prompt()
    messages = [
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(role="user", content=data.question),
    ]

    max_iterations = 5
    for _ in range(max_iterations):
        try:
            response = await client.complete(
                messages=messages,
                tools=ORG_AI_TOOLS,
                max_tokens=4096,
            )
        except Exception as e:
            return {"error": f"LLM 调用失败: {str(e)[:200]}"}

        if response.tool_calls:
            messages.append(LLMMessage(
                role="assistant",
                content=response.content or "",
                tool_calls=response.tool_calls,
            ))
            for tc in response.tool_calls:
                func = tc.get("function", {})
                tc_name = func.get("name", "")
                tc_args_raw = func.get("arguments", "{}")
                try:
                    args = json.loads(tc_args_raw) if isinstance(tc_args_raw, str) else tc_args_raw
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_result = await _execute_org_tool(
                    tc_name, args, current_user.tenant_id, db
                )
                messages.append(LLMMessage(
                    role="tool",
                    content=tool_result,
                    tool_call_id=tc.get("id", ""),
                ))
            continue

        return {"answer": response.content or ""}

    return {"answer": "查询超时，请重试"}
