"""
繳費追蹤頁面 - v3.2
✅ [FIX v3.2] 全部 width="stretch" → use_container_width=True（共 13 處）
✅ [FIX v3.2] update_payment → mark_paid 直接呼叫（移除廢棄 wrapper）
✅ 租金追蹤 + 電費追蹤 + 綜合追蹤
"""

import streamlit as st
from datetime import datetime, date
from decimal import Decimal
import pandas as pd
import logging

from services.payment_service import PaymentService
from services.electricity_service import ElectricityService
from services.tenant_service import TenantService

logger = logging.getLogger(__name__)


# ==================== 輔助函數 ====================

def safe_float(value) -> float:
    try:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, str):
            clean = str(value).replace("$","").replace("＄","").replace(",","").replace(" ","")
            return float(clean) if clean else 0.0
        return float(value)
    except (ValueError, TypeError):
        logger.warning(f"無法轉換為 float: {value}")
        return 0.0


# ==================== 主入口 ====================

def render():
    render_tracking_page()

def show():
    render()

def render_tracking_page():
    st.title("📋 繳費追蹤")

    payment_service     = PaymentService()
    electricity_service = ElectricityService()
    tenant_service      = TenantService()

    tab1, tab2, tab3 = st.tabs(["🏠 租金追蹤", "⚡ 電費追蹤", "📊 綜合追蹤"])

    with tab1:
        render_rent_tracking(payment_service, tenant_service)
    with tab2:
        render_electricity_tracking(electricity_service, tenant_service)
    with tab3:
        render_combined_tracking(payment_service, electricity_service, tenant_service)


# ==================== Tab 1: 租金追蹤 ====================

