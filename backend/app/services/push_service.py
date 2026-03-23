"""Push delivery service for OpenClaw agents.

When an OpenClaw agent has a push_url configured, messages are POSTed
to that URL immediately instead of waiting for the agent to poll.
"""

import json
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Reusable async HTTP client (connection pooling)
_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client


async def push_message_to_agent(
    push_url: str,
    push_headers: dict | None,
    push_agent_id: str | None,
    sender_name: str,
    conversation_id: str | None,
    content: str,
    history: list[dict] | None = None,
    agent_name: str = "Clawith",
    message_id: str | None = None,
    report_url: str | None = None,
    report_api_key: str | None = None,
) -> bool:
    """POST a message to an OpenClaw agent's push endpoint.

    Request body format:
    {
        "message": "sender: 张三\\nconversation_id: xxx\\nmessage_id: <uuid>\\nreport_url: ...\\ncontent: 你好\\nhistory: [...]",
        "agentId": "<push_agent_id>",
        "name": "Clawith",
        "deliver": false
    }

    Returns True on success, False on failure.
    """
    # Build the message string
    parts = [
        f"sender: {sender_name}",
        f"conversation_id: {conversation_id or 'unknown'}",
    ]
    if message_id:
        parts.append(f"message_id: {message_id}")
    if report_url:
        parts.append(f"report_url: {report_url}")
    if report_api_key:
        parts.append(f"report_api_key: {report_api_key}")
    parts.append(f"content: {content}")
    if history:
        parts.append(f"history: {json.dumps(history, ensure_ascii=False)}")

    message_str = "\n".join(parts)

    payload = {
        "message": message_str,
        "agentId": push_agent_id or "coordinator",
        "name": agent_name,
        "deliver": False,
    }

    # Build headers
    headers = {"Content-Type": "application/json"}
    if push_headers:
        headers.update(push_headers)

    try:
        client = _get_client()
        resp = await client.post(push_url, json=payload, headers=headers)
        if resp.status_code < 300:
            logger.info(
                f"[Push] Successfully pushed to {push_url}, "
                f"agentId={push_agent_id}, sender={sender_name}, status={resp.status_code}"
            )
            return True
        else:
            logger.warning(
                f"[Push] Push to {push_url} returned {resp.status_code}: {resp.text[:200]}"
            )
            return False
    except Exception as e:
        logger.error(f"[Push] Failed to push to {push_url}: {e}")
        return False
