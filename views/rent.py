"""
租金管理頁面 v3.3
✅ 完全移除 db 依賴
✅ 使用正確的 Service 方法
✅ 優化錯誤處理
✅ 統一入口函數
✅ [FIX] tenant_name → name, base_rent → rent (對齊 tenant_service v5.3)
✅ [FIX v3.2] use_container_width → width="stretch" (移除棄用警告)
✅ [FIX v3.3] st.progress Decimal 型別錯誤修正 (Decimal → float)
"""
import streamlit as st
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from services.payment_service import PaymentService
from services.tenant_service import TenantService
from typing import List, Dict
import pandas as pd
import logging

logger = logging.getLogger(__name__)


# ============================================
# 輔助函數
# ============================================

def safe_float(value) -> float:
    """
    安全將任何數值型別轉換為 float。
    修正 Supabase 回傳 Decimal 導致 st.progress / st.metric 崩潰的問題。
    """
    if value is None:
        return 0.0
    if isinstance(value, float):
        return value
    if isinstance(value, (int, Decimal)):
        return float(value)
    try:
        return float(str(value).replace(',', '').replace('$', '').strip())
    except (ValueError, TypeError):
        logger.warning(f"safe_float: 無法轉換 {value!r}，回傳 0.0")
        return 0.0


# ============================================
# 主入口
# ============================================
def render():
    """主入口函式（供 main.py 動態載入使用）"""
    render_rent_page()


def show():
    """Streamlit 頁面入口"""
    render()


def render_rent_page():
    """渲染租金管理主頁面"""
    st.title("💰 租金管理")

    # ✅ 初始化 Services
    payment_service = PaymentService()
    tenant_service = TenantService()

    tab1, tab2, tab3, tab4 = st.tabs([
        "📅 批量建立排程",
        "📊 本月摘要",
        "💳 收款管理",
        "📈 報表分析"
    ])

    with tab1:
        render_batch_schedule_tab(payment_service, tenant_service)
    with tab2:
        render_monthly_summary_tab(payment_service, tenant_service)
    with tab3:
        render_payment_management_tab(payment_service, tenant_service)
    with tab4:
        render_reports_tab(payment_service, tenant_service)


