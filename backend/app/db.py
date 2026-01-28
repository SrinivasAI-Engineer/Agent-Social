from __future__ import annotations

import json
import hashlib
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.config import settings
from app.security import decrypt_str, encrypt_str


class Base(DeclarativeBase):
    pass


class Execution(Base):
    __tablename__ = "executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="running")  # running|awaiting_human|awaiting_auth|completed|terminated
    state_json: Mapped[str] = mapped_column(Text, default="{}")
    idempotency_key: Mapped[str] = mapped_column(String(128), default="")  # url-hash etc.

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TokenStore(Base):
    __tablename__ = "tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)  # twitter|linkedin

    encrypted_json: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OAuthState(Base):
    __tablename__ = "oauth_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    state: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)  # twitter|linkedin
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    code_verifier: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


engine = create_engine(settings.database_url, future=True)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)


def save_execution_state(execution_id: str, state: dict[str, Any], status: Optional[str] = None) -> None:
    with get_session() as s:
        ex = s.scalar(select(Execution).where(Execution.execution_id == execution_id))
        if ex is None:
            raise RuntimeError(f"Execution not found: {execution_id}")
        ex.state_json = json.dumps(state, ensure_ascii=False)
        if status:
            ex.status = status
        s.add(ex)
        s.commit()


def create_execution(execution_id: str, user_id: str, url: str, initial_state: dict[str, Any], idempotency_key: str) -> None:
    with get_session() as s:
        ex = Execution(execution_id=execution_id, user_id=user_id, url=url, state_json=json.dumps(initial_state), idempotency_key=idempotency_key)
        s.add(ex)
        s.commit()


def get_execution(execution_id: str) -> Execution:
    with get_session() as s:
        ex = s.scalar(select(Execution).where(Execution.execution_id == execution_id))
        if ex is None:
            raise RuntimeError(f"Execution not found: {execution_id}")
        return ex


def list_inbox(statuses: list[str]) -> list[Execution]:
    with get_session() as s:
        stmt = select(Execution).where(Execution.status.in_(statuses)).order_by(Execution.updated_at.desc())
        return list(s.scalars(stmt).all())


def compute_idempotency_key(user_id: str, url: str) -> str:
    h = hashlib.sha256()
    h.update((user_id + "\n" + url).encode("utf-8"))
    return h.hexdigest()[:32]


def find_execution_by_idempotency(user_id: str, idempotency_key: str) -> Optional[Execution]:
    with get_session() as s:
        stmt = select(Execution).where(Execution.user_id == user_id, Execution.idempotency_key == idempotency_key)
        return s.scalar(stmt)


def upsert_tokens(user_id: str, provider: str, token_payload: dict[str, Any], expires_at: Optional[datetime]) -> None:
    plaintext = json.dumps(token_payload, ensure_ascii=False)
    encrypted = encrypt_str(plaintext)
    with get_session() as s:
        row = s.scalar(select(TokenStore).where(TokenStore.user_id == user_id, TokenStore.provider == provider))
        if row is None:
            row = TokenStore(user_id=user_id, provider=provider)
        row.encrypted_json = encrypted
        row.expires_at = expires_at
        s.add(row)
        s.commit()


def get_tokens(user_id: str, provider: str) -> Optional[dict[str, Any]]:
    with get_session() as s:
        row = s.scalar(select(TokenStore).where(TokenStore.user_id == user_id, TokenStore.provider == provider))
        if row is None or not row.encrypted_json:
            return None
        plaintext = decrypt_str(row.encrypted_json)
        return json.loads(plaintext)


def get_tokens_expiry(user_id: str, provider: str) -> Optional[datetime]:
    with get_session() as s:
        row = s.scalar(select(TokenStore).where(TokenStore.user_id == user_id, TokenStore.provider == provider))
        return None if row is None else row.expires_at


def store_oauth_state(state: str, provider: str, user_id: str, code_verifier: str) -> None:
    with get_session() as s:
        row = OAuthState(state=state, provider=provider, user_id=user_id, code_verifier=code_verifier)
        s.add(row)
        s.commit()


def pop_oauth_state(state: str, provider: str) -> Optional[dict[str, str]]:
    with get_session() as s:
        row = s.scalar(select(OAuthState).where(OAuthState.state == state, OAuthState.provider == provider))
        if row is None:
            return None
        data = {"state": row.state, "provider": row.provider, "user_id": row.user_id, "code_verifier": row.code_verifier}
        s.delete(row)
        s.commit()
        return data

