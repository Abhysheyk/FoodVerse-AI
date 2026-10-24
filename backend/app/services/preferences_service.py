from sqlalchemy.orm import Session

from app.models import User, UserPreferences
from app.repositories import users as user_repo
from app.schemas.user import PreferencesUpdate


def get_preferences(db: Session, user: User) -> UserPreferences:
    prefs = user_repo.get_preferences(db, user.id)
    if prefs is None:  # defensive: every user is created with a row
        prefs = UserPreferences(user_id=user.id)
        db.add(prefs)
        db.commit()
        db.refresh(prefs)
    return prefs


def update_preferences(db: Session, user: User, data: PreferencesUpdate) -> UserPreferences:
    prefs = get_preferences(db, user)
    prefs.unit_system = data.unit_system
    prefs.dietary_preferences = list(data.dietary_preferences)
    prefs.allergies = list(data.allergies)
    db.commit()
    db.refresh(prefs)
    return prefs
