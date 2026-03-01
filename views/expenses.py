"""
支出記錄頁面 - v2.2
✅ [FIX v2.2] add_expense 補入 user_id（修正 NOT NULL 報錯）
✅ [FIX v2.2] width="stretch" → use_container_width=True（共 5 處）
✅ v2.1 所有功能保留
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime
import logging

from services.expense_service import ExpenseService

try:
    from components.cards import section_header, metric_card, empty_state, data_table, info_card
except ImportError:
    def section_header(title, icon="", divider=True):
        st.markdown(f"### {icon} {title}")
        if divider:
            st.divider()

    def metric_card(label, value, delta="", icon="", color="normal"):
        st.metric(label, value, delta)

    def empty_state(msg, icon="", desc=""):
        st.info(f"{icon} {msg}")
        if desc:
            st.caption(desc)

    def data_table(df, key="table"):
        st.dataframe(df, use_container_width=True, key=key)

    def info_card(title, content, icon="", type="info"):
        st.info(f"{icon} {title}\n\n{content}")

try:
    from config.constants import EXPENSE
except ImportError:
    class EXPENSE:
        CATEGORIES = ["維修", "水電", "清潔", "管理費", "保險", "稅金", "其他"]

logger = logging.getLogger(__name__)


# ==================== 輔助：取得 user_id ====================

def _get_user_id() -> str | None:
    """
    ✅ [FIX v2.2] 統一從 session_state 取 user_id
    支援多種 key 命名（相容不同版本 session manager）
    """
    for key in ("user_id", "uid", "auth_user_id"):
        uid = st.session_state.get(key)
        if uid:
            return uid
    logger.warning("⚠️ 無法從 session_state 取得 user_id")
    return None


# ==================== Tab 1: 新增支出 ====================

def render_add_tab(expense_service: ExpenseService):
    section_header("➕ 新增支出", "", divider=True)

    # confirm 提示移到 form 外
    if st.session_state.get("pending_expense_no_desc"):
        pending = st.session_state.pending_expense_no_desc
        st.warning("⚠️ 說明欄位為空，確定要新增嗎？")
        col_yes, col_no = st.columns(2)

        with col_yes:
            if st.button("✅ 確認新增", type="primary", key="confirm_add_yes"):
                user_id = _get_user_id()
                if not user_id:
                    st.error("❌ 無法取得登入資訊，請重新登入")
                    return

                ok, msg = expense_service.add_expense(
                    user_id  = user_id,           # ✅ FIX v2.2
                    date     = pending["date"],
                    category = pending["category"],
                    amount   = pending["amount"],
                    description = "無說明",
                )
                if ok:
                    st.success("✅ 新增成功")
                    st.balloons()
                    del st.session_state.pending_expense_no_desc
                    st.rerun()
                else:
                    st.error(f"❌ 新增失敗: {msg}")

        with col_no:
            if st.button("❌ 取消", key="confirm_add_no"):
                del st.session_state.pending_expense_no_desc
                st.rerun()
        return

    with st.form("add_expense_form"):
        col1, col2 = st.columns(2)

        with col1:
            expense_date = st.date_input("日期", value=date.today(), key="add_date")
            category     = st.selectbox("類別", EXPENSE.CATEGORIES, key="add_category")

        with col2:
            amount = st.number_input("金額", min_value=0, value=0, step=100, key="add_amount")
            if amount > 0 and category:
                st.caption(f"💡 {category} 支出：${amount:,}")

        description = st.text_area(
            "說明", placeholder="例如：2A 房間水龍頭維修", key="add_desc"
        )

        submitted = st.form_submit_button("💾 新增支出", type="primary",
                                          use_container_width=True)

        if submitted:
            if amount <= 0:
                st.error("⚠️ 請輸入金額")
            elif not description.strip():
                st.session_state.pending_expense_no_desc = {
                    "date":     expense_date.isoformat(),
                    "category": category,
                    "amount":   amount,
                }
                st.rerun()
            else:
                user_id = _get_user_id()
                if not user_id:
                    st.error("❌ 無法取得登入資訊，請重新登入")
                    return

                ok, msg = expense_service.add_expense(
                    user_id     = user_id,        # ✅ FIX v2.2
                    date        = expense_date.isoformat(),
                    category    = category,
                    amount      = amount,
                    description = description,
                )
                if ok:
                    st.success("✅ 新增成功")
                    st.balloons()
                    st.rerun()
                else:
                    st.error(f"❌ 新增失敗: {msg}")


# ==================== Tab 2: 支出列表 ====================

def render_list_tab(expense_service: ExpenseService):
    section_header("📋 支出列表", "", divider=True)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        filter_year = st.selectbox(
            "年份",
            [None] + list(range(2020, 2031)),
            format_func=lambda x: "全部" if x is None else str(x),
            index=(date.today().year - 2020 + 1) if date.today().year >= 2020 else 0,
            key="list_year",
        )
    with col2:
        filter_month = st.selectbox(
            "月份",
            [None] + list(range(1, 13)),
            format_func=lambda x: "全部" if x is None else f"{x}月",
            key="list_month",
        )
    with col3:
        filter_category = st.multiselect("類別", EXPENSE.CATEGORIES, key="list_category")
    with col4:
        limit = st.number_input(
            "顯示筆數", min_value=10, max_value=500, value=100, step=10, key="list_limit"
        )

    st.divider()

    try:
        expenses = expense_service.get_expenses(
            year       = filter_year,
            month      = filter_month,
            categories = filter_category if filter_category else None,
            limit      = limit,
        )
        df = pd.DataFrame(expenses) if expenses else pd.DataFrame()
    except Exception as e:
        logger.error(f"查詢支出失敗: {e}")
        st.error(f"❌ 查詢失敗: {e}")
        return

    if df.empty:
        empty_state("暫無支出記錄", "📭", "")
        return

    total_amount = df["amount"].sum()
    avg_amount   = df["amount"].mean()

    c1, c2, c3 = st.columns(3)
    with c1: metric_card("總金額",   f"${total_amount:,.0f}", "", "💰", "normal")
    with c2: metric_card("總筆數",   str(len(df)),            "", "📊", "normal")
    with c3: metric_card("平均金額", f"${avg_amount:,.0f}",   "", "📈", "normal")

    st.divider()
    st.write(f"**共 {len(df)} 筆支出記錄**")

    display_df = df.copy()
    if "expense_date" in display_df.columns:
        display_df["expense_date"] = pd.to_datetime(
            display_df["expense_date"]
        ).dt.strftime("%Y-%m-%d")
    if "amount" in display_df.columns:
        display_df["amount_display"] = display_df["amount"].apply(lambda x: f"${x:,.0f}")

    # 編輯 / 刪除
    if "id" in df.columns and len(df) > 0:
        expense_options = {
            f"ID {row['id']} - {row.get('category','未分類')} (${row.get('amount',0):,.0f})": row["id"]
            for _, row in df.iterrows()
        }

        selected_label = st.selectbox(
            "選擇支出項目進行編輯或刪除",
            ["-- 請選擇 --"] + list(expense_options.keys()),
            key="selected_expense",
        )

        if selected_label != "-- 請選擇 --":
            selected_expense = expense_options[selected_label]
            expense_row      = df[df["id"] == selected_expense].iloc[0]

            col_edit, col_delete = st.columns([3, 1])

            with col_edit:
                with st.expander("✏️ 編輯支出", expanded=True):
                    with st.form("edit_expense_form"):
                        edit_date = st.date_input(
                            "日期",
                            value=pd.to_datetime(expense_row["expense_date"]).date(),
                            key="edit_date",
                        )
                        ce1, ce2 = st.columns(2)
                        with ce1:
                            edit_category = st.selectbox(
                                "類別", EXPENSE.CATEGORIES,
                                index=(
                                    EXPENSE.CATEGORIES.index(expense_row["category"])
                                    if expense_row["category"] in EXPENSE.CATEGORIES else 0
                                ),
                                key="edit_category",
                            )
                        with ce2:
                            edit_amount = st.number_input(
                                "金額", min_value=0,
                                value=int(expense_row["amount"]),
                                step=100, key="edit_amount",
                            )

                        edit_desc = st.text_area(
                            "說明",
                            value=expense_row.get("description", ""),
                            key="edit_desc",
                        )

                        if st.form_submit_button("💾 儲存變更", type="primary",
                                                 use_container_width=True):
                            ok, msg = expense_service.update_expense(
                                selected_expense,
                                edit_date.isoformat(),
                                edit_category,
                                edit_amount,
                                edit_desc,
                            )
                            if ok:
                                st.success("✅ 更新成功")
                                st.rerun()
                            else:
                                st.error(f"❌ 更新失敗: {msg}")

            with col_delete:
                st.write(""); st.write("")
                if st.button("🗑️ 刪除", type="secondary", key="delete_btn",
                             use_container_width=True):
                    if st.session_state.get("confirm_delete_expense"):
                        ok, msg = expense_service.delete_expense(selected_expense)
                        if ok:
                            st.success("✅ 刪除成功")
                            del st.session_state.confirm_delete_expense
                            st.rerun()
                        else:
                            st.error(f"❌ 刪除失敗: {msg}")
                    else:
                        st.session_state.confirm_delete_expense = True
                        st.warning("⚠️ 再次點擊確認刪除")

            st.divider()

    rename = {
        "expense_date":   "日期",
        "category":       "類別",
        "amount_display": "金額",
        "description":    "說明",
    }
    cols_to_show   = [c for c in ["id","expense_date","category","amount_display","description"]
                      if c in display_df.columns]

    st.dataframe(
        display_df[cols_to_show].rename(columns=rename),
        use_container_width=True,   # ✅ FIX 2
        hide_index=True,
        key="expense_list",
    )


# ==================== Tab 3: 統計分析 ====================

def render_stats_tab(expense_service: ExpenseService):
    section_header("📊 統計分析", "", divider=True)

    col1, col2 = st.columns(2)
    with col1:
        stats_year = st.selectbox(
            "年份", range(2020, 2031),
            index=(date.today().year - 2020), key="stats_year",
        )
    with col2:
        stats_type = st.radio(
            "統計類型", ["月度分析", "年度總覽", "類別分析"],
            horizontal=True, key="stats_type",
        )

    st.divider()

    try:
        expenses = expense_service.get_expenses(year=stats_year, limit=1000)
        df       = pd.DataFrame(expenses) if expenses else pd.DataFrame()
    except Exception as e:
        logger.error(f"查詢統計資料失敗: {e}")
        st.error(f"❌ 查詢失敗: {e}")
        return

    if df.empty:
        empty_state(f"{stats_year} 年無支出記錄", "📭", "")
        return

    df["date"]  = pd.to_datetime(df["expense_date"])
    df["year"]  = df["date"].dt.year
    df["month"] = df["date"].dt.month

    # ── 月度分析 ──────────────────────────────────────────
    if stats_type == "月度分析":
        month    = st.selectbox("月份", range(1, 13),
                                index=(date.today().month - 1), key="stats_month")
        df_month = df[df["month"] == month]

        if df_month.empty:
            empty_state(f"{stats_year} 年 {month} 月無支出記錄", "📭", "")
            return

        total = df_month["amount"].sum()
        count = len(df_month)
        avg   = df_month["amount"].mean()

        c1, c2, c3 = st.columns(3)
        with c1: metric_card("總支出", f"${total:,.0f}", "", "💰", "normal")
        with c2: metric_card("筆數",   str(count),       "", "📊", "normal")
        with c3: metric_card("平均",   f"${avg:,.0f}",   "", "📈", "normal")

        st.divider()
        st.write("**類別分布**")
        category_sum = (
            df_month.groupby("category")["amount"].sum()
            .reset_index()
            .rename(columns={"category": "類別", "amount": "金額"})
            .sort_values("金額", ascending=False)
        )
        st.bar_chart(category_sum.set_index("類別"))

        st.divider()
        st.write("**明細**")
        cat_display = category_sum.copy()
        cat_display["金額"] = cat_display["金額"].apply(lambda x: f"${x:,.0f}")
        st.dataframe(
            cat_display,
            use_container_width=True,   # ✅ FIX 3
            hide_index=True,
            key="month_category",
        )

    # ── 年度總覽 ──────────────────────────────────────────
    elif stats_type == "年度總覽":
        total_year = df["amount"].sum()
        count_year = len(df)
        avg_month  = total_year / 12

        c1, c2, c3 = st.columns(3)
        with c1: metric_card("年度總支出", f"${total_year:,.0f}", "", "💰", "normal")
        with c2: metric_card("總筆數",     str(count_year),       "", "📊", "normal")
        with c3: metric_card("月平均",     f"${avg_month:,.0f}",  "", "📈", "normal")

        st.divider()
        st.write("**月度趨勢**")
        monthly = (
            df.groupby("month")["amount"].sum().reset_index()
            .rename(columns={"month": "月份", "amount": "金額"})
        )
        all_months = pd.DataFrame({"月份": range(1, 13)})
        monthly    = all_months.merge(monthly, on="月份", how="left").fillna(0)
        st.line_chart(monthly.set_index("月份"))

        st.divider()
        monthly_display = monthly.copy()
        monthly_display["金額"] = monthly_display["金額"].apply(lambda x: f"${x:,.0f}")
        st.dataframe(
            monthly_display,
            use_container_width=True,   # ✅ FIX 4
            hide_index=True,
            key="monthly_trend",
        )

    # ── 類別分析 ──────────────────────────────────────────
    else:
        total_year = df["amount"].sum()
        st.write(f"**{stats_year} 年總支出：${total_year:,.0f}**")
        st.divider()

        category_stats = (
            df.groupby("category")
            .agg({"amount": ["sum", "count", "mean"]})
            .reset_index()
        )
        category_stats.columns = ["類別", "總金額", "筆數", "平均"]
        category_stats["佔比"] = (category_stats["總金額"] / total_year * 100).round(1)
        category_stats = category_stats.sort_values("總金額", ascending=False)

        st.write("**類別分布圖**")
        st.bar_chart(category_stats.set_index("類別")["總金額"])

        st.divider()
        cat_disp = category_stats.copy()
        cat_disp["總金額"] = cat_disp["總金額"].apply(lambda x: f"${x:,.0f}")
        cat_disp["平均"]   = cat_disp["平均"].apply(lambda x: f"${x:,.0f}")
        cat_disp["佔比"]   = cat_disp["佔比"].apply(lambda x: f"{x}%")
        st.dataframe(
            cat_disp,
            use_container_width=True,   # ✅ FIX 5
            hide_index=True,
            key="category_stats",
        )


# ==================== 主入口 ====================

def render():
    st.title("💸 支出記錄")
    expense_service = ExpenseService()
    tab1, tab2, tab3 = st.tabs(["➕ 新增支出", "📋 支出列表", "📊 統計分析"])
    with tab1: render_add_tab(expense_service)
    with tab2: render_list_tab(expense_service)
    with tab3: render_stats_tab(expense_service)

def show():
    render()

if __name__ == "__main__":
    show()