# ==================== Tab 1: 批量建立排程 ====================
def render_batch_schedule_tab(payment_service: PaymentService, tenant_service: TenantService):
    """批量建立排程頁籤 v3.2"""

    st.subheader("📅 批量建立月租金排程 v3.2")
    st.caption("💡 選擇特定房間，一次建立多個月份的租金記錄")

    st.divider()

    # === 載入房客資料 ===
    try:
        tenants = tenant_service.get_all_tenants()

        if not tenants:
            st.warning("⚠️ 尚無房客資料，請先前往「👥 房客管理」新增房客")
            return

        # 按房號分組
        tenants_by_room = {t['room_number']: t for t in tenants}
        room_list = sorted(tenants_by_room.keys())

    except Exception as e:
        st.error(f"❌ 載入房客資料失敗: {str(e)}")
        logger.error(f"載入房客資料錯誤: {str(e)}", exc_info=True)
        return

    # === 選擇模式 ===
    st.markdown("### 🎯 選擇建立模式")

    col_mode1, col_mode2 = st.columns(2)

    with col_mode1:
        mode_all = st.button(
            "🏘️ 全部房間",
            width="stretch",
            help="為所有現有房客建立租金記錄"
        )

    with col_mode2:
        mode_select = st.button(
            "🏠 選擇房間",
            width="stretch",
            type="primary",
            help="選擇特定房間建立租金記錄"
        )

    if 'batch_mode' not in st.session_state:
        st.session_state.batch_mode = 'select'

    if mode_all:
        st.session_state.batch_mode = 'all'
        st.rerun()

    if mode_select:
        st.session_state.batch_mode = 'select'
        st.rerun()

    st.divider()

    # === 房間選擇 ===
    selected_rooms = []

    if st.session_state.batch_mode == 'select':
        st.markdown("### 🏠 選擇房間")

        selected_rooms = st.multiselect(
            "請選擇要建立租金記錄的房間（可多選）",
            options=room_list,
            default=[],
            format_func=lambda x: (
                f"{x} - "
                f"{tenants_by_room[x].get('name', '未知')} "
                f"(NT${tenants_by_room[x].get('rent', 0):,.0f}/月)"
            ),
            key="selected_rooms_for_batch"
        )

        if not selected_rooms:
            st.info("👆 請先選擇至少一個房間")
            return

        # 顯示選中的房客資訊
        st.caption("**已選擇：**")
        num_cols = min(len(selected_rooms), 4)
        cols = st.columns(num_cols)

        for idx, room in enumerate(selected_rooms):
            tenant = tenants_by_room[room]
            with cols[idx % num_cols]:
                st.metric(
                    label=f"房間 {room}",
                    value=f"NT${tenant.get('rent', 0):,.0f}",
                    delta=tenant.get('name', '未知')
                )

        st.divider()

    else:
        selected_rooms = room_list
        st.info(f"📊 將為 **{len(selected_rooms)}** 個房間建立租金記錄")
        st.divider()

    # === 設定時間範圍 ===
    st.markdown("### 📅 設定時間範圍")

    col1, col2 = st.columns([2, 2])

    with col1:
        start_year = st.number_input(
            "起始年份",
            min_value=2020,
            max_value=2030,
            value=date.today().year,
            step=1,
            key="batch_start_year"
        )

    with col2:
        start_month = st.selectbox(
            "起始月份",
            range(1, 13),
            index=date.today().month - 1,
            key="batch_start_month"
        )

    st.divider()

    # === 批量建立月份數 ===
    st.markdown("### 🗓️ 批量建立月份數")

    col_month1, col_month2 = st.columns([3, 1])

    with col_month1:
        num_months = st.slider(
            "一次建立幾個月？",
            min_value=1,
            max_value=12,
            value=1,
            help="例如：選擇 3，則會建立連續 3 個月的租金記錄",
            key="batch_num_months"
        )

    with col_month2:
        st.write("")
        st.write("")
        st.metric("建立月數", f"{num_months} 個月")

    # 計算月份範圍
    start_date = date(start_year, start_month, 1)
    month_range = []

    for i in range(num_months):
        target_date = start_date + relativedelta(months=i)
        month_range.append({
            'year': target_date.year,
            'month': target_date.month,
            'display': f"{target_date.year}/{target_date.month:02d}"
        })

    st.caption("**將建立以下月份：**")
    month_display = " → ".join([m['display'] for m in month_range])
    st.info(f"📅 {month_display}")

    st.divider()

    # === 預覽建立項目 ===
    st.markdown("### 👀 預覽建立項目")

    total_records = len(selected_rooms) * num_months

    st.metric(
        label="預計建立記錄",
        value=f"{total_records} 筆",
        delta=f"{len(selected_rooms)} 房間 × {num_months} 月"
    )

    with st.expander("📋 查看詳細明細", expanded=False):
        preview_data = []

        for room in selected_rooms:
            tenant = tenants_by_room[room]

            for month_info in month_range:
                preview_data.append({
                    '房號': room,
                    '房客': tenant.get('name', '未知'),
                    '年份': month_info['year'],
                    '月份': f"{month_info['month']:02d}",
                    '租金': f"NT${tenant.get('rent', 0):,.0f}"
                })

        st.dataframe(
            preview_data,
            width="stretch",
            hide_index=True
        )

    st.divider()

    # === 建立按鈕 ===
    col_btn1, col_btn2 = st.columns([3, 1])

    with col_btn1:
        if st.button(
            f"🚀 一鍵建立排程（{total_records} 筆）",
            type="primary",
            width="stretch",
            key="batch_create_btn"
        ):
            with st.spinner("正在建立租金記錄..."):
                try:
                    success_count = 0
                    fail_count = 0
                    skip_count = 0
                    error_messages = []

                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    total_items = len(selected_rooms) * num_months
                    current = 0

                    for room in selected_rooms:
                        for month_info in month_range:
                            current += 1
                            progress = current / total_items
                            progress_bar.progress(progress)
                            status_text.text(
                                f"處理中... {current}/{total_items} ({room} - {month_info['display']})"
                            )

                            try:
                                ok, msg = payment_service.create_monthly_schedule(
                                    room_number=room,
                                    year=month_info['year'],
                                    month=month_info['month']
                                )

                                if ok:
                                    if "已存在" in msg:
                                        skip_count += 1
                                    else:
                                        success_count += 1
                                else:
                                    fail_count += 1
                                    error_messages.append(
                                        f"{room} ({month_info['display']}): {msg}"
                                    )

                            except Exception as e:
                                fail_count += 1
                                error_messages.append(
                                    f"{room} ({month_info['display']}): {str(e)}"
                                )
                                logger.error(
                                    f"建立排程失敗: {room} - {month_info['display']}: {str(e)}",
                                    exc_info=True
                                )

                    progress_bar.progress(1.0)
                    status_text.text("✅ 完成！")

                    st.divider()

                    col_r1, col_r2, col_r3 = st.columns(3)
                    with col_r1:
                        st.metric("✅ 成功建立", f"{success_count} 筆")
                    with col_r2:
                        st.metric("⏭️ 已存在（跳過）", f"{skip_count} 筆")
                    with col_r3:
                        st.metric("❌ 失敗", f"{fail_count} 筆")

                    if success_count > 0:
                        st.success(f"🎉 成功建立 {success_count} 筆租金記錄！")
                        logger.info(f"批量建立租金記錄成功: {success_count} 筆")

                    if skip_count > 0:
                        st.info(f"⏭️ 跳過 {skip_count} 筆已存在的記錄")

                    if fail_count > 0:
                        st.error(f"❌ {fail_count} 筆建立失敗")
                        with st.expander("查看錯誤詳情"):
                            for msg in error_messages:
                                st.text(f"• {msg}")
                        logger.error(f"批量建立租金記錄部分失敗: {fail_count} 筆")

                except Exception as e:
                    st.error(f"❌ 批量建立失敗: {str(e)}")
                    logger.error(f"批量建立租金記錄異常: {str(e)}", exc_info=True)

    with col_btn2:
        if st.button(
            "🔄 重置",
            width="stretch"
        ):
            if 'selected_rooms_for_batch' in st.session_state:
                del st.session_state['selected_rooms_for_batch']
            st.session_state.batch_mode = 'select'
            st.rerun()


