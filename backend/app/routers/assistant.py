"""Recruiter assistant endpoints: chat and direct tool calls."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..ai.llm import llm_available
from ..assistant.agent import run_turn
from ..assistant.tools import TOOLS, execute_tool
from ..db import get_db
from ..deps import OrgContext, org_context
from ..ratelimit import hit

router = APIRouter(tags=["assistant"])


class ChatMessage(BaseModel):
    role: str
    content: str


class AssistantChatIn(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)
    job_id: str | None = None


class ToolCallIn(BaseModel):
    name: str
    arguments: dict = {}
    job_id: str | None = None


@router.post("/assistant/chat")
def assistant_chat(body: AssistantChatIn, ctx: OrgContext = Depends(org_context),
                   db: Session = Depends(get_db)):
    if not hit(f"assist:{ctx.user.id}", 30, 600):
        raise HTTPException(429, "Too many messages, please wait a few minutes")
    if not llm_available():
        return {"llm": False}
    history = [{"role": m.role, "content": m.content} for m in body.messages]
    return run_turn(db, ctx, history, body.job_id)


@router.post("/assistant/tool")
def assistant_tool(body: ToolCallIn, ctx: OrgContext = Depends(org_context),
                   db: Session = Depends(get_db)):
    """Direct tool call for quick actions (works without LLM)."""
    if body.name not in TOOLS:
        raise HTTPException(404, "Unknown tool")
    if not hit(f"assist-tool:{ctx.user.id}", 60, 600):
        raise HTTPException(429, "Too many requests")
    return execute_tool(db, ctx, body.name, body.arguments)
