"""
支出記錄頁面 - v3.0
✅ [FIX] 表格隱藏 id 欄，只顯示「日期 / 類別 / 金額 / 說明」
✅ [FIX] Selectbox label → 「日期｜類別｜$金額｜說明」可辨識格式
✅ [FIX] use_container_width → width="stretch"
✅ [FIX] info_card \\n 修正
✅ [NEW] 關鍵字搜尋（說明欄）
✅ [NEW] 篩選器整合進列表頁上方
✅ [NEW] 編輯區移至獨立欄位，刪除確認流程優化
✅ [KEEP] v2.3 所有功能：expense_date= 修正、確認無說明流程
"""

import streamlit as st
import pandas as pd
from datetime import date
import logging

from services.expense_service import ExpenseService

try:
    from components.cards import section_header, metric_card, empty_state, data_table
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
        st.dataframe(df, width="stretch", key=key, hide_index=True)

try:
    from config.constants import EXPENSE
except ImportError:
    class EXPENSE:
        CATEGORIES = ["維修", "水電費", "清潔", "管理費", "保險", "稅金", "網路費", "貸款", "雜項", "其他"]

logger = logging.getLogger(__name__)

# ── DB 欄位 → 顯示名稱 ────────────────────────────────────
COLUMN_DISPLAY_MAP = {
    "expense_date":   "日期",
    "category":       "類別",
    "amount_display": "金額",
    "description":    "說明",
}


# ── 取得 user_id ─────────────────────────────────────────
def _get_user_id() -> str | None:
    for key in ("user_id", "uid", "auth_user_id"):
        uid = st.session_state.get(key)
        if uid:
            return uid
    logger.warning("⚠️ 無法從 session_state 取得 user_id")
    return None


# ── Selectbox label 產生器（一眼辨識）────────────────────
def _expense_label(row: pd.Series) -> str:
    """
    格式：2026-03-03｜網路費｜$1,199｜3月網路
    """
    try:
        d = pd.to_datetime(row.get("expense_date", "")).strftime("%Y-%m-%d")
    except Exception:
        d = str(row.get("expense_date", ""))
    cat  = row.get("category", "未分類")
    amt  = row.get("amount", 0)
    desc = str(row.get("description", "")) or "無說明"
    # 說明太長就截斷
    desc = desc[:15] + "…" if len(desc) > 15 else desc
    return f"{d}｜{cat}｜${float(amt):,.0f}｜{desc}"


# ==================== Tab 1: 新增支出 ====================

def render_add_tab(expense_service: ExpenseService):
    section_header("新增支出", "➕")

    # 無說明確認流程（form 外）
    if st.session_state.get("pending_expense_no_desc"):
        pending = st.session_state.pending_expense_no_desc
        st.warning(
            f"⚠️ 說明欄位為空，確定要新增嗎？\n\n"
            f"**{pending['date']} ｜ {pending['category']} ｜ ${int(pending['amount']):,}**"
        )
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("✅ 確認新增", type="primary", key="confirm_add_yes", width="stretch"):
                user_id = _get_user_id()
                if not user_id:
                    st.error("❌ 無法取得登入資訊，請重新登入")
                    return
                ok, msg = expense_service.add_expense(
                    user_id      = user_id,
                    expense_date = pending["date"],
                    category     = pending["category"],
                    amount       = pending["amount"],
                    description  = "無說明",
                )
                if ok:
                    st.success("✅ 新增成功")
                    st.balloons()
                    del st.session_state.pending_expense_no_desc
                    st.rerun()
                else:
                    st.error(f"❌ 新增失敗: {msg}")
        with col_no:
            if st.button("❌ 取消", key="confirm_add_no", width="stretch"):
                del st.session_state.pending_expense_no_desc
                st.rerun()
        return

    with st.form("add_expense_form"):
        col1, col2 = st.columns(2)

        with col1:
            expense_date = st.date_input("日期 *", value=date.today(), key="add_date")
            category     = st.selectbox("類別 *", EXPENSE.CATEGORIES, key="add_category")

        with col2:
            amount = st.number_input(
                "金額 *", min_value=0.0, value=0.0, step=100.0, key="add_amount"
            )
            if amount > 0:
                st.caption(f"💡 {category} ${amount:,.0f}")

        description = st.text_area(
            "說明", placeholder="例如：2A 房間水龍頭維修、3月網路費",
            key="add_desc"
        )

        submitted = st.form_submit_button("💾 新增支出", type="primary", width="stretch")

        if submitted:
            if amount <= 0:
                st.error("⚠️ 請輸入有效金額（必須 > 0）")
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
                    user_id      = user_id,
                    expense_date = expense_date.isoformat(),
                    category     = category,
                    amount       = amount,
                    description  = description,
                )
                if ok:
                    st.success("✅ 新增成功")
                    st.balloons()
                    st.rerun()
                else:
                    st.error(f"❌ 新增失敗: {msg}")


# ==================== Tab 2: 支出列表 ====================

