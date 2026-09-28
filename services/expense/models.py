from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from services.database import Base, now_utc


class ExpenseAccount(Base):
    __tablename__ = "expense_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    account_type: Mapped[str] = mapped_column(String(20), default="bank")  # bank, ewallet, cash, savings, stock, reserve
    initial_balance: Mapped[float] = mapped_column(Float, default=0.0)
    verified_balance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    transactions: Mapped[list["ExpenseTransaction"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


class ExpenseTransaction(Base):
    __tablename__ = "expense_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("expense_accounts.id"), nullable=False)
    transaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(20), default="expense")  # expense, income, transfer
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="Ăn uống")
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    balance_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source_image_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    period_label: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # ví dụ: "Kỳ T06/2026"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: now_utc())

    account: Mapped[ExpenseAccount] = relationship(back_populates="transactions")


class ExpenseSubscription(Base):
    __tablename__ = "expense_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    billing_day: Mapped[int] = mapped_column(Integer, default=1)
    account_name: Mapped[str] = mapped_column(String(50), default="MSB")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ExpenseDebt(Base):
    __tablename__ = "expense_debts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    person_name: Mapped[str] = mapped_column(String(100), nullable=False)
    debt_type: Mapped[str] = mapped_column(String(20), default="lend")  # lend: mình cho mượn, borrow: mình nợ
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="")
    is_settled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: now_utc())
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ExpenseSetting(Base):
    __tablename__ = "expense_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    default_salary_day: Mapped[int] = mapped_column(Integer, default=6)
    use_salary_cycle: Mapped[bool] = mapped_column(Boolean, default=True)