# ==================== Tab 2: 本月摘要 ====================
def render_monthly_summary_tab(payment_service: PaymentService, tenant_service: TenantService):
    """本月摘要頁籤"""
    st.subheader("📊 本月租金收款摘要")

    col1, col2, col3 = st.columns([2, 2, 3])

    with col1:
        year = st.selectbox(
            "年份", range(2020, 2031),
            index=date.today().year - 2020,
            key="summary_year"
        )

    with col2:
        month = st.selectbox(
            "月份", range(1, 13),
            index=date.today().month - 1,
            key="summary_month"
        )

    with col3:
        try:
            tenants = tenant_service.get_all_tenants()
            room_list = sorted(set([t['room_number'] for t in tenants]))
            selected_room = st.selectbox(
                "🏠 房號篩選",
                options=["全部"] + room_list,
                key="monthly_room_filter"
            )
        except Exception as e:
            st.error(f"❌ 載入房間列表失敗: {str(e)}")
            selected_room = "全部"

    try:
        if selected_room == "全部":
            summary = payment_service.get_monthly_summary(year, month)
            payments = payment_service.get_payments_by_period(year, month)
        else:
            payments = payment_service.get_room_payments(selected_room, year, month)
            df_tmp = pd.DataFrame(payments) if payments else pd.DataFrame()
            if not df_tmp.empty:
                # ✅ [FIX v3.3] 全部轉 float，避免 Decimal 在 st.progress / metric delta 崩潰
                total_expected = safe_float(df_tmp['amount'].sum())
                paid_df = df_tmp[df_tmp['status'] == 'paid']
                total_received = safe_float(
                    paid_df['paid_amount'].sum()
                    if not paid_df.empty and 'paid_amount' in paid_df.columns
                    else 0
                )
                unpaid_count  = int(len(df_tmp[df_tmp['status'] == 'unpaid']))
                overdue_count = int(len(df_tmp[df_tmp['status'] == 'overdue']))
                collection_rate = total_received / total_expected if total_expected > 0 else 0.0
                summary = {
                    'total_expected':  total_expected,
                    'total_received':  total_received,
                    'unpaid_count':    unpaid_count,
                    'overdue_count':   overdue_count,
                    'collection_rate': collection_rate,  # 已是 float
                }
            else:
                summary = {
                    'total_expected': 0.0, 'total_received': 0.0,
                    'unpaid_count': 0, 'overdue_count': 0, 'collection_rate': 0.0
                }

        # === 指標卡片 ===
        _s = lambda k: summary[k] if isinstance(summary, dict) else getattr(summary, k)

        # ✅ [FIX v3.3] 所有數值先過 safe_float，統一型別
        total_expected  = safe_float(_s('total_expected'))
        total_received  = safe_float(_s('total_received'))
        unpaid_count    = int(_s('unpaid_count')  or 0)
        overdue_count   = int(_s('overdue_count') or 0)
        cr              = safe_float(_s('collection_rate'))   # ← 關鍵：確保是 float

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("應收總額", f"NT${total_expected:,.0f}", help="本月應繳租金總額")
        with col2:
            st.metric(
                "實收總額",
                f"NT${total_received:,.0f}",
                delta=f"{cr:.1%}",
                help="已收到的租金金額與收款率"
            )
        with col3:
            st.metric("待收", f"{unpaid_count} 筆", help="尚未繳款的租金記錄數")
        with col4:
            st.metric(
                "逾期", f"{overdue_count} 筆",
                delta="-" if overdue_count > 0 else "正常",
                delta_color="inverse"
            )

        # ✅ [FIX v3.3] st.progress 只接受 float，min() 的兩個參數也須是 float
        st.progress(min(cr, 1.0))
        st.caption(f"收款進度：{cr:.1%}")

        st.divider()

        # === 詳細列表 ===
        title = "📋 本月繳費明細" if selected_room == "全部" else f"📋 {selected_room} 房繳費明細"
        st.subheader(title)

        if not payments:
            st.info("📭 本月尚無租金記錄")
            return

        df = pd.DataFrame(payments)

        if 'due_date' in df.columns:
            df['due_date'] = pd.to_datetime(df['due_date']).dt.strftime('%Y-%m-%d')
        if 'paid_date' in df.columns:
            df['paid_date'] = pd.to_datetime(df['paid_date'], errors='coerce').dt.strftime('%Y-%m-%d')

        status_map = {'unpaid': '⏳ 未繳', 'paid': '✅ 已繳', 'overdue': '🚨 逾期'}
        df['status_display'] = df['status'].map(status_map).fillna(df['status'])

        display_cols = ['room_number', 'tenant_name', 'amount', 'due_date', 'status_display']
        if 'payment_method' in df.columns:
            display_cols.append('payment_method')
        available_cols = [c for c in display_cols if c in df.columns]

        rename_map = {
            'room_number': '房號', 'tenant_name': '房客',
            'amount': '應繳金額', 'due_date': '到期日',
            'status_display': '狀態', 'payment_method': '繳款方式'
        }
        st.dataframe(
            df[available_cols].rename(columns=rename_map),
            width="stretch",
            hide_index=True
        )

        # === 標記功能 ===
        unpaid_df = df[df['status'] == 'unpaid']

        if not unpaid_df.empty:
            st.divider()
            hdr = '批量標記已繳' if selected_room == '全部' else f'{selected_room} 房標記已繳'
            st.subheader(f"✅ {hdr}")

            col1, col2 = st.columns([3, 1])

            with col1:
                selected_ids = st.multiselect(
                    "選擇要標記為已繳的項目（可多選）",
                    options=unpaid_df['id'].tolist(),
                    format_func=lambda x: (
                        f"{unpaid_df[unpaid_df['id']==x]['room_number'].values[0]} - "
                        f"{unpaid_df[unpaid_df['id']==x].get('tenant_name', unpaid_df[unpaid_df['id']==x].get('room_number', '')).values[0]} "
                        f"(NT${unpaid_df[unpaid_df['id']==x]['amount'].values[0]:,.0f})"
                    ),
                    key="monthly_multiselect"
                )

            with col2:
                st.write("")
                st.write("")
                if st.button(
                    f"✅ 標記 ({len(selected_ids)})",
                    type="primary",
                    disabled=len(selected_ids) == 0,
                    width="stretch",
                    key="monthly_mark_paid"
                ):
                    with st.spinner("處理中..."):
                        try:
                            results = payment_service.batch_mark_paid(selected_ids)
                            if results['success'] > 0:
                                st.success(f"✅ 成功標記 {results['success']} 筆")
                                st.rerun()
                            if results['failed'] > 0:
                                st.error(f"❌ 失敗 {results['failed']} 筆")
                        except Exception as e:
                            st.error(f"❌ 標記失敗: {str(e)}")
                            logger.error(f"批量標記失敗: {str(e)}", exc_info=True)

    except Exception as e:
        st.error(f"❌ 載入摘要失敗: {str(e)}")
        logger.error(f"載入摘要錯誤: {str(e)}", exc_info=True)


