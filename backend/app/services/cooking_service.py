"""The conversational cooking assistant and one-shot recipe generation.

Flow: build a bounded, user-scoped prompt -> ask the configured text provider -> validate the
reply against a strict schema -> run the deterministic allergen/diet gate -> persist.
A reply whose recipe fails the gate is stored with an explicit warning and **without** the
recipe; the model's prose is never shown as if the recipe were usable.
"""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.ai.cooking import (
    CHAT_JSON_SCHEMA, RECIPE_JSON_SCHEMA, ChatReplyDraft, RecipeDraft, build_chat_messages,
    build_recipe_prompt, parse_chat, parse_recipe,
)
from app.ai.text import ChatTurn, TextProvider, TextProviderInfo
from app.core.config import Settings
from app.core.errors import NotFoundError
from app.core.limits import limiter
from app.domain.diet_rules import DIET_LABELS, declared_but_unverifiable
from app.domain.recipes import allergy_disclosure, enforce
from app.models.cooking import CookingConversation, CookingMessage, MessageRole
from app.models import User, UserPreferences
from app.repositories import conversations as convo_repo
from app.repositories import recipes as recipe_repo
from app.schemas.common import Page
from app.schemas.cooking import (
    ChatRequest, ChatResponse, Choice, ConversationDetail, ConversationSummary,
    CookingCapabilities, GenerateRecipeRequest, MessageOut, RecipeRead, TextCapability,
)
from app.services import recipe_service
from app.services.preferences_service import get_preferences

logger = logging.getLogger("app.cooking")

MAX_REPLY_CHARS = 6000


def capabilities(settings: Settings) -> CookingCapabilities:
    if settings.text_provider == "openai_compatible":
        from app.ai.openai_vision import is_local_url

        text = TextCapability(
            configured=True, provider="openai_compatible", model=settings.text_api_model,
            external=not is_local_url(settings.text_api_base_url),
        )
    elif not settings.ollama_enabled:
        text = TextCapability(
            configured=False, provider="ollama",
            message="The cooking assistant is not enabled on this server. Recipes cannot be generated.",
        )
    elif not settings.ollama_text_model:
        text = TextCapability(
            configured=False, provider="ollama",
            message="No text model is configured on this server (OLLAMA_TEXT_MODEL).",
        )
    else:
        text = TextCapability(
            configured=True, provider="ollama", model=settings.ollama_text_model, external=False
        )
    return CookingCapabilities(
        text=text,
        diets=[Choice(value=k, label=v) for k, v in DIET_LABELS.items()],
        context_messages=settings.cooking_context_messages,
    )


def _restrictions(db: Session, user: User) -> tuple[list[str], list[str]]:
    prefs: UserPreferences = get_preferences(db, user)
    return list(prefs.allergies), list(prefs.dietary_preferences)


def _message_out(row: CookingMessage) -> MessageOut:
    return MessageOut(
        id=row.id, role=row.role.value, content=row.content, recipe_id=row.recipe_id,
        warnings=list(row.warnings or []), created_at=row.created_at,
    )


def _history(db: Session, conversation_id: uuid.UUID, settings: Settings) -> list[tuple[str, str]]:
    rows = convo_repo.recent_messages(db, conversation_id, settings.cooking_context_messages)
    turns: list[tuple[str, str]] = []
    used = 0
    for row in rows:  # newest N messages, trimmed by characters from the oldest end
        content = row.content[:MAX_REPLY_CHARS]
        used += len(content)
        if used > settings.cooking_context_chars:
            break
        turns.append((row.role.value, content))
    return turns


def _create_conversation(db: Session, user: User, title: str) -> CookingConversation:
    return convo_repo.add(
        db, CookingConversation(owner_id=user.id, title=" ".join(title.split())[:200] or "Cooking")
    )


def _store(
    db: Session,
    user: User,
    conversation: CookingConversation,
    role: MessageRole,
    content: str,
    *,
    recipe_id: uuid.UUID | None = None,
    warnings: list[str] | None = None,
) -> CookingMessage:
    return convo_repo.add_message(
        db,
        CookingMessage(
            conversation_id=conversation.id,
            owner_id=user.id,
            role=role,
            content=content[:MAX_REPLY_CHARS],
            recipe_id=recipe_id,
            warnings=warnings or [],
            position=convo_repo.next_position(db, conversation.id),
        ),
    )