def render_rent_tracking(payment_service: PaymentService, tenant_service: TenantService):
    st.subheader("🔍 快速篩選")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if st.button("🚨 逾期未繳", key="rent_overdue",
                     use_container_width=True, type="primary"):   # ✅ FIX 1
            st.session_state.rent_filter = "overdue"
            st.rerun()
    with col2:
        if st.button("⚠️ 即將到期", key="rent_upcoming",
                     use_container_width=True):                   # ✅ FIX 2
            st.session_state.rent_filter = "upcoming"
            st.rerun()
    with col3:
        if st.button("⏳ 全部未繳", key="rent_unpaid",
                     use_container_width=True):                   # ✅ FIX 3
            st.session_state.rent_filter = "unpaid"
            st.rerun()
    with col4:
        if st.button("🔄 重置", key="rent_reset",
                     use_container_width=True):                   # ✅ FIX 4
            st.session_state.rent_filter = "all"
            st.rerun()

    if "rent_filter" not in st.session_state:
        st.session_state.rent_filter = "all"

    current_filter = st.session_state.rent_filter
    st.divider()

    # 房號篩選
    try:
        tenants       = tenant_service.get_all_tenants()
        room_list     = sorted({t["room_number"] for t in tenants})
        selected_rooms = st.multiselect(
            "🏠 房號篩選（可多選）", options=room_list, default=[],
            key="rent_room_filter",
        )
    except Exception as e:
        st.error(f"❌ 載入房間列表失敗: {str(e)}")
        logger.error(f"載入房間列表失敗: {str(e)}", exc_info=True)
        selected_rooms = []

    # 載入資料
    try:
        if current_filter == "overdue":
            payments = payment_service.get_overdue_payments()
            st.info(f"📊 顯示：逾期未繳（共 {len(payments)} 筆）")

        elif current_filter == "upcoming":
            all_unpaid = payment_service.get_unpaid_payments()
            today      = date.today()
            payments   = [
                p for p in all_unpaid
                if 0 <= (pd.to_datetime(p["due_date"]).date() - today).days <= 3
            ]
            st.info(f"📊 顯示：3 天內到期（共 {len(payments)} 筆）")

        elif current_filter == "unpaid":
            payments = payment_service.get_unpaid_payments()
            st.info(f"📊 顯示：全部未繳（共 {len(payments)} 筆）")

        else:
            payments = payment_service.get_all_payments()
            st.info(f"📊 顯示：全部記錄（共 {len(payments)} 筆）")

        if selected_rooms:
            payments = [p for p in payments if p["room_number"] in selected_rooms]
            st.caption(f"🔎 已篩選房號：{', '.join(selected_rooms)}")

        if not payments:
            st.success("✅ 沒有符合條件的記錄")
            return

        df           = pd.DataFrame(payments)
        today_ts     = pd.Timestamp.now().normalize()
        df["due_date_dt"]    = pd.to_datetime(df["due_date"])
        df["days_overdue"]   = (today_ts - df["due_date_dt"]).dt.days.clip(lower=0)
        df["due_date"]       = df["due_date_dt"].dt.strftime("%Y-%m-%d")

        status_map = {"unpaid": "⏳ 未繳", "paid": "✅ 已繳", "overdue": "🚨 逾期"}
        df["status_display"]  = df["status"].map(status_map).fillna(df["status"])
        df["overdue_display"] = df.apply(
            lambda r: f"🚨 逾期 {r['days_overdue']} 天" if r["days_overdue"] > 0 else "-",
            axis=1,
        )

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("待繳款",   f"{len(df[df['status']=='unpaid'])} 筆")
        total_overdue = len(df[df["days_overdue"] > 0])
        c2.metric("逾期", f"{total_overdue} 筆",
                  delta="-" if total_overdue > 0 else "正常", delta_color="inverse")
        c3.metric("待收金額", f"${sum(safe_float(a) for a in df[df['status']=='unpaid']['amount']):,.0f}")
        c4.metric("逾期金額", f"${sum(safe_float(a) for a in df[df['days_overdue']>0]['amount']):,.0f}")

        st.divider()
        st.subheader("📋 詳細列表")

        df_sorted = df.sort_values(["days_overdue","due_date_dt"], ascending=[False,True])
        df_sorted["amount_display"] = df_sorted["amount"].apply(lambda x: f"${safe_float(x):,.0f}")

        display_cols  = ["room_number","tenant_name","payment_year","payment_month",
                         "amount_display","due_date","overdue_display","status_display"]
        available_cols = [c for c in display_cols if c in df_sorted.columns]

        st.dataframe(
            df_sorted[available_cols].rename(columns={
                "room_number": "房號", "tenant_name": "房客",
                "payment_year": "年份", "payment_month": "月份",
                "amount_display": "金額", "due_date": "到期日",
                "overdue_display": "逾期狀態", "status_display": "繳款狀態",
            }),
            use_container_width=True,   # ✅ FIX 5
            hide_index=True,
        )

        # 批量標記
        unpaid_df = df[df["status"] == "unpaid"]
        if not unpaid_df.empty:
            st.divider()
            st.subheader("✅ 批量標記已繳")

            col1, col2 = st.columns([3, 1])
            with col1:
                selected_ids = st.multiselect(
                    "選擇要標記為已繳的項目（可多選）",
                    options=unpaid_df["id"].tolist(),
                    format_func=lambda x: (
                        f"{unpaid_df[unpaid_df['id']==x]['room_number'].values[0]} - "
                        f"{unpaid_df[unpaid_df['id']==x]['tenant_name'].values[0]} "
                        f"({unpaid_df[unpaid_df['id']==x]['payment_year'].values[0]}/"
                        f"{unpaid_df[unpaid_df['id']==x]['payment_month'].values[0]:02d}) "
                        f"${safe_float(unpaid_df[unpaid_df['id']==x]['amount'].values[0]):,.0f}"
                    ),
                    key="rent_multiselect",
                )
            with col2:
                st.write(""); st.write("")
                if st.button(
                    f"✅ 標記 ({len(selected_ids)})", type="primary",
                    disabled=len(selected_ids) == 0,
                    use_container_width=True,   # ✅ FIX 6
                    key="rent_mark_paid",
                ):
                    with st.spinner("處理中..."):
                        try:
                            results = payment_service.batch_mark_paid(selected_ids)
                            if results["success"] > 0:
                                st.success(f"✅ 成功標記 {results['success']} 筆")
                                st.rerun()
                            if results["failed"] > 0:
                                st.error(f"❌ 失敗 {results['failed']} 筆")
                        except Exception as e:
                            st.error(f"❌ 標記失敗: {str(e)}")
                            logger.error(f"批量標記失敗: {str(e)}", exc_info=True)

    except Exception as e:
        st.error(f"❌ 載入資料失敗: {str(e)}")
        logger.error(f"租金追蹤錯誤: {str(e)}", exc_info=True)


