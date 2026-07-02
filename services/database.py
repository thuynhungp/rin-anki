from __future__ import annotations

import os
import libsql
import json
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
    grammar_notes: Mapped[list["GrammarNote"]] = relationship(back_populates="user", cascade="all, delete")


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
    conjugations: Mapped[str | None] = mapped_column(Text, nullable=True, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: now_utc())
    deck: Mapped[Deck] = relationship(back_populates="vocabulary")
    progress: Mapped["Progress"] = relationship(back_populates="vocabulary", cascade="all, delete", uselist=False)

    @property
    def conjugation_data(self) -> dict[str, str]:
        if not self.conjugations:
            return {}
        try:
            return json.loads(self.conjugations)
        except Exception:
            return {}

    @conjugation_data.setter
    def conjugation_data(self, value: dict[str, str]) -> None:
        self.conjugations = json.dumps(value, ensure_ascii=False)


class Progress(Base):
    __tablename__ = "progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vocabulary_id: Mapped[int] = mapped_column(ForeignKey("vocabulary.id"), unique=True, nullable=False)
    next_review: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: now_utc())
    remember_streak: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    wrong_count: Mapped[int] = mapped_column(Integer, default=0)
    last_review: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    next_review_rev: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=lambda: now_utc())
    remember_streak_rev: Mapped[int | None] = mapped_column(Integer, default=0)
    correct_count_rev: Mapped[int | None] = mapped_column(Integer, default=0)
    wrong_count_rev: Mapped[int | None] = mapped_column(Integer, default=0)
    last_review_rev: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    vocabulary: Mapped[Vocabulary] = relationship(back_populates="progress")


class LibSQLConnectionProxy:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def create_function(self, *args, **kwargs):
        # Dummy function to satisfy SQLAlchemy's sqlite dialect
        return None


def get_connection():
    db_url = os.getenv("TURSO_DATABASE_URL")
    auth_token = os.getenv("TURSO_AUTH_TOKEN")
    
    if db_url and auth_token:
        # Connect to remote Turso database
        conn = libsql.connect(database=db_url, auth_token=auth_token)
    else:
        # Fallback to local SQLite database
        DATA_DIR.mkdir(exist_ok=True)
        conn = libsql.connect(str(DB_PATH))
        
    return LibSQLConnectionProxy(conn)


engine = create_engine("sqlite://", creator=get_connection, future=True)
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

        columns_vocab = {row[1] for row in connection.execute(text("PRAGMA table_info(vocabulary)"))}
        if "conjugations" not in columns_vocab:
            connection.execute(text("ALTER TABLE vocabulary ADD COLUMN conjugations TEXT DEFAULT '{}'"))

        columns_progress = {row[1] for row in connection.execute(text("PRAGMA table_info(progress)"))}
        if "next_review_rev" not in columns_progress:
            connection.execute(text("ALTER TABLE progress ADD COLUMN next_review_rev DATETIME"))
        if "remember_streak_rev" not in columns_progress:
            connection.execute(text("ALTER TABLE progress ADD COLUMN remember_streak_rev INTEGER DEFAULT 0"))
        if "correct_count_rev" not in columns_progress:
            connection.execute(text("ALTER TABLE progress ADD COLUMN correct_count_rev INTEGER DEFAULT 0"))
        if "wrong_count_rev" not in columns_progress:
            connection.execute(text("ALTER TABLE progress ADD COLUMN wrong_count_rev INTEGER DEFAULT 0"))
        if "last_review_rev" not in columns_progress:
            connection.execute(text("ALTER TABLE progress ADD COLUMN last_review_rev DATETIME"))

    with SessionLocal() as session:
        for name in USERS:
            user = session.scalar(select(User).where(User.name == name))
            if user is None:
                user = User(name=name, theme="Dịu mắt")
                session.add(user)
                session.flush()
                default_lang = "KR" if name == "Rin" else "EN"
                session.add(Deck(user_id=user.id, language=default_lang, name="Bài 1"))
            else:
                for deck in user.decks:
                    if not deck.language:
                        deck.language = "KR" if name == "Rin" else "EN"
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
    session.add(Progress(vocabulary_id=vocab.id, next_review=now_utc(), next_review_rev=now_utc()))
    session.commit()
    return vocab