# ==================== Tab 3: 收款管理 ====================
def render_payment_management_tab(payment_service: PaymentService, tenant_service: TenantService):
    """收款管理頁籤"""
    st.subheader("💳 收款管理")

    col1, col2 = st.columns([3, 3])

    with col1:
        status_filter = st.radio(
            "篩選狀態",
            ["全部", "未繳", "已繳", "逾期"],
            horizontal=True
        )

    with col2:
        try:
            tenants = tenant_service.get_all_tenants()
            room_list = sorted(set([t['room_number'] for t in tenants]))
            selected_room = st.selectbox(
                "🏠 房號篩選",
                options=["全部"] + room_list,
                key="management_room_filter"
            )
        except Exception as e:
            st.error(f"❌ 載入房間列表失敗: {str(e)}")
            selected_room = "全部"

    try:
        if status_filter == "未繳":
            payments = payment_service.get_unpaid_payments()
        elif status_filter == "逾期":
            payments = payment_service.get_overdue_payments()
        elif status_filter == "已繳":
            payments = payment_service.get_paid_payments()
        else:
            payments = payment_service.get_all_payments()

        if selected_room != "全部":
            payments = [p for p in payments if p['room_number'] == selected_room]

        if not payments:
            st.info("✅ 沒有符合條件的記錄")
            return

        df = pd.DataFrame(payments)
        if 'due_date' in df.columns:
            df['due_date'] = pd.to_datetime(df['due_date']).dt.strftime('%Y-%m-%d')

        status_map = {'unpaid': '⏳ 未繳', 'paid': '✅ 已繳', 'overdue': '🚨 逾期'}
        df['status_display'] = df['status'].map(status_map).fillna(df['status'])

        display_cols = [
            'room_number', 'tenant_name', 'payment_year',
            'payment_month', 'amount', 'due_date', 'status_display'
        ]
        available_cols = [c for c in display_cols if c in df.columns]

        rename_map = {
            'room_number': '房號', 'tenant_name': '房客',
            'payment_year': '年份', 'payment_month': '月份',
            'amount': '金額', 'due_date': '到期日', 'status_display': '狀態'
        }
        st.dataframe(
            df[available_cols].rename(columns=rename_map),
            width="stretch",
            hide_index=True
        )

        if status_filter in ["未繳", "逾期"]:
            st.divider()
            st.subheader("✅ 批量標記已繳")

            col1, col2 = st.columns([3, 1])

            with col1:
                selected_ids = st.multiselect(
                    "選擇要標記的記錄（可多選）",
                    options=df['id'].tolist(),
                    format_func=lambda x: (
                        f"{df[df['id']==x]['room_number'].values[0]} - "
                        f"{df[df['id']==x]['payment_year'].values[0]}/"
                        f"{df[df['id']==x]['payment_month'].values[0]:02d}"
                    ),
                    key="management_multiselect"
                )

            with col2:
                st.write("")
                st.write("")
                if st.button(
                    f"✅ 標記 ({len(selected_ids)})",
                    type="primary",
                    disabled=len(selected_ids) == 0,
                    width="stretch"
                ):
                    with st.spinner("處理中..."):
                        try:
                            results = payment_service.batch_mark_paid(selected_ids)
                            st.success(
                                f"✅ 完成！成功 {results['success']} 筆，失敗 {results['failed']} 筆"
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ 標記失敗: {str(e)}")
                            logger.error(f"批量標記失敗: {str(e)}", exc_info=True)

    except Exception as e:
        st.error(f"❌ 載入資料失敗: {str(e)}")
        logger.error(f"收款管理錯誤: {str(e)}", exc_info=True)


# ==================== Tab 4: 報表分析 ====================
def render_reports_tab(payment_service: PaymentService, tenant_service: TenantService):
    """報表分析頁籤"""
    st.subheader("📈 報表分析")

    report_type = st.selectbox(
        "報表類型",
        ["月度收款趨勢", "房客繳款歷史", "年度統計"]
    )

    if report_type == "月度收款趨勢":
        render_monthly_trend_report(payment_service)
    elif report_type == "房客繳款歷史":
        render_tenant_history_report(payment_service, tenant_service)
    elif report_type == "年度統計":
        render_annual_report(payment_service)


def render_monthly_trend_report(payment_service: PaymentService):
    """月度趨勢報表"""
    st.info("🚧 月度趨勢報表開發中...")


def render_tenant_history_report(payment_service: PaymentService, tenant_service: TenantService):
    """房客繳款歷史"""
    try:
        tenants = tenant_service.get_all_tenants()

        if not tenants:
            st.warning("沒有活躍房客")
            return

        tenant_options = {
            t['room_number']: f"{t['room_number']} - {t.get('name', '未知')}"
            for t in tenants
        }

        selected_room = st.selectbox(
            "選擇房客",
            options=list(tenant_options.keys()),
            format_func=lambda x: tenant_options[x]
        )

        history = payment_service.get_tenant_history(selected_room, limit=12)

        if history:
            df = pd.DataFrame(history)
            available_cols_list = [
                'payment_year', 'payment_month', 'amount',
                'status', 'paid_date', 'due_date'
            ]
            display_cols = [c for c in available_cols_list if c in df.columns]
            st.dataframe(
                df[display_cols],
                width="stretch",
                hide_index=True
            )
        else:
            st.info("此房客尚無繳款記錄")

    except Exception as e:
        st.error(f"❌ 載入失敗: {str(e)}")
        logger.error(f"房客歷史報表錯誤: {str(e)}", exc_info=True)


def render_annual_report(payment_service: PaymentService):
    """年度統計報表"""
    st.info("🚧 年度統計報表開發中...")


# ============================================
# 本機測試入口
# ============================================
if __name__ == "__main__":
    render_rent_page()
