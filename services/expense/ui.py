from __future__ import annotations

import base64
import io
from datetime import datetime, date, time
from typing import Any, Optional

import pandas as pd
import streamlit as st
from PIL import Image

from services.database import SessionLocal, now_utc
from services.expense.extractor import GeminiExpenseExtractor
from services.expense.service import (
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES,
    bulk_create_transactions,
    calculate_account_balances,
    calculate_period_summary,
    create_debt,
    create_subscription,
    create_transaction,
    delete_debt,
    delete_subscription,
    delete_transaction,
    determine_period_for_date,
    ensure_default_accounts,
    get_accounts,
    get_available_periods,
    get_debts,
    get_subscriptions,
    get_transactions,
    get_user_setting,
    settle_debt,
    update_account_initial_balance,
    update_account_verified_balance,
    update_user_setting,
)


def format_vnd(amount: float | int | None) -> str:
    if amount is None:
        return "-"
    return f"{amount:,.0f} đ".replace(",", ".")


def expense_screen(user_id: int) -> None:
    with SessionLocal() as session:
        accounts = ensure_default_accounts(session, user_id)
        account_names = [acc.name for acc in accounts]
        setting = get_user_setting(session, user_id)
        periods = get_available_periods(session, user_id)

    # Header & Period Selection
    header_col1, header_col2, header_col3 = st.columns([3, 2, 2])
    with header_col1:
        st.subheader("💰 Quản lý chi tiêu của Rin")

    with header_col2:
        selected_period = st.selectbox(
            "Kỳ chi tiêu",
            periods,
            index=0 if periods else None,
            help="Kỳ chi tiêu bắt đầu từ ngày nhận lương. Các ngày đầu tháng trước ngày nhận lương vẫn thuộc kỳ trước.",
            key="expense_selected_period",
        )

    with header_col3:
        st.write("") # spacing
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            with st.popover("➕ Nhận Lương"):
                st.markdown("**Ghi nhận Lương để mở kỳ mới**")
                salary_date = st.date_input("Ngày nhận lương", value=date.today(), key="salary_date_input")
                salary_amount = st.number_input("Số tiền lương", min_value=0.0, step=500000.0, value=17800000.0, format="%.0f")
                salary_acc = st.selectbox("Tài khoản nhận", account_names, index=0 if "MSB" in account_names else 0)
                salary_desc = st.text_input("Ghi chú", value="Lương công ty")
                if st.button("Xác nhận nhận lương", type="primary", use_container_width=True):
                    with SessionLocal() as session:
                        target_acc = next((a for a in accounts if a.name == salary_acc), None)
                        if target_acc:
                            dt = datetime.combine(salary_date, datetime.min.time())
                            period_lbl = f"Kỳ lương T{dt.month:02d}/{dt.year}"
                            create_transaction(
                                session=session,
                                user_id=user_id,
                                account_id=target_acc.id,
                                transaction_date=dt,
                                transaction_type="income",
                                category="Lương",
                                amount=salary_amount,
                                description=salary_desc,
                                period_label=period_lbl,
                            )
                            st.success(f"Đã ghi nhận lương và kích hoạt {period_lbl}!")
                            st.rerun()

        with col_btn2:
            with st.popover("⚙️ Cài đặt"):
                st.markdown("**Cấu hình chu kỳ chi tiêu**")
                def_day = st.number_input("Ngày nhận lương dự kiến", min_value=1, max_value=31, value=setting.default_salary_day)
                use_sal = st.checkbox("Tính tháng theo ngày nhận Lương", value=setting.use_salary_cycle)
                if st.button("Lưu cài đặt", use_container_width=True):
                    with SessionLocal() as session:
                        update_user_setting(session, user_id, int(def_day), bool(use_sal))
                        st.success("Đã cập nhật cài đặt!")
                        st.rerun()

    # Metric Cards
    if selected_period:
        with SessionLocal() as session:
            summary = calculate_period_summary(session, user_id, selected_period)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🟢 Tổng thu nhập", format_vnd(summary["total_income"]))
        m2.metric("🔴 Tổng chi tiêu", format_vnd(summary["total_expense"]))
        m3.metric("🔵 Số dư ròng (Thu - Chi)", format_vnd(summary["net_savings"]))
        m4.metric("🟡 Khả dụng (Bank/Ví/TM)", format_vnd(summary["available_balance"]))

    st.markdown("---")

    # Tabs
    tab_ai, tab_report, tab_cash, tab_subs = st.tabs([
        "⚡ Quét Bank bằng AI",
        "📊 Báo cáo & Đối chiếu số dư",
        "💵 Chi tiêu thủ công & Tiền mặt",
        "📌 Gói tháng & Sổ nợ",
    ])

    # -------------------------------------------------------------
    # TAB 1: Quét Bank bằng AI
    # -------------------------------------------------------------
    with tab_ai:
        st.markdown(
            "Tải lên hoặc dán (`Ctrl+V`) một hoặc nhiều ảnh chụp lịch sử giao dịch app ngân hàng (**MSB, ACB, Momo...**). "
            "Gemini AI sẽ tự động bóc tách số tiền, ngày giờ, nội dung, tự phân loại danh mục và phát hiện số dư sau giao dịch."
        )

        uploaded_files = st.file_uploader(
            "Chọn ảnh chụp màn hình (có thể chọn nhiều ảnh)",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            key="bank_screenshot_uploader",
        )

        col_act1, col_act2 = st.columns([2, 5])
        with col_act1:
            scan_btn = st.button("🤖 Phân tích giao dịch bằng AI", type="primary", use_container_width=True)

        if scan_btn:
            if not uploaded_files:
                st.warning("Vui lòng tải lên ít nhất một ảnh chụp lịch sử giao dịch.")
            else:
                with st.spinner("Gemini AI đang phân tích và bóc tách các giao dịch..."):
                    try:
                        images = [Image.open(f) for f in uploaded_files]
                        extractor = GeminiExpenseExtractor()
                        extracted_items = extractor.extract_from_images(images)

                        if not extracted_items:
                            st.warning("Không tìm thấy giao dịch nào trong ảnh. Vui lòng kiểm tra lại ảnh chụp rõ ràng hơn.")
                        else:
                            # Chuẩn hóa dữ liệu thành DataFrame để preview trên st.data_editor
                            preview_rows = []
                            for idx, item in enumerate(extracted_items):
                                preview_rows.append({
                                    "Chọn": True,
                                    "Ngày (YYYY-MM-DD)": str(item.get("date", date.today().isoformat())),
                                    "Nguồn": item.get("bank_name", "MSB"),
                                    "Loại": item.get("type", "expense"),
                                    "Danh mục": item.get("category", "Ăn uống"),
                                    "Số tiền": float(item.get("amount", 0.0)),
                                    "Mô tả": str(item.get("description", "")),
                                    "Số dư sau GD": float(item.get("balance_after")) if item.get("balance_after") is not None else None,
                                })
                            st.session_state["ai_extracted_preview"] = pd.DataFrame(preview_rows)
                            st.success(f"Đã phát hiện thành công {len(preview_rows)} giao dịch!")
                    except Exception as exc:
                        st.error(f"Lỗi khi quét ảnh: {exc}")

        # Hiển thị bảng xem trước và cho phép chỉnh sửa trước khi lưu
        if "ai_extracted_preview" in st.session_state and not st.session_state["ai_extracted_preview"].empty:
            st.markdown("#### 📋 Kiểm tra & Chỉnh sửa trước khi lưu")
            st.caption("Bạn có thể sửa trực tiếp số tiền, danh mục, nguồn hoặc bỏ chọn những giao dịch không muốn lưu.")

            edited_df = st.data_editor(
                st.session_state["ai_extracted_preview"],
                column_config={
                    "Chọn": st.column_config.CheckboxColumn("Lưu", default=True),
                    "Ngày (YYYY-MM-DD)": st.column_config.TextColumn("Ngày"),
                    "Nguồn": st.column_config.SelectboxColumn("Nguồn", options=account_names, required=True),
                    "Loại": st.column_config.SelectboxColumn("Loại", options=["expense", "income"]),
                    "Danh mục": st.column_config.SelectboxColumn("Danh mục", options=EXPENSE_CATEGORIES + INCOME_CATEGORIES, required=True),
                    "Số tiền": st.column_config.NumberColumn("Số tiền (VNĐ)", format="%.0f"),
                    "Mô tả": st.column_config.TextColumn("Mô tả"),
                    "Số dư sau GD": st.column_config.NumberColumn("Số dư sau GD (nếu có)", format="%.0f"),
                },
                use_container_width=True,
                num_rows="dynamic",
                key="editor_ai_transactions",
            )

            col_save1, col_save2 = st.columns([2, 5])
            with col_save1:
                if st.button("💾 Xác nhận & Lưu vào sổ", type="primary", use_container_width=True):
                    with SessionLocal() as session:
                        to_save = []
                        last_balances = {} # account_id -> verified_balance
                        
                        for _, row in edited_df.iterrows():
                            if not row["Chọn"]:
                                continue
                            
                            # Tìm account_id tương ứng
                            src_name = str(row["Nguồn"]).strip()
                            acc = next((a for a in accounts if a.name.lower() == src_name.lower()), None)
                            if not acc:
                                # Fallback sang tài khoản đầu tiên
                                acc = accounts[0]

                            try:
                                tx_date = datetime.strptime(str(row["Ngày (YYYY-MM-DD)"]), "%Y-%m-%d")
                            except Exception:
                                tx_date = datetime.now()

                            amt = float(row["Số tiền"])
                            bal_after = float(row["Số dư sau GD"]) if pd.notna(row["Số dư sau GD"]) else None

                            to_save.append({
                                "user_id": user_id,
                                "account_id": acc.id,
                                "transaction_date": tx_date,
                                "transaction_type": str(row["Loại"]),
                                "category": str(row["Danh mục"]),
                                "amount": amt,
                                "description": str(row["Mô tả"]),
                                "balance_after": bal_after,
                                "source_image_name": "AI_Bank_Scan",
                            })

                            if bal_after is not None:
                                last_balances[acc.id] = bal_after

                        count = bulk_create_transactions(session, to_save)

                        # Cập nhật số dư thực tế đối chiếu nếu có
                        for acc_id, v_bal in last_balances.items():
                            update_account_verified_balance(session, acc_id, v_bal)

                        st.session_state.pop("ai_extracted_preview", None)
                        st.success(f"Đã lưu thành công {count} giao dịch vào sổ chi tiêu!")
                        st.rerun()

    # -------------------------------------------------------------
    # TAB 2: Báo cáo & Đối chiếu số dư
    # -------------------------------------------------------------
    with tab_report:
        st.markdown(f"### ⚖️ Bảng đối chiếu số dư ({selected_period})")
        st.caption(
            "So sánh **Số dư sổ sách** (Số dư ban đầu + Thu - Chi) với **Số dư thực tế** (cập nhật từ app bank). "
            "Nếu chênh lệch bằng 0 đ là hoàn toàn khớp!"
        )

        with SessionLocal() as session:
            balances = calculate_account_balances(session, user_id, period_label=selected_period)
            
            recon_data = []
            for item in balances:
                diff = item["difference"]
                if diff is None:
                    status = "⚪ Chưa đối chiếu"
                elif abs(diff) < 1.0:
                    status = "🟢 Khớp hoàn toàn"
                elif diff > 0:
                    status = f"🔴 Thừa {format_vnd(diff)}"
                else:
                    status = f"🔴 Thiếu {format_vnd(abs(diff))}"

                recon_data.append({
                    "account_id": item["account_id"],
                    "Tài khoản": item["name"],
                    "Số dư ban đầu": item["initial_balance"],
                    "Tổng thu": item["total_income"],
                    "Tổng chi": item["total_expense"],
                    "Số dư sổ sách": item["calculated_balance"],
                    "Số dư thực tế": item["verified_balance"],
                    "Chênh lệch": diff if diff is not None else 0.0,
                    "Trạng thái": status,
                })

            recon_df = pd.DataFrame(recon_data)

            # Cấu hình bảng hiển thị
            st.dataframe(
                recon_df[[
                    "Tài khoản", "Số dư ban đầu", "Tổng thu", "Tổng chi",
                    "Số dư sổ sách", "Số dư thực tế", "Chênh lệch", "Trạng thái"
                ]],
                column_config={
                    "Số dư ban đầu": st.column_config.NumberColumn(format="%.0f đ"),
                    "Tổng thu": st.column_config.NumberColumn(format="%.0f đ"),
                    "Tổng chi": st.column_config.NumberColumn(format="%.0f đ"),
                    "Số dư sổ sách": st.column_config.NumberColumn(format="%.0f đ"),
                    "Số dư thực tế": st.column_config.NumberColumn(format="%.0f đ"),
                    "Chênh lệch": st.column_config.NumberColumn(format="%.0f đ"),
                },
                use_container_width=True,
                hide_index=True,
            )

            # Form cập nhật nhanh số dư
            with st.expander("📝 Cập nhật số dư ban đầu hoặc số dư thực tế các tài khoản"):
                col_acc1, col_acc2, col_acc3, col_acc4 = st.columns([2, 2, 2, 1])
                with col_acc1:
                    acc_to_edit = st.selectbox("Chọn tài khoản", account_names, key="edit_acc_select")
                with col_acc2:
                    acc_obj = next((a for a in accounts if a.name == acc_to_edit), None)
                    new_init_bal = st.number_input("Số dư ban đầu (đ)", value=float(acc_obj.initial_balance if acc_obj else 0.0), format="%.0f", step=100000.0)
                with col_acc3:
                    new_ver_bal = st.number_input("Số dư thực tế bank (đ)", value=float(acc_obj.verified_balance if acc_obj and acc_obj.verified_balance is not None else 0.0), format="%.0f", step=100000.0)
                with col_acc4:
                    st.write("")
                    st.write("")
                    if st.button("Lưu số dư", use_container_width=True):
                        if acc_obj:
                            update_account_initial_balance(session, acc_obj.id, new_init_bal)
                            update_account_verified_balance(session, acc_obj.id, new_ver_bal)
                            st.success(f"Đã cập nhật số dư cho {acc_to_edit}!")
                            st.rerun()

            st.markdown("---")

            # Biểu đồ chi tiêu
            st.markdown(f"### 📈 Phân tích chi tiêu ({selected_period})")
            txs = get_transactions(session, user_id, period_label=selected_period)
            exp_txs = [t for t in txs if t.transaction_type == "expense"]

            if exp_txs:
                chart_col1, chart_col2 = st.columns(2)
                with chart_col1:
                    st.markdown("**Chi tiêu theo Danh mục**")
                    cat_summary = {}
                    for t in exp_txs:
                        cat_summary[t.category] = cat_summary.get(t.category, 0.0) + t.amount
                    cat_df = pd.DataFrame(list(cat_summary.items()), columns=["Danh mục", "Số tiền"]).sort_values("Số tiền", ascending=False)
                    st.bar_chart(cat_df.set_index("Danh mục"))

                with chart_col2:
                    st.markdown("**Chi tiêu theo Nguồn tiền**")
                    acc_map = {a.id: a.name for a in accounts}
                    src_summary = {}
                    for t in exp_txs:
                        src_name = acc_map.get(t.account_id, "Khác")
                        src_summary[src_name] = src_summary.get(src_name, 0.0) + t.amount
                    src_df = pd.DataFrame(list(src_summary.items()), columns=["Nguồn", "Số tiền"]).sort_values("Số tiền", ascending=False)
                    st.bar_chart(src_df.set_index("Nguồn"))
            else:
                st.info("Chưa có giao dịch chi tiêu nào trong kỳ này để hiển thị biểu đồ.")

            # Bảng danh sách chi tiết các giao dịch
            st.markdown("### 📜 Nhật ký giao dịch chi tiết")
            if txs:
                tx_rows = []
                acc_map = {a.id: a.name for a in accounts}
                for t in txs:
                    tx_rows.append({
                        "id": t.id,
                        "Ngày": t.transaction_date.strftime("%d/%m/%Y"),
                        "Nguồn": acc_map.get(t.account_id, "-"),
                        "Loại": "Chi tiêu" if t.transaction_type == "expense" else "Thu nhập",
                        "Danh mục": t.category,
                        "Số tiền": t.amount,
                        "Mô tả": t.description,
                    })
                tx_df = pd.DataFrame(tx_rows)
                
                # Bộ lọc
                f_col1, f_col2, f_col3 = st.columns([2, 2, 3])
                with f_col1:
                    filter_cat = st.selectbox("Lọc danh mục", ["Tất cả"] + list(tx_df["Danh mục"].unique()))
                with f_col2:
                    filter_src = st.selectbox("Lọc nguồn", ["Tất cả"] + list(tx_df["Nguồn"].unique()))
                with f_col3:
                    search_kw = st.text_input("Tìm kiếm mô tả", placeholder="Nhập từ khóa...")

                filtered_df = tx_df.copy()
                if filter_cat != "Tất cả":
                    filtered_df = filtered_df[filtered_df["Danh mục"] == filter_cat]
                if filter_src != "Tất cả":
                    filtered_df = filtered_df[filtered_df["Nguồn"] == filter_src]
                if search_kw:
                    filtered_df = filtered_df[filtered_df["Mô tả"].str.contains(search_kw, case=False, na=False)]

                st.dataframe(
                    filtered_df[["Ngày", "Nguồn", "Loại", "Danh mục", "Số tiền", "Mô tả"]],
                    column_config={
                        "Số tiền": st.column_config.NumberColumn(format="%.0f đ"),
                    },
                    use_container_width=True,
                    hide_index=True,
                )

                # Nút xóa giao dịch nếu cần
                with st.expander("🗑️ Xóa giao dịch"):
                    tx_id_to_del = st.selectbox("Chọn giao dịch muốn xóa", filtered_df["id"].tolist(), format_func=lambda x: f"ID {x}: {filtered_df[filtered_df['id']==x]['Mô tả'].values[0]} ({format_vnd(filtered_df[filtered_df['id']==x]['Số tiền'].values[0])})")
                    if st.button("Xác nhận xóa", type="secondary"):
                        delete_transaction(session, tx_id_to_del)
                        st.success("Đã xóa giao dịch!")
                        st.rerun()
            else:
                st.info("Chưa có giao dịch nào được ghi nhận trong kỳ này.")

    # -------------------------------------------------------------
    # TAB 3: Chi tiêu thủ công & Tiền mặt
    # -------------------------------------------------------------
    with tab_cash:
        st.markdown("### 💵 Ghi nhanh chi tiêu tiền mặt hoặc giao dịch thủ công")
        col_c1, col_c2 = st.columns(2)

        with col_c1:
            st.markdown("#### ➕ Thêm giao dịch")
            with st.form("manual_tx_form"):
                m_date = st.date_input("Ngày giao dịch", value=date.today())
                m_type = st.radio("Loại giao dịch", ["expense", "income"], format_func=lambda x: "Chi tiêu" if x == "expense" else "Thu nhập", horizontal=True)
                m_src = st.selectbox("Nguồn tiền", account_names, index=account_names.index("Tiền mặt") if "Tiền mặt" in account_names else 0)
                
                cats = EXPENSE_CATEGORIES if m_type == "expense" else INCOME_CATEGORIES
                m_cat = st.selectbox("Danh mục", cats)
                m_amount = st.number_input("Số tiền (VNĐ)", min_value=0.0, step=10000.0, format="%.0f")
                m_desc = st.text_input("Mô tả", placeholder="Ví dụ: Gửi xe, Omachi, Xăng...")

                if st.form_submit_button("Lưu giao dịch", type="primary", use_container_width=True):
                    if m_amount <= 0:
                        st.warning("Vui lòng nhập số tiền lớn hơn 0.")
                    else:
                        with SessionLocal() as session:
                            target_acc = next((a for a in accounts if a.name == m_src), accounts[0])
                            dt = datetime.combine(m_date, datetime.min.time())
                            create_transaction(
                                session=session,
                                user_id=user_id,
                                account_id=target_acc.id,
                                transaction_date=dt,
                                transaction_type=m_type,
                                category=m_cat,
                                amount=m_amount,
                                description=m_desc,
                            )
                            st.success("Đã lưu giao dịch thành công!")
                            st.rerun()

        with col_c2:
            st.markdown("#### 🪙 Kiểm đếm ví tiền mặt")
            st.caption("Đếm số tiền mặt thực tế trong ví của bạn hôm nay để so sánh với số dư trên sổ.")
            
            with SessionLocal() as session:
                cash_acc = next((a for a in accounts if a.name == "Tiền mặt"), None)
                if cash_acc:
                    balances = calculate_account_balances(session, user_id, period_label=selected_period)
                    cash_item = next((b for b in balances if b["account_id"] == cash_acc.id), None)
                    book_cash = cash_item["calculated_balance"] if cash_item else 0.0

                    st.info(f"Số dư tiền mặt trên sổ: **{format_vnd(book_cash)}**")

                    real_cash = st.number_input("Số tiền mặt thực tế trong ví", min_value=0.0, step=10000.0, value=float(cash_acc.verified_balance or book_cash), format="%.0f")
                    diff_cash = real_cash - book_cash
                    
                    if diff_cash == 0:
                        st.success("🟢 Số tiền mặt trong ví khớp hoàn toàn với sổ sách!")
                    elif diff_cash > 0:
                        st.warning(f"🟡 Thừa tiền mặt: +{format_vnd(diff_cash)} (có thể có tiền lẻ chưa ghi nhận)")
                    else:
                        st.error(f"🔴 Thiếu tiền mặt: -{format_vnd(abs(diff_cash))} (có thể có khoản chi lẻ chưa ghi)")

                    if st.button("Lưu số dư tiền mặt thực tế", use_container_width=True):
                        update_account_verified_balance(session, cash_acc.id, real_cash)
                        st.success("Đã cập nhật số dư tiền mặt thực tế!")
                        st.rerun()

    # -------------------------------------------------------------
    # TAB 4: Gói tháng & Sổ nợ
    # -------------------------------------------------------------
    with tab_subs:
        col_s1, col_s2 = st.columns(2)

        with col_s1:
            st.markdown("### 🔄 Gói tháng / Subscription")
            st.caption("Các dịch vụ cố định hàng tháng (iCloud, Spotify, Claude, ACB SMS...)")

            with SessionLocal() as session:
                subs = get_subscriptions(session, user_id)
                if subs:
                    for sub in subs:
                        sub_col1, sub_col2, sub_col3 = st.columns([3, 2, 1])
                        with sub_col1:
                            st.write(f"**{sub.name}**")
                            st.caption(f"Trừ qua {sub.account_name} • Ngày {sub.billing_day} hàng tháng")
                        with sub_col2:
                            st.write(f"**{format_vnd(sub.amount)}**")
                        with sub_col3:
                            if st.button("Xóa", key=f"del_sub_{sub.id}"):
                                delete_subscription(session, sub.id)
                                st.rerun()
                        st.markdown("---")
                else:
                    st.info("Chưa có gói tháng nào. Thêm gói mới bên dưới:")

                with st.expander("➕ Thêm gói tháng mới"):
                    with st.form("new_sub_form"):
                        sub_name = st.text_input("Tên gói (ví dụ: iCloud, Spotify...)")
                        sub_amt = st.number_input("Giá gói (VNĐ)", min_value=0.0, step=10000.0, format="%.0f")
                        sub_day = st.number_input("Ngày thanh toán trong tháng", min_value=1, max_value=31, value=5)
                        sub_acc = st.selectbox("Tài khoản thanh toán", account_names)
                        if st.form_submit_button("Thêm gói", type="primary"):
                            if sub_name and sub_amt > 0:
                                create_subscription(session, user_id, sub_name, sub_amt, int(sub_day), sub_acc)
                                st.success("Đã thêm gói tháng thành công!")
                                st.rerun()

        with col_s2:
            st.markdown("### 🤝 Sổ nợ & Khoản mượn")
            st.caption("Theo dõi ai nợ Rin hoặc Rin nợ ai.")

            with SessionLocal() as session:
                debts = get_debts(session, user_id)
                unsettled = [d for d in debts if not d.is_settled]
                settled = [d for d in debts if d.is_settled]

                if unsettled:
                    for d in unsettled:
                        d_col1, d_col2, d_col3 = st.columns([3, 2, 2])
                        with d_col1:
                            label = "Mượn Rin" if d.debt_type == "lend" else "Rin nợ"
                            st.write(f"**{d.person_name}** ({label})")
                            if d.note:
                                st.caption(d.note)
                        with d_col2:
                            st.write(f"**{format_vnd(d.amount)}**")
                        with d_col3:
                            if st.button("Đã trả xong", key=f"settle_debt_{d.id}", type="secondary"):
                                settle_debt(session, d.id)
                                st.rerun()
                        st.markdown("---")
                else:
                    st.info("Hiện không có khoản nợ nào chưa giải quyết.")

                with st.expander("➕ Thêm khoản nợ mới"):
                    with st.form("new_debt_form"):
                        d_name = st.text_input("Tên người (Châu, Nguyên...)")
                        d_type = st.radio("Loại", ["lend", "borrow"], format_func=lambda x: "Họ nợ Rin (Rin cho mượn)" if x == "lend" else "Rin nợ họ")
                        d_amt = st.number_input("Số tiền", min_value=0.0, step=50000.0, format="%.0f")
                        d_note = st.text_input("Ghi chú", placeholder="Lý do mượn / hạn trả...")
                        if st.form_submit_button("Thêm khoản nợ", type="primary"):
                            if d_name and d_amt > 0:
                                create_debt(session, user_id, d_name, d_type, d_amt, d_note)
                                st.success("Đã thêm khoản nợ thành công!")
                                st.rerun()