def chat(
    db: Session,
    settings: Settings,
    user: User,
    req: ChatRequest,
    make_provider: Callable[[], TextProvider],
) -> ChatResponse:
    limiter("cooking assistant", settings.cooking_rate_limit_per_minute).check(str(user.id))
    allergies, diets = _restrictions(db, user)

    if req.conversation_id is not None:
        conversation = convo_repo.get_owned(db, req.conversation_id, user.id)
        if conversation is None:
            raise NotFoundError("Conversation not found.", code="conversation_not_found")
    else:
        conversation = _create_conversation(db, user, req.message)

    provider = make_provider()  # raises a clear error when no model is configured
    history = _history(db, conversation.id, settings)
    messages = [
        ChatTurn(**m)
        for m in build_chat_messages(
            history=history, user_message=req.message, allergies=allergies, diets=diets,
            recipe_allowed=True,
        )
    ]
    logger.info("cooking_chat_started user_id=%s conversation_id=%s model=%s",
                user.id, conversation.id, provider.info.model)
    raw = provider.complete(messages, CHAT_JSON_SCHEMA)
    reply: ChatReplyDraft = parse_chat(raw)

    user_row = _store(db, user, conversation, MessageRole.USER, req.message)
    warnings = list(allergy_disclosure(
        reply.recipe, allergies
    )["warnings"]) if reply.recipe else []
    warnings += [
        f"“{d}” cannot be verified from an ingredient list; check certification yourself."
        for d in declared_but_unverifiable(diets)
    ]
    recipe_row = None
    recipe_out: RecipeRead | None = None
    if reply.recipe is not None:
        conflicts = enforce(reply.recipe, allergies, diets)
        if conflicts:
            warnings.append(
                "A suggested recipe was withheld because it conflicts with your restrictions: "
                + "; ".join(c.message for c in conflicts[:4])
            )
        else:
            recipe_row = recipe_service.create_suggested(
                db, user, reply.recipe,
                provider=provider.info, conversation_id=conversation.id,
            )
            recipe_out = recipe_service.to_read(recipe_row)

    content = reply.reply
    if reply.follow_up_questions:
        content += "\n\n" + "\n".join(f"· {q}" for q in reply.follow_up_questions)
    assistant_row = _store(
        db, user, conversation, MessageRole.ASSISTANT, content,
        recipe_id=recipe_row.id if recipe_row else None, warnings=warnings,
    )
    conversation.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(user_row)
    db.refresh(assistant_row)
    logger.info("cooking_chat_finished user_id=%s conversation_id=%s recipe=%s",
                user.id, conversation.id, bool(recipe_row))
    return ChatResponse(
        conversation_id=conversation.id,
        user_message=_message_out(user_row),
        assistant_message=_message_out(assistant_row),
        recipe=recipe_out,
        provider=provider.info,
    )


def generate_recipe(
    db: Session,
    settings: Settings,
    user: User,
    req: GenerateRecipeRequest,
    make_provider: Callable[[], TextProvider],
) -> RecipeRead:
    limiter("cooking assistant", settings.cooking_rate_limit_per_minute).check(str(user.id))
    allergies, diets = _restrictions(db, user)
    if req.mode == "from_ingredients" and not req.ingredients:
        from app.core.errors import AppError

        raise AppError("List at least one ingredient.", code="invalid_input", status_code=422)

    conversation = None
    if req.conversation_id is not None:
        conversation = convo_repo.get_owned(db, req.conversation_id, user.id)
        if conversation is None:
            raise NotFoundError("Conversation not found.", code="conversation_not_found")

    provider = make_provider()
    prompt = build_recipe_prompt(
        ingredients=req.ingredients, allergies=allergies, diets=diets,
        servings=req.servings, style=req.mode,
    )
    logger.info("recipe_generate_started user_id=%s model=%s", user.id, provider.info.model)
    raw = provider.complete(
        [ChatTurn(role="system", content="You are a careful recipe writer."),
         ChatTurn(role="user", content=prompt)],
        RECIPE_JSON_SCHEMA,
    )
    draft: RecipeDraft = parse_recipe(raw)
    row = recipe_service.create_suggested(
        db, user, draft, provider=provider.info,
        conversation_id=conversation.id if conversation else None,
    )
    db.commit()
    db.refresh(row)
    logger.info("recipe_generate_finished user_id=%s recipe_id=%s", user.id, row.id)
    return recipe_service.to_read(row)


# --------------------------------------------------------------------------- conversations
def _summary(db: Session, row: CookingConversation) -> ConversationSummary:
    return ConversationSummary(
        id=row.id, title=row.title, message_count=convo_repo.message_count(db, row.id),
        created_at=row.created_at, updated_at=row.updated_at,
    )


def list_conversations(db: Session, user: User, *, page: int, page_size: int) -> Page[ConversationSummary]:
    rows, total = convo_repo.list_page(db, user.id, limit=page_size, offset=(page - 1) * page_size)
    return Page.build([_summary(db, r) for r in rows], total, page, page_size)


def get_conversation(db: Session, user: User, conversation_id: uuid.UUID) -> ConversationDetail:
    row = convo_repo.get_owned(db, conversation_id, user.id)
    if row is None:
        raise NotFoundError("Conversation not found.", code="conversation_not_found")
    recipes = recipe_repo.for_conversation(db, row.id)
    base = _summary(db, row)
    return ConversationDetail(
        **base.model_dump(),
        messages=[_message_out(m) for m in convo_repo.all_messages(db, row.id)],
        recipes=[recipe_service.summary(r) for r in recipes],
    )


def delete_conversation(db: Session, user: User, conversation_id: uuid.UUID) -> None:
    row = convo_repo.get_owned(db, conversation_id, user.id)
    if row is None:
        raise NotFoundError("Conversation not found.", code="conversation_not_found")
    db.delete(row)  # messages cascade; suggested recipes keep their content (conversation_id null)
    db.commit()
    logger.info("conversation_deleted user_id=%s conversation_id=%s", user.id, conversation_id)


def provider_info(provider: TextProvider) -> TextProviderInfo:
    return provider.info