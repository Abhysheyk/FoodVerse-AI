import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import (
    AppSettings, CurrentUser, DbSession, TextFactory, require_csrf_header,
)
from app.schemas.common import MAX_PAGE_SIZE, Page
from app.schemas.cooking import (
    AttachNutritionRequest, ChatRequest, ChatResponse, ConversationDetail, ConversationSummary,
    CookingCapabilities, FavoriteRequest, GenerateRecipeRequest, RecipeRead, RecipeSummary,
    RecipeWrite,
)
from app.services import cooking_service, recipe_service

router = APIRouter(prefix="/cooking", tags=["cooking"])


@router.get("/capabilities", response_model=CookingCapabilities)
def capabilities(_user: CurrentUser, settings: AppSettings) -> CookingCapabilities:
    return cooking_service.capabilities(settings)


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_csrf_header)])
def chat(
    body: ChatRequest, user: CurrentUser, db: DbSession, settings: AppSettings,
    make_provider: TextFactory,
) -> ChatResponse:
    return cooking_service.chat(db, settings, user, body, make_provider)


@router.get("/conversations", response_model=Page[ConversationSummary])
def list_conversations(
    user: CurrentUser, db: DbSession,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
) -> Page[ConversationSummary]:
    return cooking_service.list_conversations(db, user, page=page, page_size=page_size)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> ConversationDetail:
    return cooking_service.get_conversation(db, user, conversation_id)


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf_header)],
)
def delete_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> Response:
    cooking_service.delete_conversation(db, user, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/recipes/generate", response_model=RecipeRead,
    status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf_header)],
)
def generate_recipe(
    body: GenerateRecipeRequest, user: CurrentUser, db: DbSession, settings: AppSettings,
    make_provider: TextFactory,
) -> RecipeRead:
    return cooking_service.generate_recipe(db, settings, user, body, make_provider)


@router.get("/recipes", response_model=Page[RecipeSummary])
def list_recipes(
    user: CurrentUser, db: DbSession,
    q: Annotated[str | None, Query(max_length=80)] = None,
    favorite: bool | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 10,
) -> Page[RecipeSummary]:
    return recipe_service.list_recipes(
        db, user, page=page, page_size=page_size, query=q, favorite=favorite
    )


@router.get("/recipes/{recipe_id}", response_model=RecipeRead)
def get_recipe(
    recipe_id: uuid.UUID, user: CurrentUser, db: DbSession,
    servings: Annotated[int | None, Query(ge=1, le=24)] = None,
) -> RecipeRead:
    recipe = recipe_service.get_owned_or_404(db, user, recipe_id)
    return recipe_service.scaled(recipe, servings) if servings else recipe_service.to_read(recipe)


@router.post(
    "/recipes/{recipe_id}/save", response_model=RecipeRead,
    dependencies=[Depends(require_csrf_header)],
)
def save_recipe(recipe_id: uuid.UUID, user: CurrentUser, db: DbSession) -> RecipeRead:
    return recipe_service.save_recipe(db, user, recipe_id)


@router.post(
    "/recipes/{recipe_id}/favorite", response_model=RecipeRead,
    dependencies=[Depends(require_csrf_header)],
)
def favorite_recipe(
    recipe_id: uuid.UUID, body: FavoriteRequest, user: CurrentUser, db: DbSession
) -> RecipeRead:
    return recipe_service.set_favorite(db, user, recipe_id, body.favorite)


@router.put(
    "/recipes/{recipe_id}", response_model=RecipeRead,
    dependencies=[Depends(require_csrf_header)],
)
def update_recipe(
    recipe_id: uuid.UUID, body: RecipeWrite, user: CurrentUser, db: DbSession
) -> RecipeRead:
    return recipe_service.update_recipe(db, user, recipe_id, body)


@router.post(
    "/recipes/{recipe_id}/nutrition", response_model=RecipeRead,
    dependencies=[Depends(require_csrf_header)],
)
def attach_nutrition(
    recipe_id: uuid.UUID, body: AttachNutritionRequest, user: CurrentUser,
    db: DbSession, settings: AppSettings,
) -> RecipeRead:
    return recipe_service.attach_nutrition(db, settings, user, recipe_id, body)


@router.delete(
    "/recipes/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf_header)],
)
def delete_recipe(recipe_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    recipe_service.delete_recipe(db, user, recipe_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)