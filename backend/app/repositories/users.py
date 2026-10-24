import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, UserPreferences


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def get_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    return db.get(User, user_id)


def create_user(db: Session, *, email: str, password_hash: str, display_name: str) -> User:
    """Insert a user with a default preferences row. Caller commits."""
    user = User(email=email, password_hash=password_hash, display_name=display_name)
    user.preferences = UserPreferences()
    db.add(user)
    db.flush()  # raises IntegrityError on a duplicate email
    return user


def get_preferences(db: Session, user_id: uuid.UUID) -> UserPreferences | None:
    return db.get(UserPreferences, user_id)