# ==================== Tab 2: 電費追蹤 ====================

def render_electricity_tracking(
    electricity_service: ElectricityService,
    tenant_service: TenantService,
):
    st.subheader("⚡ 電費繳費追蹤")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("⏳ 未繳電費", key="elec_unpaid",
                     use_container_width=True, type="primary"):   # ✅ FIX 7
            st.session_state.elec_filter = "unpaid"; st.rerun()
    with col2:
        if st.button("✅ 已繳電費", key="elec_paid",
                     use_container_width=True):                   # ✅ FIX 8
            st.session_state.elec_filter = "paid"; st.rerun()
    with col3:
        if st.button("📜 全部電費", key="elec_all",
                     use_container_width=True):                   # ✅ FIX 9
            st.session_state.elec_filter = "all"; st.rerun()
    with col4:
        if st.button("🔄 重置", key="elec_reset",
                     use_container_width=True):                   # ✅ FIX 10
            st.session_state.elec_filter = "unpaid"; st.rerun()

    if "elec_filter" not in st.session_state:
        st.session_state.elec_filter = "unpaid"
    current_filter = st.session_state.elec_filter

    st.divider()

    try:
        periods = electricity_service.get_all_periods()
        if not periods:
            st.warning("⚠️ 尚未建立電費計費期間，請前往「⚡ 電費管理」建立")
            return

        period_options = {
            f"{p['period_year']}/{p['period_month_start']:02d}-{p['period_month_end']:02d} (ID: {p['id']})": p["id"]
            for p in periods
        }
        selected_period = st.selectbox("📅 選擇計費期間",
                                       list(period_options.keys()),
                                       key="elec_period_select")
        if not selected_period:
            return

        period_id = period_options[selected_period]
        st.info(f"📅 當前期間 ID: {period_id}")

        tenants        = tenant_service.get_all_tenants()
        room_list      = sorted({t["room_number"] for t in tenants})
        selected_rooms = st.multiselect(
            "🏠 房號篩選（可多選）", options=room_list, default=[],
            key="elec_room_filter",
        )

        st.divider()

        with st.spinner("正在載入電費記錄..."):
            records = electricity_service.get_period_records(period_id)
            df      = records.copy() if isinstance(records, pd.DataFrame) else pd.DataFrame(records or [])

        if df.empty:
            st.warning(f"📭 期間 ID {period_id} 尚無電費記錄，請前往「⚡ 電費管理」完成計算並儲存")
            return

        # ── 欄位對齊：get_period_records 已回傳中文欄位，此段為向後相容 ──
        if "room_number" in df.columns:
            df = df.rename(columns={
                "room_number":   "房號",
                "payment_status":"繳費狀態",
                "amount":        "應繳金額",
                "paid_amount":   "已繳金額",
                "usage":         "使用度數",
                "shared_usage":  "公用分攤",
                "total_usage":   "總度數",
                "unit_price":    "單價",
                "tenant_type":   "類型",
                "paid_date":     "繳費日期",
            })

        # ── 繳費狀態正規化（英文 → 中文，已是中文則 fillna 保留原值）──
        if "繳費狀態" in df.columns:
            df["繳費狀態"] = (
                df["繳費狀態"]
                .map({"unpaid": "⏳ 未繳", "paid": "✅ 已繳"})
                .fillna(df["繳費狀態"])
            )

        # 篩選
        if current_filter == "unpaid":
            df = df[df["繳費狀態"] == "⏳ 未繳"]
            st.info(f"📊 顯示：未繳電費（共 {len(df)} 筆）")
        elif current_filter == "paid":
            df = df[df["繳費狀態"] == "✅ 已繳"]
            st.info(f"📊 顯示：已繳電費（共 {len(df)} 筆）")
        else:
            st.info(f"📊 顯示：全部電費（共 {len(df)} 筆）")

        if selected_rooms:
            df = df[df["房號"].isin(selected_rooms)]
            st.caption(f"🔎 已篩選房號：{', '.join(selected_rooms)}")

        if df.empty:
            st.success("✅ 沒有符合條件的記錄")
            return

        df["應繳金額_數值"] = df["應繳金額"].apply(safe_float)
        df["已繳金額_數值"] = df.get("已繳金額", pd.Series([0]*len(df))).apply(safe_float)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("待繳款", f"{len(df[df['繳費狀態']=='⏳ 未繳'])} 筆")
        c2.metric("已繳",   f"{len(df[df['繳費狀態']=='✅ 已繳'])} 筆")
        c3.metric("應收總額", f"${df['應繳金額_數值'].sum():,.0f}")
        c4.metric("已收金額", f"${df['已繳金額_數值'].sum():,.0f}")

        st.divider()
        st.subheader("📋 電費明細")

        display_cols   = ["房號","類型","使用度數","公用分攤",
                          "總度數","單價","應繳金額","已繳金額","繳費狀態","繳費日期"]
        available_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(
            df[available_cols],
            use_container_width=True,   # ✅ FIX 11
            hide_index=True,
        )

        unpaid_df = df[df["繳費狀態"] == "⏳ 未繳"]
        if not unpaid_df.empty:
            st.divider()
            st.subheader("⚡ 快速標記已繳")
            st.caption("💡 點擊房間旁的「✅」按鈕，即可快速更新繳費狀態")

            for idx, row in unpaid_df.iterrows():
                col_info, col_btn = st.columns([4, 1])
                room        = row["房號"]
                amount      = row["應繳金額_數值"]
                tenant_type = row.get("類型", "N/A")
                total_usage = row.get("總度數", 0)

                with col_info:
                    st.write(f"**{room}** | {tenant_type} | {total_usage} 度 | ${amount:,.0f} 元")

                with col_btn:
                    if st.button("✅", key=f"elec_pay_{period_id}_{idx}"):
                        with st.spinner(f"正在標記 {room}..."):
                            try:
                                # ✅ [FIX v3.2] 直接呼叫 mark_paid，不走廢棄 wrapper
                                ok, msg = electricity_service.mark_paid(
                                    period_id    = period_id,
                                    room_number  = room,
                                    paid_amount  = int(amount),
                                    payment_date = date.today().isoformat(),
                                )
                                if ok:
                                    st.success(f"✅ {room} 已標記為已繳")
                                    logger.info(f"電費標記成功: {room} - ${amount:,.0f}")
                                    st.rerun()
                                else:
                                    st.error(f"❌ 標記失敗: {msg}")
                                    logger.error(f"電費標記失敗: {room} - {msg}")
                            except Exception as e:
                                st.error(f"❌ 標記時發生錯誤: {str(e)}")
                                logger.error(f"電費標記異常: {str(e)}", exc_info=True)
        else:
            st.success("✅ 全部已繳清")

    except Exception as e:
        st.error(f"❌ 載入電費記錄失敗: {str(e)}")
        logger.error(f"電費追蹤錯誤: {str(e)}", exc_info=True)