def render_list_tab(expense_service: ExpenseService):
    section_header("支出列表", "📋")

    # ── 篩選器區 ─────────────────────────────────────────
    col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 3, 2])
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
        search_keyword = st.text_input(
            "搜尋說明", placeholder="輸入關鍵字…", key="list_keyword"
        )
    with col5:
        limit = st.number_input(
            "顯示筆數", min_value=10, max_value=500, value=100, step=10, key="list_limit"
        )

    st.divider()

    # ── 讀取資料 ─────────────────────────────────────────
    try:
        expenses = expense_service.get_expenses(
            year       = filter_year,
            month      = filter_month,
            categories = filter_category if filter_category else None,
            limit      = limit,
        )
        df = pd.DataFrame(expenses) if expenses else pd.DataFrame()
    except Exception as e:
        logger.error(f"查詢支出失敗: {e}", exc_info=True)
        st.error(f"❌ 查詢失敗: {e}")
        return

    if df.empty:
        empty_state("暫無支出記錄", "📭", "點擊「新增支出」開始記錄")
        return

    # 關鍵字過濾（前端 in-memory）
    if search_keyword.strip():
        mask = df.get("description", pd.Series(dtype=str)).str.contains(
            search_keyword.strip(), case=False, na=False
        )
        df = df[mask]

    if df.empty:
        st.info(f"💭 沒有符合「{search_keyword}」的記錄")
        return

    # ── 摘要指標 ─────────────────────────────────────────
    total_amount = df["amount"].sum()
    avg_amount   = df["amount"].mean()
    c1, c2, c3  = st.columns(3)
    with c1: metric_card("總金額",   f"${total_amount:,.0f}", "", "💰")
    with c2: metric_card("總筆數",   str(len(df)),            "", "📊")
    with c3: metric_card("平均金額", f"${avg_amount:,.0f}",   "", "📈")

    st.divider()

    # ── 編輯 / 刪除選擇器 ────────────────────────────────
    if "id" in df.columns and len(df) > 0:
        # ✅ FIX: label 顯示 「日期｜類別｜$金額｜說明」，隱藏 UUID
        expense_options = {
            _expense_label(row): row["id"]
            for _, row in df.sort_values(
                "expense_date", ascending=False
            ).iterrows()
        }

        selected_label = st.selectbox(
            "選擇支出項目進行編輯或刪除",
            options=[None] + list(expense_options.keys()),
            format_func=lambda x: "-- 請選擇 --" if x is None else x,
            index=0,
            key="selected_expense",
        )

        if selected_label is not None:
            selected_id  = expense_options[selected_label]
            expense_row  = df[df["id"] == selected_id].iloc[0]

            st.divider()
            col_edit, col_delete = st.columns([4, 1])

            # ── 編輯區 ────────────────────────────────────
            with col_edit:
                with st.expander("✏️ 編輯此筆支出", expanded=True):
                    with st.form("edit_expense_form"):
                        ef1, ef2 = st.columns(2)
                        with ef1:
                            edit_date = st.date_input(
                                "日期",
                                value=pd.to_datetime(expense_row["expense_date"]).date(),
                                key="edit_date",
                            )
                            edit_category = st.selectbox(
                                "類別",
                                EXPENSE.CATEGORIES,
                                index=(
                                    EXPENSE.CATEGORIES.index(expense_row["category"])
                                    if expense_row.get("category") in EXPENSE.CATEGORIES
                                    else 0
                                ),
                                key="edit_category",
                            )
                        with ef2:
                            edit_amount = st.number_input(
                                "金額",
                                min_value=0.0,
                                value=float(expense_row.get("amount", 0)),
                                step=100.0,
                                key="edit_amount",
                            )
                            st.write("")  # 間距對齊

                        edit_desc = st.text_area(
                            "說明",
                            value=expense_row.get("description", ""),
                            key="edit_desc",
                        )

                        if st.form_submit_button("💾 儲存變更", type="primary", width="stretch"):
                            ok, msg = expense_service.update_expense(
                                selected_id,
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

            # ── 刪除區 ────────────────────────────────────
            with col_delete:
                st.write(""); st.write(""); st.write("")
                confirm_key = f"confirm_delete_{selected_id}"
                if st.button("🗑️ 刪除", type="secondary", key="delete_btn", width="stretch"):
                    if not st.session_state.get(confirm_key):
                        st.session_state[confirm_key] = True
                        st.rerun()
                    else:
                        ok, msg = expense_service.delete_expense(selected_id)
                        if ok:
                            st.success("✅ 刪除成功")
                            if confirm_key in st.session_state:
                                del st.session_state[confirm_key]
                            st.rerun()
                        else:
                            st.error(f"❌ 刪除失敗: {msg}")

                if st.session_state.get(confirm_key):
                    st.warning("⚠️ 再次點擊確認刪除")

            st.divider()

    # ── 主表格（不顯示 id）──────────────────────────────
    st.write(f"**共 {len(df)} 筆支出記錄**")

    display_df = df.copy()

    # 格式化
    if "expense_date" in display_df.columns:
        display_df["expense_date"] = pd.to_datetime(
            display_df["expense_date"], errors="coerce"
        ).dt.strftime("%Y-%m-%d")

    if "amount" in display_df.columns:
        display_df["amount_display"] = display_df["amount"].apply(
            lambda x: f"${float(x):,.0f}" if pd.notna(x) else "-"
        )

    # ✅ FIX: 不顯示 id；只顯示可讀欄位
    show_cols = [c for c in ["expense_date", "category", "amount_display", "description"]
                 if c in display_df.columns]

    data_table(
        display_df[show_cols].rename(columns=COLUMN_DISPLAY_MAP),
        key="expense_list",
    )


# ==================== Tab 3: 統計分析 ====================

def render_stats_tab(expense_service: ExpenseService):
    section_header("統計分析", "📊")

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
        logger.error(f"查詢統計資料失敗: {e}", exc_info=True)
        st.error(f"❌ 查詢失敗: {e}")
        return

    if df.empty:
        empty_state(f"{stats_year} 年無支出記錄", "📭", "")
        return

    df["_date"]  = pd.to_datetime(df["expense_date"], errors="coerce")
    df["_month"] = df["_date"].dt.month

    # ── 月度分析 ─────────────────────────────────────────
    if stats_type == "月度分析":
        month    = st.selectbox(
            "月份", range(1, 13),
            index=(date.today().month - 1), key="stats_month"
        )
        df_month = df[df["_month"] == month]

        if df_month.empty:
            empty_state(f"{stats_year}/{month} 月無記錄", "📭", "")
            return

        c1, c2, c3 = st.columns(3)
        with c1: metric_card("總支出", f"${df_month['amount'].sum():,.0f}", "", "💰")
        with c2: metric_card("筆數",   str(len(df_month)),                  "", "📊")
        with c3: metric_card("平均",   f"${df_month['amount'].mean():,.0f}", "", "📈")

        st.divider()
        cat_sum = (
            df_month.groupby("category")["amount"].sum().reset_index()
            .rename(columns={"category": "類別", "amount": "金額"})
            .sort_values("金額", ascending=False)
        )
        st.write("**類別分布**")
        st.bar_chart(cat_sum.set_index("類別"))
        st.divider()
        cat_display = cat_sum.copy()
        cat_display["金額"] = cat_display["金額"].apply(lambda x: f"${x:,.0f}")
        data_table(cat_display, key="month_category")

    # ── 年度總覽 ─────────────────────────────────────────
    elif stats_type == "年度總覽":
        total_year = df["amount"].sum()
        c1, c2, c3 = st.columns(3)
        with c1: metric_card("年度總支出", f"${total_year:,.0f}",        "", "💰")
        with c2: metric_card("總筆數",     str(len(df)),                  "", "📊")
        with c3: metric_card("月平均",     f"${total_year / 12:,.0f}",   "", "📈")

        st.divider()
        monthly = (
            df.groupby("_month")["amount"].sum().reset_index()
            .rename(columns={"_month": "月份", "amount": "金額"})
        )
        all_months = pd.DataFrame({"月份": range(1, 13)})
        monthly    = all_months.merge(monthly, on="月份", how="left").fillna(0)
        st.write("**月度趨勢**")
        st.line_chart(monthly.set_index("月份"))

        st.divider()
        monthly_disp = monthly.copy()
        monthly_disp["金額"] = monthly_disp["金額"].apply(lambda x: f"${x:,.0f}")
        data_table(monthly_disp, key="monthly_trend")

    # ── 類別分析 ─────────────────────────────────────────
    else:
        total_year = df["amount"].sum()
        st.write(f"**{stats_year} 年總支出：${total_year:,.0f}**")
        st.divider()

        cat_stats = (
            df.groupby("category")
            .agg(總金額=("amount", "sum"), 筆數=("amount", "count"), 平均=("amount", "mean"))
            .reset_index()
            .rename(columns={"category": "類別"})
            .sort_values("總金額", ascending=False)
        )
        cat_stats["佔比"] = (cat_stats["總金額"] / total_year * 100).round(1).astype(str) + "%"

        st.write("**類別分布圖**")
        st.bar_chart(cat_stats.set_index("類別")["總金額"])
        st.divider()

        cat_disp = cat_stats.copy()
        cat_disp["總金額"] = cat_disp["總金額"].apply(lambda x: f"${x:,.0f}")
        cat_disp["平均"]   = cat_disp["平均"].apply(lambda x: f"${x:,.0f}")
        data_table(cat_disp, key="category_stats")


# ==================== 主入口 ====================

def render():
    st.title("💸 支出記錄")
    try:
        expense_service = ExpenseService()
        if not expense_service.health_check():
            st.error("❌ 資料庫連接失敗，請稍後再試")
            return
    except Exception as e:
        st.error(f"❌ 初始化服務失敗: {str(e)}")
        logger.error(f"初始化 ExpenseService 失敗: {str(e)}", exc_info=True)
        return

    tab1, tab2, tab3 = st.tabs(["➕ 新增支出", "📋 支出列表", "📊 統計分析"])
    with tab1: render_add_tab(expense_service)
    with tab2: render_list_tab(expense_service)
    with tab3: render_stats_tab(expense_service)


def show():
    render()


if __name__ == "__main__":
    show()
