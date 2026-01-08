"""
繳費追蹤 - 錯誤修復版
修復: KeyError - 動態檢查欄位是否存在
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import logging

# 安全 import
try:
    from components.cards import section_header, metric_card, empty_state, data_table, info_card
except ImportError:
    def section_header(title, icon="", divider=True):
        st.markdown(f"### {icon} {title}")
        if divider: st.divider()
    def metric_card(label, value, delta="", icon="", color="normal"):
        st.metric(label, value, delta)
    def empty_state(msg, icon="", desc=""):
        st.info(f"{icon} {msg}")
    def data_table(df, key="table"):
        st.dataframe(df, use_container_width=True, key=key)
    def info_card(title, content, icon="", type="info"):
        st.info(f"{icon} {title}: {content}")

try:
    from config.constants import ROOMS
except ImportError:
    class ROOMS:
        ALL_ROOMS = ["1A", "1B", "2A", "2B", "3A", "3B", "3C", "3D", "4A", "4B", "4C", "4D"]

logger = logging.getLogger(__name__)


def get_overdue_days(due_date) -> int:
    """計算逾期天數"""
    if pd.isna(due_date):
        return 0
    
    try:
        if isinstance(due_date, str):
            due_date = datetime.strptime(due_date, "%Y-%m-%d").date()
        elif isinstance(due_date, datetime):
            due_date = due_date.date()
        
        today = date.today()
        delta = (today - due_date).days
        return max(0, delta)
    except:
        return 0


def categorize_payment_status(row) -> str:
    """分類繳費狀態"""
    if row.get('status') == '已繳':
        return '已繳'
    
    overdue_days = get_overdue_days(row.get('due_date'))
    
    if overdue_days > 7:
        return '逾期未繳'
    elif overdue_days > 0:
        return '即將逾期'
    else:
        return '未到期'


def render(db):
    """主渲染函數"""
    st.title("📋 繳費追蹤")
    
    # === 篩選區域 ===
    section_header("篩選條件", "🔍")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        filter_year = st.selectbox(
            "年份",
            [None] + list(range(2020, 2031)),
            format_func=lambda x: "全部" if x is None else str(x),
            index=date.today().year - 2020 + 1 if date.today().year >= 2020 else 0,
            key="track_year"
        )
    
    with col2:
        filter_month = st.selectbox(
            "月份",
            [None] + list(range(1, 13)),
            format_func=lambda x: "全部" if x is None else str(x),
            key="track_month"
        )
    
    with col3:
        filter_status = st.selectbox(
            "狀態",
            [None, "未繳", "已繳"],
            format_func=lambda x: "全部" if x is None else x,
            key="track_status"
        )
    
    with col4:
        filter_rooms = st.multiselect(
            "房號",
            ROOMS.ALL_ROOMS,
            key="track_rooms"
        )
    
    st.divider()
    
    # === 查詢資料 ===
    try:
        df = db.get_payment_schedule(
            year=filter_year,
            month=filter_month,
            status=filter_status
        )
    except Exception as e:
        st.error(f"❌ 查詢失敗: {e}")
        return
    
    if df.empty:
        empty_state("沒有符合條件的記錄", "📭")
        return
    
    # 應用房號篩選
    if filter_rooms and 'room_number' in df.columns:
        df = df[df['room_number'].isin(filter_rooms)]
    
    # 計算逾期天數
    df['逾期天數'] = df.apply(lambda row: get_overdue_days(row.get('due_date')), axis=1)
    
    # 分類狀態
    df['狀態分類'] = df.apply(categorize_payment_status, axis=1)
    
    if df.empty:
        empty_state("沒有符合條件的記錄", "📭")
        return
    
    # === 統計卡片 ===
    section_header("統計概覽", "📊")
    
    total_count = len(df)
    unpaid_df = df[df['status'] == '未繳'] if 'status' in df.columns else pd.DataFrame()
    paid_df = df[df['status'] == '已繳'] if 'status' in df.columns else pd.DataFrame()
    overdue_df = df[(df['status'] == '未繳') & (df['逾期天數'] > 0)] if 'status' in df.columns else pd.DataFrame()
    
    col_s1, col_s2, col_s3, col_s4, col_s5 = st.columns(5)
    
    with col_s1:
        metric_card("總筆數", str(total_count), icon="📋", color="normal")
    
    with col_s2:
        paid_amount = paid_df['paid_amount'].sum() if 'paid_amount' in paid_df.columns else 0
        metric_card("已繳", str(len(paid_df)), f"${paid_amount:,.0f}", "✅", "success")
    
    with col_s3:
        unpaid_amount = unpaid_df['amount'].sum() if 'amount' in unpaid_df.columns else 0
        metric_card("未繳", str(len(unpaid_df)), f"${unpaid_amount:,.0f}", "⏳", "warning")
    
    with col_s4:
        overdue_amount = overdue_df['amount'].sum() if 'amount' in overdue_df.columns else 0
        metric_card("逾期", str(len(overdue_df)), f"${overdue_amount:,.0f}", "🚨", "error")
    
    with col_s5:
        payment_rate = (len(paid_df) / total_count * 100) if total_count > 0 else 0
        metric_card("收款率", f"{payment_rate:.1f}%", icon="📊", color="normal")
    
    st.divider()
    
    # === 逾期警示 ===
    if not overdue_df.empty:
        st.error(f"🚨 **逾期警示**: {len(overdue_df)} 筆未繳且已逾期")
        
        with st.expander("查看逾期明細", expanded=True):
            for _, row in overdue_df.head(5).iterrows():
                room = row.get('room_number', 'N/A')
                tenant = row.get('tenant_name', 'N/A')
                year = row.get('payment_year', 'N/A')
                month = row.get('payment_month', 'N/A')
                amount = row.get('amount', 0)
                days = row.get('逾期天數', 0)
                
                st.write(f"**{room}** {tenant} | {year}/{month} | ${amount:,} | 逾期 {days} 天")
            
            if len(overdue_df) > 5:
                st.caption(f"... 還有 {len(overdue_df) - 5} 筆")
        
        st.divider()
    
    # === 批量操作 ===
    if not unpaid_df.empty:
        section_header("批量操作", "⚡")
        
        # 快速篩選按鈕
        col_q1, col_q2, col_q3, col_q4 = st.columns(4)
        
        with col_q1:
            if st.button("🔴 選擇所有逾期"):
                st.session_state.selected_tracking = overdue_df['id'].tolist() if 'id' in overdue_df.columns else []
                st.rerun()
        
        with col_q2:
            if st.button("🟡 選擇即將逾期"):
                soon_overdue = df[df['狀態分類'] == '即將逾期']['id'].tolist() if 'id' in df.columns else []
                st.session_state.selected_tracking = soon_overdue
                st.rerun()
        
        with col_q3:
            if st.button("🟢 選擇全部未繳"):
                st.session_state.selected_tracking = unpaid_df['id'].tolist() if 'id' in unpaid_df.columns else []
                st.rerun()
        
        with col_q4:
            if st.button("🔄 清除選擇"):
                st.session_state.selected_tracking = []
                st.rerun()
        
        # 手動選擇
        if 'selected_tracking' not in st.session_state:
            st.session_state.selected_tracking = []
        
        if 'id' in unpaid_df.columns:
            selected_ids = st.multiselect(
                "或手動選擇要標記的項目",
                unpaid_df['id'].tolist(),
                default=st.session_state.selected_tracking,
                format_func=lambda x: f"{unpaid_df[unpaid_df['id']==x]['room_number'].values[0] if 'room_number' in unpaid_df.columns else 'N/A'} - {unpaid_df[unpaid_df['id']==x]['payment_year'].values[0] if 'payment_year' in unpaid_df.columns else 'N/A'}/{unpaid_df[unpaid_df['id']==x]['payment_month'].values[0] if 'payment_month' in unpaid_df.columns else 'N/A'} (${unpaid_df[unpaid_df['id']==x]['amount'].values[0] if 'amount' in unpaid_df.columns else 0:,.0f})",
                key="manual_select"
            )
            
            st.session_state.selected_tracking = selected_ids
            
            if st.button(f"✅ 標記已繳 ({len(selected_ids)})", type="primary", disabled=len(selected_ids) == 0):
                try:
                    success, fail = db.batch_mark_paid(selected_ids)
                    
                    if success > 0:
                        st.success(f"✅ 成功標記 {success} 筆")
                        st.session_state.selected_tracking = []
                        st.rerun()
                    
                    if fail > 0:
                        st.error(f"❌ 失敗 {fail} 筆")
                except Exception as e:
                    st.error(f"❌ 批量標記失敗: {e}")
        
        st.divider()
    
    # === 資料表格 ===
    section_header("詳細列表", "📋")
    
    st.write(f"共 {len(df)} 筆記錄")
    
    # 格式化顯示
    display_df = df.copy()
    
    # 安全處理欄位
    if 'payment_year' in display_df.columns and 'payment_month' in display_df.columns:
        display_df['期間'] = display_df.apply(
            lambda x: f"{x['payment_year']}/{x['payment_month']}", axis=1
        )
    
    if 'amount' in display_df.columns:
        display_df['應收金額'] = display_df['amount'].apply(lambda x: f"${x:,.0f}")
    
    if 'paid_amount' in display_df.columns:
        display_df['實收金額'] = display_df['paid_amount'].apply(lambda x: f"${x:,.0f}")
    
    # 狀態標記
    def status_with_icon(row):
        status = row.get('status', 'N/A')
        overdue = row.get('逾期天數', 0)
        
        if status == '已繳':
            return '✅ 已繳'
        elif overdue > 7:
            return f'🚨 逾期 {overdue} 天'
        elif overdue > 0:
            return f'🟡 逾期 {overdue} 天'
        else:
            return '⏳ 未繳'
    
    display_df['狀態標記'] = display_df.apply(status_with_icon, axis=1)
    
    # 到期日格式化
    if 'due_date' in display_df.columns:
        display_df['到期日'] = pd.to_datetime(display_df['due_date'], errors='coerce').dt.strftime('%Y-%m-%d')
    
    # 選擇要顯示的欄位（動態檢查）
    available_cols = display_df.columns.tolist()
    preferred_cols = ['id', 'room_number', 'tenant_name', '期間', '應收金額', '實收金額', 'payment_method', '到期日', '狀態標記']
    
    cols_to_show = [col for col in preferred_cols if col in available_cols]
    
    rename_cols = {
        'room_number': '房號',
        'tenant_name': '房客',
        'payment_method': '繳款方式'
    }
    
    display_df = display_df.rename(columns=rename_cols)
    
    # 更新 cols_to_show 以反映重命名
    final_cols = []
    for col in cols_to_show:
        if col in rename_cols:
            final_cols.append(rename_cols[col])
        else:
            final_cols.append(col)
    
    # 確保所有欄位都存在
    final_cols = [col for col in final_cols if col in display_df.columns]
    
    # 顯示表格
    if final_cols:
        st.dataframe(display_df[final_cols], use_container_width=True, hide_index=True, key="tracking_table")
    else:
        st.warning("⚠️ 無法顯示資料表格，請檢查資料格式")
    
    # 匯出功能
    st.divider()
    section_header("匯出資料", "📥", divider=False)
    
    csv = df.to_csv(index=False, encoding='utf-8-sig')
    
    st.download_button(
        "📥 下載 CSV",
        csv,
        f"tracking_{datetime.now().strftime('%Y%m%d')}.csv",
        "text/csv"
    )
