"""Chainlit entrypoint for the Inventory Planner chat service."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from functools import lru_cache

import chainlit as cl

from services.chat.agent import InventoryChatAgent
from services.chat.auth import CognitoJwtVerifier
from services.chat.config import ChatConfig
from services.chat.gallery import AgentReply, gallery_markdown, strip_gallery
from services.chat.history import model_history
from services.chat.images import ImageUrlService
from services.chat.retrieval import InventoryRetriever
from services.chat.session_id import legacy_session_id, new_session_id, user_sub_from
from services.chat.sessions import SessionMessage, SessionStore, SessionSummary
from services.ingestion.embedding import EmbeddingClient
from services.ingestion.opensearch_client import OpenSearchInventoryClient

logger = logging.getLogger(__name__)
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

_WELCOME = (
    "Hi — I am Candywagon. Tell me about the event (theme, guest count, "
    "budget, and the rental look you want). I will search the indexed "
    "inventory and build a grounded shortlist. "
    "Live availability is not confirmed from the catalog alone."
)
_MAX_RESUME_ACTIONS = 4


@lru_cache(maxsize=1)
def _config() -> ChatConfig:
    return ChatConfig.from_env()


@lru_cache(maxsize=1)
def _verifier() -> CognitoJwtVerifier:
    cfg = _config()
    return CognitoJwtVerifier(
        user_pool_id=cfg.cognito_user_pool_id,
        app_client_id=cfg.cognito_app_client_id,
        region=cfg.aws_region,
    )


@lru_cache(maxsize=1)
def _agent() -> InventoryChatAgent:
    cfg = _config()
    embedder = EmbeddingClient(
        model_id=cfg.hf_embed_model_id,
        region=cfg.aws_region,
    )
    search = OpenSearchInventoryClient(
        endpoint=cfg.opensearch_endpoint,
        index=cfg.opensearch_index,
        region=cfg.aws_region,
    )
    retriever = InventoryRetriever(
        embedder=embedder,
        search=search,
        default_size=cfg.default_search_size,
        max_size=cfg.max_search_size,
    )
    images = ImageUrlService(
        bucket_name=cfg.data_bucket_name,
        images_prefix=cfg.images_prefix,
        region=cfg.aws_region,
        ttl_seconds=cfg.image_url_ttl_seconds,
    )
    return InventoryChatAgent(
        model_id=cfg.groq_model_id,
        region=cfg.aws_region,
        retriever=retriever,
        images=images,
        max_tool_rounds=cfg.max_tool_rounds,
    )


@lru_cache(maxsize=1)
def _sessions() -> SessionStore:
    cfg = _config()
    return SessionStore(
        table_name=cfg.dynamodb_table_name,
        region=cfg.aws_region,
        ttl_days=cfg.session_ttl_days,
    )


@cl.password_auth_callback
def password_auth_callback(username: str, password: str) -> cl.User | None:
    """Browser login form → Cognito email/password."""
    try:
        user = _verifier().authenticate_password(username, password)
    except Exception:
        logger.exception("cognito_password_login_failed")
        return None
    return cl.User(
        identifier=username,
        metadata={
            "sub": user.sub,
            "token_use": user.token_use,
            "username": user.username,
        },
    )


@cl.header_auth_callback
def header_auth_callback(headers: dict) -> cl.User | None:
    """API clients: Cognito access token (Authorization: Bearer …)."""
    auth = headers.get("Authorization") or headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    try:
        user = _verifier().verify_access_token(token)
    except Exception:
        logger.exception("cognito_jwt_rejected")
        return None
    return cl.User(
        identifier=user.username or user.sub,
        metadata={"sub": user.sub, "token_use": user.token_use},
    )


@cl.on_chat_start
async def on_chat_start() -> None:
    cfg_user = cl.user_session.get("user")
    user_sub = user_sub_from(cfg_user)
    session_id = _resolve_startup_session(user_sub)
    cl.user_session.set("session_id", session_id)

    prior = _sessions().list_messages(session_id, limit=100)
    actions = _session_actions(user_sub=user_sub, current_session_id=session_id)

    if prior:
        logger.info(
            "session_resumed session_id=%s turns=%s",
            session_id,
            len(prior),
        )
        await _replay_history(prior)
        await cl.Message(
            content=(
                "Your previous conversation was restored from DynamoDB. "
                "Use **New chat** to start a fresh thread, or open another recent chat below."
            ),
            actions=actions,
        ).send()
        return

    logger.info("session_started session_id=%s", session_id)
    await cl.Message(content=_WELCOME, actions=actions).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    cfg_user = cl.user_session.get("user")
    user_sub = user_sub_from(cfg_user)

    session_id = cl.user_session.get("session_id")
    if not session_id:
        session_id = _resolve_startup_session(user_sub)
    cl.user_session.set("session_id", session_id)

    store = _sessions()
    store.append(
        session_id=session_id,
        role="user",
        content=message.content,
        user_sub=user_sub,
    )

    history_messages = store.list_messages(session_id, limit=40)
    history = model_history(history_messages, strip=strip_gallery)
    # Current user message is already last; agent.reply adds it again if we pass
    # full history including it — strip the trailing user turn for history arg.
    if history and history[-1]["role"] == "user":
        prior = history[:-1]
    else:
        prior = history
    user_text = message.content

    try:
        answer = _agent().reply(user_message=user_text, history=prior)
    except Exception:
        logger.exception("agent_reply_failed session_id=%s", session_id)
        answer = AgentReply(
            text=(
                "I hit an error talking to the inventory services. "
                "Please try again in a moment."
            )
        )

    content = answer.text
    md = gallery_markdown(answer.gallery)
    if md:
        content = f"{content.rstrip()}\n{md}"

    store.append(
        session_id=session_id,
        role="assistant",
        content=content,
        user_sub=user_sub,
    )

    actions = _session_actions(user_sub=user_sub, current_session_id=session_id)
    await cl.Message(content=content, actions=actions).send()


@cl.action_callback("new_chat")
async def on_new_chat(action: cl.Action) -> None:
    del action
    cfg_user = cl.user_session.get("user")
    user_sub = user_sub_from(cfg_user)
    session_id = new_session_id(user_sub)
    cl.user_session.set("session_id", session_id)
    logger.info("session_new session_id=%s", session_id)
    actions = _session_actions(user_sub=user_sub, current_session_id=session_id)
    await cl.Message(
        content="Started a new chat. Previous threads stay saved in DynamoDB.",
        actions=actions,
    ).send()
    await cl.Message(content=_WELCOME).send()


@cl.action_callback("resume_chat")
async def on_resume_chat(action: cl.Action) -> None:
    session_id = (action.payload or {}).get("session_id") if action.payload else None
    if not session_id:
        await cl.Message(content="Could not resume that chat — missing session id.").send()
        return

    cfg_user = cl.user_session.get("user")
    user_sub = user_sub_from(cfg_user)
    session_id = str(session_id)
    if user_sub and not _user_owns_session(user_sub, session_id):
        await cl.Message(content="That chat does not belong to your account.").send()
        return

    cl.user_session.set("session_id", session_id)
    prior = _sessions().list_messages(session_id, limit=100)
    actions = _session_actions(user_sub=user_sub, current_session_id=session_id)
    logger.info(
        "session_switched session_id=%s turns=%s",
        session_id,
        len(prior),
    )
    if prior:
        await _replay_history(prior)
        await cl.Message(
            content="Switched to that saved chat.",
            actions=actions,
        ).send()
    else:
        await cl.Message(content=_WELCOME, actions=actions).send()


def _user_owns_session(user_sub: str, session_id: str) -> bool:
    """Allow resume only for threads that belong to this Cognito user."""
    if session_id.startswith(f"user:{user_sub}"):
        return True
    try:
        owned = {
            row.session_id
            for row in _sessions().list_sessions_for_user(user_sub, limit=20)
        }
    except Exception:
        logger.exception("ownership_check_failed session_id=%s", session_id)
        return False
    return session_id in owned


def _resolve_startup_session(user_sub: str | None) -> str:
    """Resume the newest thread for this user, or open the legacy / a new one."""
    if not user_sub:
        return new_session_id(None)

    store = _sessions()
    summaries = store.list_sessions_for_user(user_sub, limit=1)
    if summaries:
        return summaries[0].session_id

    legacy = legacy_session_id(user_sub)
    if store.list_messages(legacy, limit=1):
        return legacy
    return legacy


def _session_actions(
    *,
    user_sub: str | None,
    current_session_id: str,
) -> list[cl.Action]:
    actions: list[cl.Action] = [
        cl.Action(
            name="new_chat",
            payload={"action": "new_chat"},
            label="New chat",
        )
    ]
    if not user_sub:
        return actions

    try:
        summaries = _sessions().list_sessions_for_user(user_sub, limit=_MAX_RESUME_ACTIONS + 1)
    except Exception:
        logger.exception("list_sessions_failed user_sub=%s", user_sub)
        return actions

    others = [row for row in summaries if row.session_id != current_session_id]
    for index, row in enumerate(others[:_MAX_RESUME_ACTIONS], start=1):
        actions.append(
            cl.Action(
                name="resume_chat",
                payload={"session_id": row.session_id},
                label=_resume_label(index, row),
            )
        )
    return actions


def _resume_label(index: int, row: SessionSummary) -> str:
    when = datetime.fromtimestamp(row.last_timestamp / 1000, tz=timezone.utc).strftime(
        "%b %d %H:%M"
    )
    preview = row.preview or "chat"
    return f"Resume {index}: {when} — {preview[:40]}"


async def _replay_history(messages: list[SessionMessage]) -> None:
    """Re-render durable DynamoDB turns into the Chainlit UI."""
    for message in messages:
        if message.role == "user":
            await cl.Message(
                content=message.content,
                author="You",
                type="user_message",
            ).send()
        elif message.role == "assistant":
            await cl.Message(content=message.content).send()
