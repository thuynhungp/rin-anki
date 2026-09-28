from __future__ import annotations

from datetime import datetime, timezone, date, timedelta
from typing import Any, Optional
from sqlalchemy import select, and_, func, or_
from sqlalchemy.orm import Session

from services.database import now_utc
from services.expense.models import (
    ExpenseAccount,
    ExpenseDebt,
    ExpenseSetting,
    ExpenseSubscription,
    ExpenseTransaction,
)

DEFAULT_ACCOUNTS = [
    {"name": "MSB", "account_type": "bank", "display_order": 1},
    {"name": "ACB", "account_type": "bank", "display_order": 2},
    {"name": "Momo", "account_type": "ewallet", "display_order": 3},
    {"name": "Tiền mặt", "account_type": "cash", "display_order": 4},
    {"name": "Shopee", "account_type": "ewallet", "display_order": 5},
    {"name": "Dự phòng", "account_type": "reserve", "display_order": 6},
    {"name": "Sổ tiết kiệm", "account_type": "savings", "display_order": 7},
    {"name": "Quỹ CK", "account_type": "stock", "display_order": 8},
]

EXPENSE_CATEGORIES = [
    "Ăn uống",
    "Mua sắm",
    "Thiết yếu",
    "Subscription",
    "Giải trí",
    "Y tế",
    "Ngoài lề",
    "Nợ",
    "Khác",
]

INCOME_CATEGORIES = [
    "Lương",
    "Thưởng",
    "Ba mẹ / Gia đình",
    "Bán CK / Lãi",
    "Thu nợ",
    "Khởi tạo",
    "Khác",
]


def ensure_default_accounts(session: Session, user_id: int) -> list[ExpenseAccount]:
    """Tạo các tài khoản mặc định và cài đặt cho user nếu chưa có."""
    # Ensure settings
    setting = session.scalar(select(ExpenseSetting).where(ExpenseSetting.user_id == user_id))
    if not setting:
        setting = ExpenseSetting(user_id=user_id, default_salary_day=6, use_salary_cycle=True)
        session.add(setting)
        session.commit()

    accounts = get_accounts(session, user_id)
    if accounts:
        return accounts

    for item in DEFAULT_ACCOUNTS:
        acc = ExpenseAccount(
            user_id=user_id,
            name=item["name"],
            account_type=item["account_type"],
            initial_balance=0.0,
            display_order=item["display_order"],
            is_active=True,
        )
        session.add(acc)
    session.commit()
    return get_accounts(session, user_id)


def get_user_setting(session: Session, user_id: int) -> ExpenseSetting:
    setting = session.scalar(select(ExpenseSetting).where(ExpenseSetting.user_id == user_id))
    if not setting:
        setting = ExpenseSetting(user_id=user_id, default_salary_day=6, use_salary_cycle=True)
        session.add(setting)
        session.commit()
    return setting


def update_user_setting(session: Session, user_id: int, default_salary_day: int, use_salary_cycle: bool) -> None:
    setting = get_user_setting(session, user_id)
    setting.default_salary_day = default_salary_day
    setting.use_salary_cycle = use_salary_cycle
    session.commit()


# --- Quản lý Kỳ lương (Salary Periods) ---

def get_salary_milestones(session: Session, user_id: int) -> list[tuple[datetime, str]]:
    """Lấy danh sách các giao dịch nhận Lương thực tế đã ghi nhận trong database.
    Mỗi mốc đánh dấu ngày bắt đầu của 1 kỳ lương thực tế.
    Trả về: [(tx_date, period_label), ...] sắp xếp tăng dần.
    """
    stmt = (
        select(ExpenseTransaction)
        .where(
            ExpenseTransaction.user_id == user_id,
            ExpenseTransaction.transaction_type == "income",
            or_(
                ExpenseTransaction.category == "Lương",
                func.lower(ExpenseTransaction.description).contains("lương")
            )
        )
        .order_by(ExpenseTransaction.transaction_date.asc())
    )
    txs = list(session.scalars(stmt).all())
    milestones = []
    for tx in txs:
        # Nhận lương vào tháng nào thì đó là kỳ lương của tháng đó (hoặc tháng nhận)
        period_label = f"Kỳ lương T{tx.transaction_date.month:02d}/{tx.transaction_date.year}"
        milestones.append((tx.transaction_date, period_label))
    return milestones


