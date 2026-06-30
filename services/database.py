from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "database.db"

# Load environment variables (from .env file on local runs)
load_dotenv(BASE_DIR / ".env")

LANGUAGES = ["KR", "EN", "JP", "CN"]
USERS = ("Rin", "Friend")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    theme: Mapped[str] = mapped_column(String(50), nullable=False, default="Dịu mắt")
    decks: Mapped[list["Deck"]] = relationship(back_populates="user", cascade="all, delete")


class Deck(Base):
    __tablename__ = "decks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False, default="KR")
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: now_utc())
    user: Mapped[User] = relationship(back_populates="decks")
    vocabulary: Mapped[list["Vocabulary"]] = relationship(back_populates="deck", cascade="all, delete")


class Vocabulary(Base):
    __tablename__ = "vocabulary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deck_id: Mapped[int] = mapped_column(ForeignKey("decks.id"), nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    word: Mapped[str] = mapped_column(String(255), nullable=False)
    meaning: Mapped[str] = mapped_column(Text, nullable=False)
    example: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: now_utc())
    deck: Mapped[Deck] = relationship(back_populates="vocabulary")
    progress: Mapped["Progress"] = relationship(back_populates="vocabulary", cascade="all, delete", uselist=False)


class Progress(Base):
    __tablename__ = "progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vocabulary_id: Mapped[int] = mapped_column(ForeignKey("vocabulary.id"), unique=True, nullable=False)
    next_review: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: now_utc())
    remember_streak: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    wrong_count: Mapped[int] = mapped_column(Integer, default=0)
    last_review: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    vocabulary: Mapped[Vocabulary] = relationship(back_populates="progress")


TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")

if TURSO_DATABASE_URL and TURSO_AUTH_TOKEN:
    # Use remote Turso (libSQL) database
    url = TURSO_DATABASE_URL
    if url.startswith("libsql://"):
        url = url.replace("libsql://", "sqlite+libsql://")
    elif not url.startswith("sqlite+libsql://"):
        url = f"sqlite+libsql://{url}"
    
    # Append secure=true for security unless connecting to localhost
    if "secure=true" not in url and not url.startswith("sqlite+libsql://localhost"):
        if "?" in url:
            url += "&secure=true"
        else:
            url += "/?secure=true"

    engine = create_engine(
        url,
        connect_args={
            "auth_token": TURSO_AUTH_TOKEN,
        },
        future=True
    )
else:
    # Fallback to local SQLite database
    DATA_DIR.mkdir(exist_ok=True)
    engine = create_engine(f"sqlite:///{DB_PATH}", future=True)

SessionLocal = sessionmaker(bind=engine, future=True)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def init_db() -> None:
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        columns_decks = {row[1] for row in connection.execute(text("PRAGMA table_info(decks)"))}
        if "language" not in columns_decks:
            connection.execute(text("ALTER TABLE decks ADD COLUMN language VARCHAR(2) NOT NULL DEFAULT 'KR'"))
        
        columns_users = {row[1] for row in connection.execute(text("PRAGMA table_info(users)"))}
        if "theme" not in columns_users:
            connection.execute(text("ALTER TABLE users ADD COLUMN theme VARCHAR(50) NOT NULL DEFAULT 'Dịu mắt'"))

    with SessionLocal() as session:
        for name in USERS:
            user = session.scalar(select(User).where(User.name == name))
            if user is None:
                user = User(name=name, theme="Dịu mắt")
                session.add(user)
                session.flush()
                session.add(Deck(user_id=user.id, language="KR", name="Bài 1"))
            else:
                for deck in user.decks:
                    if not deck.language:
                        deck.language = "KR"
                    if deck.name == "Bai 1":
                        deck.name = "Bài 1"
        session.commit()


def get_users(session: Session) -> list[User]:
    return list(session.scalars(select(User).order_by(User.id)))


def get_decks(session: Session, user_id: int) -> list[Deck]:
    return list(session.scalars(select(Deck).where(Deck.user_id == user_id).order_by(Deck.created_at, Deck.id)))


def create_deck(session: Session, user_id: int, name: str, language: str = "KR") -> Deck:
    deck = Deck(user_id=user_id, language=language, name=name.strip())
    session.add(deck)
    session.commit()
    return deck


def add_vocabulary(session: Session, deck_id: int, row: dict[str, str]) -> Vocabulary:
    deck = session.get(Deck, deck_id)
    language = deck.language if deck is not None else row.get("language", "KR")
    vocab = Vocabulary(
        deck_id=deck_id,
        language=language,
        word=row["word"],
        meaning=row["meaning"],
        example=row.get("example", ""),
        note=row.get("note", ""),
    )
    session.add(vocab)
    session.flush()
    session.add(Progress(vocabulary_id=vocab.id, next_review=now_utc()))
    session.commit()
    return vocab


def update_schedule(session: Session, vocabulary_id: int, result: str) -> None:
    progress = session.scalar(select(Progress).where(Progress.vocabulary_id == vocabulary_id))
    if progress is None:
        progress = Progress(vocabulary_id=vocabulary_id)
        session.add(progress)

    current_streak = progress.remember_streak or 0
    if result == "forgot":
        progress.next_review = now_utc() + timedelta(minutes=15)
        progress.remember_streak = 0
        progress.wrong_count = (progress.wrong_count or 0) + 1
    elif result == "partial":
        progress.next_review = now_utc() + timedelta(hours=2)
        progress.correct_count = (progress.correct_count or 0) + 1
    else:
        new_streak = current_streak + 1
        interval_days = {1: 7, 2: 14, 3: 30, 4: 60}.get(new_streak, 90)
        progress.next_review = now_utc() + timedelta(days=interval_days)
        progress.remember_streak = new_streak
        progress.correct_count = (progress.correct_count or 0) + 1

    progress.last_review = now_utc()
    session.commit()


def due_vocabulary(session: Session, deck_id: int, limit: int) -> list[Vocabulary]:
    statement = (
        select(Vocabulary)
        .join(Progress)
        .where(Vocabulary.deck_id == deck_id, Progress.next_review <= now_utc())
        .order_by(Progress.next_review, Vocabulary.id)
        .limit(limit)
    )
    return list(session.scalars(statement))
