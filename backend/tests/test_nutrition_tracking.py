from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.conftest import auth_headers, register_user

Make = Callable[..., TestClient]


def test_targets_round_trip(make_client: Make) -> None:
    c = make_client()
    tok = register_user(c, "a@example.com")
    r = c.put(
        "/api/v1/users/me/nutrition-target",
        headers=auth_headers(tok),
        json={"calories_min": 1800, "calories_max": 2200, "protein_g_min": 60},
    )
    assert r.status_code == 200, r.text
    assert r.json()["calories_min"] == 1800
    got = c.get("/api/v1/users/me/nutrition-target", headers=auth_headers(tok)).json()
    assert got["protein_g_min"] == 60
    assert c.delete(
        "/api/v1/users/me/nutrition-target", headers=auth_headers(tok)
    ).status_code == 204
    assert c.get(
        "/api/v1/users/me/nutrition-target", headers=auth_headers(tok)
    ).json()["calories_min"] is None


def test_targets_validation(make_client: Make) -> None:
    c = make_client()
    tok = register_user(c, "a@example.com")
    r = c.put(
        "/api/v1/users/me/nutrition-target",
        headers=auth_headers(tok),
        json={"calories_min": 2500, "calories_max": 2000},
    )
    assert r.status_code == 422


def test_tracking_renders_empty_range_without_invented_data(make_client: Make) -> None:
    c = make_client()
    tok = register_user(c, "a@example.com")
    body = c.get(
        "/api/v1/users/me/nutrition-target/tracking", headers=auth_headers(tok)
    ).json()
    assert body["days_with_data"] == 0
    assert body["chart_available"] is False
    assert len(body["days"]) == 7
    assert all(d["meals_logged"] == 0 for d in body["days"])


def test_tracking_aggregates_consumed_meals_only(make_client: Make) -> None:
    """The service counts meals in the meal log. Plans are NOT counted."""
    from app.db.session import get_session_factory
    from app.models import AnalysisRecord, AnalysisStatus, MealCategory, MealLog, ModuleKey
    from app.models import User
    from sqlalchemy import select

    c = make_client()
    tok = register_user(c, "a@example.com")
    # create two meals directly in the log
    with get_session_factory()() as db:
        user = db.scalar(select(User))
        assert user is not None
        today = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
        for i in range(2):
            rec = AnalysisRecord(
                owner_id=user.id,
                module=ModuleKey.FOOD_RECOGNITION,
                status=AnalysisStatus.COMPLETED,
                title=f"m{i}",
                result={
                    "totals": {"energy_kcal": {"low": 500.0, "high": 500.0, "complete": True}},
                },
            )
            db.add(rec)
            db.flush()
            db.add(
                MealLog(
                    analysis_id=rec.id,
                    owner_id=user.id,
                    eaten_at=today - timedelta(days=i),
                    category=MealCategory.LUNCH,
                    notes=None,
                    totals={"energy_kcal": {"low": 500.0, "high": 500.0, "complete": True}},
                    item_count=1,
                    items_label="x",
                )
            )
        db.commit()
    body = c.get(
        "/api/v1/users/me/nutrition-target/tracking", headers=auth_headers(tok)
    ).json()
    assert body["days_with_data"] == 2
    assert body["chart_available"] is False  # need >= 3 days
    total = sum(d["kcal_low"] for d in body["days"])
    assert total == 1000.0


def test_tracking_is_user_scoped(make_client: Make) -> None:
    c = make_client()
    tok = register_user(c, "a@example.com")
    bob = register_user(c, "b@example.com")
    r = c.get(
        "/api/v1/users/me/nutrition-target/tracking", headers=auth_headers(bob)
    )
    assert r.status_code == 200
    assert r.json()["days_with_data"] == 0
    assert tok != bob