def determine_period_for_date(session: Session, user_id: int, dt: datetime) -> str:
    """Xác định kỳ chi tiêu cho một ngày giao dịch cụ thể theo quy tắc:
    - Tháng bắt đầu từ ngày nhận Lương.
    - Ví dụ: ngày 2/7 nhưng chưa nhận lương tháng 7 thì vẫn thuộc Kỳ lương tháng 6.
    - Dựa trên các mốc nhận lương thực tế (nếu có), hoặc ngày lương mặc định (default_salary_day).
    """
    setting = get_user_setting(session, user_id)
    if not setting.use_salary_cycle:
        return f"Tháng {dt.month:02d}/{dt.year}"

    milestones = get_salary_milestones(session, user_id)

    # Nếu đã có các mốc nhận lương thực tế được ghi nhận
    if milestones:
        # Nếu dt nằm sau hoặc bằng mốc lương cuối cùng
        last_date, last_label = milestones[-1]
        if dt >= last_date:
            return last_label

        # Nếu dt nằm giữa 2 mốc lương
        for i in range(len(milestones) - 1):
            curr_date, curr_label = milestones[i]
            next_date, _ = milestones[i + 1]
            if curr_date <= dt < next_date:
                return curr_label

        # Nếu dt nằm trước mốc lương đầu tiên ghi nhận: fallback theo default_salary_day

    # Tính theo ngày lương mặc định (default_salary_day, ví dụ ngày 6)
    sal_day = setting.default_salary_day
    if dt.day >= sal_day:
        return f"Kỳ lương T{dt.month:02d}/{dt.year}"
    else:
        # Lùi về tháng trước
        prev_month = dt.month - 1
        prev_year = dt.year
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1
        return f"Kỳ lương T{prev_month:02d}/{prev_year}"


def get_available_periods(session: Session, user_id: int) -> list[str]:
    """Lấy danh sách các kỳ chi tiêu có trong database để chọn trên dropdown."""
    stmt = (
        select(ExpenseTransaction.period_label)
        .where(
            ExpenseTransaction.user_id == user_id,
            ExpenseTransaction.period_label.is_not(None)
        )
        .distinct()
    )
    labels = [row for row in session.scalars(stmt).all() if row]
    
    # Đảm bảo kỳ hiện tại luôn có mặt trong danh sách
    current_period = determine_period_for_date(session, user_id, now_utc())
    if current_period not in labels:
        labels.append(current_period)

    # Sắp xếp các kỳ
    def sort_key(label: str) -> tuple[int, int]:
        # Trích xuất tháng và năm từ chuỗi "Kỳ lương TMM/YYYY" hoặc "Tháng MM/YYYY"
        try:
            parts = label.replace("Kỳ lương T", "").replace("Tháng ", "").split("/")
            return (int(parts[1]), int(parts[0]))
        except Exception:
            return (0, 0)

    labels.sort(key=sort_key, reverse=True)
    return labels


# --- Tài khoản & Số dư ---

def get_accounts(session: Session, user_id: int) -> list[ExpenseAccount]:
    statement = (
        select(ExpenseAccount)
        .where(ExpenseAccount.user_id == user_id, ExpenseAccount.is_active == True)
        .order_by(ExpenseAccount.display_order.asc(), ExpenseAccount.id.asc())
    )
    return list(session.scalars(statement).all())


def get_account_by_name(session: Session, user_id: int, name: str) -> Optional[ExpenseAccount]:
    statement = select(ExpenseAccount).where(
        ExpenseAccount.user_id == user_id,
        func.lower(ExpenseAccount.name) == func.lower(name.strip())
    )
    return session.scalars(statement).first()