# ==================== Tab 3: 綜合追蹤 ====================

def render_combined_tracking(
    payment_service: PaymentService,
    electricity_service: ElectricityService,
    tenant_service: TenantService,
):
    st.subheader("📊 綜合繳費追蹤")
    st.caption("💡 查看租金與電費的整體繳費狀況")
    st.divider()

    # 租金數據
    try:
        rent_unpaid = payment_service.get_unpaid_payments()
        rent_df     = pd.DataFrame(rent_unpaid) if rent_unpaid else pd.DataFrame()
        rent_total  = sum(safe_float(p["amount"]) for p in rent_unpaid) if rent_unpaid else 0.0
        rent_count  = len(rent_unpaid)
    except Exception as e:
        st.error(f"❌ 載入租金數據失敗: {str(e)}")
        logger.error(f"租金數據載入錯誤: {str(e)}", exc_info=True)
        rent_total, rent_count, rent_df = 0.0, 0, pd.DataFrame()

    # 電費數據
    elec_total, elec_count, elec_unpaid_df = 0.0, 0, pd.DataFrame()
    try:
        periods = electricity_service.get_all_periods()
        if periods:
            latest    = periods[0]
            period_id = latest["id"]
            st.info(
                f"📅 電費期間: {latest['period_year']}/"
                f"{latest['period_month_start']:02d}-{latest['period_month_end']:02d}"
            )

            records_df = electricity_service.get_period_records(period_id)

            if isinstance(records_df, pd.DataFrame) and not records_df.empty:
                elec_df = records_df.copy()

                if "繳費狀態" in elec_df.columns:
                    unpaid_mask = elec_df["繳費狀態"].isin(["⏳ 未繳", "unpaid"])
                elif "payment_status" in elec_df.columns:
                    unpaid_mask = elec_df["payment_status"] == "unpaid"
                else:
                    unpaid_mask = pd.Series([False] * len(elec_df))

                elec_unpaid_df = elec_df[unpaid_mask]
                amount_col     = "應繳金額" if "應繳金額" in elec_unpaid_df.columns else "amount"
                amount_series  = elec_unpaid_df.get(amount_col, pd.Series([], dtype=float))
                elec_total     = sum(safe_float(v) for v in amount_series)
                elec_count     = len(elec_unpaid_df)
        else:
            st.warning("⚠️ 尚未建立電費期間")

    except Exception as e:
        st.error(f"❌ 載入電費數據失敗: {str(e)}")
        logger.error(f"電費數據載入錯誤: {str(e)}", exc_info=True)

    # 整體統計
    st.markdown("### 💰 整體待收摘要")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🏠 租金待收", f"${rent_total:,.0f}",  delta=f"{rent_count} 筆")
    c2.metric("⚡ 電費待收", f"${elec_total:,.0f}",  delta=f"{elec_count} 筆")
    c3.metric("💵 總待收金額", f"${rent_total + elec_total:,.0f}", delta=f"{rent_count+elec_count} 筆")
    c4.metric("📊 收繳概況",  f"{rent_count + elec_count} 筆待繳")

    st.divider()

    # 分類明細
    col_rent, col_elec = st.columns(2)

    with col_rent:
        st.markdown("#### 🏠 租金明細（未繳）")
        if not rent_df.empty:
            d = rent_df[["room_number","tenant_name","payment_year","payment_month","amount"]].copy()
            d["payment_period"]  = d.apply(lambda r: f"{r['payment_year']}/{r['payment_month']:02d}", axis=1)
            d["amount_display"]  = d["amount"].apply(lambda x: f"${safe_float(x):,.0f}")
            st.dataframe(
                d[["room_number","tenant_name","payment_period","amount_display"]].rename(columns={
                    "room_number": "房號", "tenant_name": "房客",
                    "payment_period": "期間", "amount_display": "金額",
                }),
                use_container_width=True,   # ✅ FIX 12
                hide_index=True,
            )
        else:
            st.success("✅ 全部已繳清")

    with col_elec:
        st.markdown("#### ⚡ 電費明細（未繳）")
        if elec_count > 0 and not elec_unpaid_df.empty:
            ed = elec_unpaid_df.copy()
            if "room_number" in ed.columns:
                ed = ed.rename(columns={
                    "room_number": "房號", "tenant_type": "類型",
                    "total_usage": "總度數", "amount": "應繳金額",
                })
            display_cols   = ["房號","類型","總度數","應繳金額"]
            available_cols = [c for c in display_cols if c in ed.columns]
            st.dataframe(
                ed[available_cols],
                use_container_width=True,   # ✅ FIX 13
                hide_index=True,
            )
        else:
            st.success("✅ 全部已繳清")

    st.divider()

    # 快速操作提示
    st.markdown("### 🚀 快速操作")
    col1, col2 = st.columns(2)
    with col1:
        st.info("""
**📝 標記租金已繳：**
1. 前往「🏠 租金追蹤」Tab
2. 使用快速篩選找到未繳項目
3. 勾選項目後點擊「✅ 標記」
        """)
    with col2:
        st.info("""
**⚡ 標記電費已繳：**
1. 前往「⚡ 電費追蹤」Tab
2. 選擇計費期間
3. 點擊房間旁的「✅」按鈕快速標記
        """)


# ==================== 本機測試 ====================
if __name__ == "__main__":
    render_tracking_page()