def check_vocabulary_exists(session: Session, deck_id: int, word: str) -> bool:
    from sqlalchemy import func
    word_stripped = word.strip().lower()
    statement = select(Vocabulary).where(
        Vocabulary.deck_id == deck_id,
        func.lower(Vocabulary.word) == word_stripped
    )
    result = session.scalars(statement).all()
    return len(result) > 0



def update_schedule(session: Session, vocabulary_id: int, result: str, reversed: bool = False) -> None:
    progress = session.scalar(select(Progress).where(Progress.vocabulary_id == vocabulary_id))
    if progress is None:
        progress = Progress(vocabulary_id=vocabulary_id, next_review=now_utc(), next_review_rev=now_utc())
        session.add(progress)

    if not reversed:
        current_streak = progress.remember_streak or 0
        if result == "forgot":
            progress.next_review = now_utc() + timedelta(minutes=5)
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
    else:
        current_streak = progress.remember_streak_rev or 0
        if result == "forgot":
            progress.next_review_rev = now_utc() + timedelta(minutes=5)
            progress.remember_streak_rev = 0
            progress.wrong_count_rev = (progress.wrong_count_rev or 0) + 1
        elif result == "partial":
            progress.next_review_rev = now_utc() + timedelta(hours=2)
            progress.correct_count_rev = (progress.correct_count_rev or 0) + 1
        else:
            new_streak = current_streak + 1
            interval_days = {1: 7, 2: 14, 3: 30, 4: 60}.get(new_streak, 90)
            progress.next_review_rev = now_utc() + timedelta(days=interval_days)
            progress.remember_streak_rev = new_streak
            progress.correct_count_rev = (progress.correct_count_rev or 0) + 1
        progress.last_review_rev = now_utc()

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


def due_vocabulary_cards(session: Session, deck_id: int, limit: int) -> list[dict]:
    from sqlalchemy import or_
    now = now_utc()
    
    # Query vocabulary and progress
    statement = (
        select(Vocabulary)
        .join(Progress)
        .where(
            Vocabulary.deck_id == deck_id,
            or_(
                Progress.next_review <= now,
                Progress.next_review_rev == None,
                Progress.next_review_rev <= now
            )
        )
    )
    vocab_items = list(session.scalars(statement))
    
    # For each vocabulary item, check which sides are due
    cards = []
    for vocab in vocab_items:
        progress = vocab.progress
        if progress.next_review <= now:
            cards.append({
                "vocab": vocab,
                "reversed": False,
                "due_time": progress.next_review
            })
        
        rev_due = progress.next_review_rev if progress.next_review_rev is not None else now
        if progress.next_review_rev is None or progress.next_review_rev <= now:
            cards.append({
                "vocab": vocab,
                "reversed": True,
                "due_time": rev_due
            })
            
    # Sort cards by due_time so that more overdue cards are shown first
    cards.sort(key=lambda c: c["due_time"])
    
    # Take up to the limit
    selected_cards = cards[:limit]
    
    # Format them as the quiz expects
    return [
        {
            "id": c["vocab"].id,
            "word": c["vocab"].word,
            "meaning": c["vocab"].meaning,
            "example": c["vocab"].example,
            "note": c["vocab"].note,
            "reversed": c["reversed"],
        }
        for c in selected_cards
    ]


class GrammarNote(Base):
    __tablename__ = "grammar_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: now_utc())

    user: Mapped[User] = relationship(back_populates="grammar_notes")


def get_grammar_notes(session: Session, user_id: int, search: str = "") -> list[GrammarNote]:
    from sqlalchemy import func
    statement = select(GrammarNote).where(GrammarNote.user_id == user_id)
    if search:
        search_stripped = f"%{search.strip().lower()}%"
        statement = statement.where(
            (func.lower(GrammarNote.title).like(search_stripped)) |
            (func.lower(GrammarNote.content).like(search_stripped))
        )
    statement = statement.order_by(GrammarNote.created_at.desc(), GrammarNote.id.desc())
    return list(session.scalars(statement))


def create_grammar_note(session: Session, user_id: int, title: str, content: str) -> GrammarNote:
    note = GrammarNote(user_id=user_id, title=title.strip(), content=content)
    session.add(note)
    session.commit()
    return note


def update_grammar_note(session: Session, note_id: int, title: str, content: str) -> None:
    note = session.get(GrammarNote, note_id)
    if note:
        note.title = title.strip()
        note.content = content
        session.commit()


def delete_grammar_note(session: Session, note_id: int) -> None:
    note = session.get(GrammarNote, note_id)
    if note:
        session.delete(note)
        session.commit()