def update_account_initial_balance(session: Session, account_id: int, initial_balance: float) -> None:
    acc = session.get(ExpenseAccount, account_id)
    if acc:
        acc.initial_balance = float(initial_balance)
        session.commit()


def update_account_verified_balance(session: Session, account_id: int, verified_balance: float) -> None:
    acc = session.get(ExpenseAccount, account_id)
    if acc:
        acc.verified_balance = float(verified_balance)
        acc.verified_at = now_utc()
        session.commit()


# --- Giao dịch ---

def create_transaction(
    session: Session,
    user_id: int,
    account_id: int,
    transaction_date: datetime,
    transaction_type: str,
    category: str,
    amount: float,
    description: str = "",
    balance_after: Optional[float] = None,
    source_image_name: Optional[str] = None,
    period_label: Optional[str] = None,
) -> ExpenseTransaction:
    if not period_label:
        period_label = determine_period_for_date(session, user_id, transaction_date)

    tx = ExpenseTransaction(
        user_id=user_id,
        account_id=account_id,
        transaction_date=transaction_date,
        transaction_type=transaction_type,
        category=category,
        amount=abs(float(amount)),
        description=description,
        balance_after=balance_after,
        source_image_name=source_image_name,
        period_label=period_label,
        created_at=now_utc(),
    )
    session.add(tx)
    session.commit()
    session.refresh(tx)
    return tx


def bulk_create_transactions(session: Session, items: list[dict[str, Any]]) -> int:
    created_count = 0
    for item in items:
        user_id = item["user_id"]
        tx_date = item["transaction_date"]
        period_label = item.get("period_label")
        if not period_label:
            period_label = determine_period_for_date(session, user_id, tx_date)

        tx = ExpenseTransaction(
            user_id=user_id,
            account_id=item["account_id"],
            transaction_date=tx_date,
            transaction_type=item["transaction_type"],
            category=item["category"],
            amount=abs(float(item["amount"])),
            description=item.get("description", ""),
            balance_after=item.get("balance_after"),
            source_image_name=item.get("source_image_name"),
            period_label=period_label,
            created_at=now_utc(),
        )
        session.add(tx)
        created_count += 1
    session.commit()
    return created_count


def delete_transaction(session: Session, transaction_id: int) -> bool:
    tx = session.get(ExpenseTransaction, transaction_id)
    if tx:
        session.delete(tx)
        session.commit()
        return True
    return False


def get_transactions(
    session: Session,
    user_id: int,
    period_label: Optional[str] = None,
    account_id: Optional[int] = None,
    transaction_type: Optional[str] = None,
) -> list[ExpenseTransaction]:
    statement = select(ExpenseTransaction).where(ExpenseTransaction.user_id == user_id)
    
    if period_label:
        statement = statement.where(ExpenseTransaction.period_label == period_label)

    if account_id is not None:
        statement = statement.where(ExpenseTransaction.account_id == account_id)
        
    if transaction_type is not None:
        statement = statement.where(ExpenseTransaction.transaction_type == transaction_type)

    statement = statement.order_by(
        ExpenseTransaction.transaction_date.desc(),
        ExpenseTransaction.id.desc()
    )
    return list(session.scalars(statement).all())


def calculate_account_balances(
    session: Session,
    user_id: int,
    period_label: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Tính toán số dư từng tài khoản:
    - Sổ sách (Book balance): initial_balance + income - expense
    - Thực tế (Verified balance)
    - Chênh lệch (Difference = Verified - Calculated)
    """
    accounts = get_accounts(session, user_id)
    transactions = get_transactions(session, user_id, period_label=period_label)
    
    acc_income: dict[int, float] = {acc.id: 0.0 for acc in accounts}
    acc_expense: dict[int, float] = {acc.id: 0.0 for acc in accounts}
    
    for tx in transactions:
        if tx.account_id in acc_income:
            if tx.transaction_type == "income":
                acc_income[tx.account_id] += tx.amount
            elif tx.transaction_type == "expense":
                acc_expense[tx.account_id] += tx.amount

    result = []
    for acc in accounts:
        inc = acc_income.get(acc.id, 0.0)
        exp = acc_expense.get(acc.id, 0.0)
        calc_bal = acc.initial_balance + inc - exp
        ver_bal = acc.verified_balance
        diff = (ver_bal - calc_bal) if ver_bal is not None else None
        
        result.append({
            "account_id": acc.id,
            "name": acc.name,
            "account_type": acc.account_type,
            "initial_balance": acc.initial_balance,
            "total_income": inc,
            "total_expense": exp,
            "calculated_balance": calc_bal,
            "verified_balance": ver_bal,
            "difference": diff,
            "verified_at": acc.verified_at,
        })
    return result


def calculate_period_summary(
    session: Session,
    user_id: int,
    period_label: str,
) -> dict[str, Any]:
    txs = get_transactions(session, user_id, period_label=period_label)
    total_income = sum(tx.amount for tx in txs if tx.transaction_type == "income")
    total_expense = sum(tx.amount for tx in txs if tx.transaction_type == "expense")
    net_savings = total_income - total_expense

    account_balances = calculate_account_balances(session, user_id, period_label=period_label)
    
    # Khả dụng = Các ví thanh toán linh hoạt
    available_types = {"bank", "ewallet", "cash"}
    available_balance = sum(
        item["calculated_balance"] for item in account_balances
        if item["account_type"] in available_types
    )

    total_net_worth = sum(item["calculated_balance"] for item in account_balances)

    return {
        "period_label": period_label,
        "total_income": total_income,
        "total_expense": total_expense,
        "net_savings": net_savings,
        "available_balance": available_balance,
        "total_net_worth": total_net_worth,
        "account_balances": account_balances,
        "transaction_count": len(txs),
    }


# --- Subscriptions ---
def get_subscriptions(session: Session, user_id: int) -> list[ExpenseSubscription]:
    stmt = (
        select(ExpenseSubscription)
        .where(ExpenseSubscription.user_id == user_id)
        .order_by(ExpenseSubscription.billing_day.asc())
    )
    return list(session.scalars(stmt).all())


def create_subscription(
    session: Session,
    user_id: int,
    name: str,
    amount: float,
    billing_day: int,
    account_name: str = "MSB",
) -> ExpenseSubscription:
    sub = ExpenseSubscription(
        user_id=user_id,
        name=name.strip(),
        amount=float(amount),
        billing_day=int(billing_day),
        account_name=account_name,
        is_active=True,
    )
    session.add(sub)
    session.commit()
    session.refresh(sub)
    return sub


def delete_subscription(session: Session, sub_id: int) -> bool:
    sub = session.get(ExpenseSubscription, sub_id)
    if sub:
        session.delete(sub)
        session.commit()
        return True
    return False


# --- Debts ---
def get_debts(session: Session, user_id: int) -> list[ExpenseDebt]:
    stmt = select(ExpenseDebt).where(ExpenseDebt.user_id == user_id).order_by(ExpenseDebt.is_settled.asc(), ExpenseDebt.created_at.desc())
    return list(session.scalars(stmt).all())


def create_debt(
    session: Session,
    user_id: int,
    person_name: str,
    debt_type: str,
    amount: float,
    note: str = "",
) -> ExpenseDebt:
    debt = ExpenseDebt(
        user_id=user_id,
        person_name=person_name.strip(),
        debt_type=debt_type,
        amount=float(amount),
        note=note,
        is_settled=False,
        created_at=now_utc(),
    )
    session.add(debt)
    session.commit()
    session.refresh(debt)
    return debt


def settle_debt(session: Session, debt_id: int) -> bool:
    debt = session.get(ExpenseDebt, debt_id)
    if debt:
        debt.is_settled = True
        debt.settled_at = now_utc()
        session.commit()
        return True
    return False


def delete_debt(session: Session, debt_id: int) -> bool:
    debt = session.get(ExpenseDebt, debt_id)
    if debt:
        session.delete(debt)
        session.commit()
        return True
    return False
