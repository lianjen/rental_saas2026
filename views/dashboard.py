"""
儀表板 - 重構版
特性:
- 錯誤邊界處理
- 效能優化 (快取)
- 動態房間數
- 統一日期處理
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional
import sys
sys.path.append('..')

from components.cards import (
    section_header, metric_card, room_status_card, 
    empty_state, info_card, status_badge
)
from config.constants import ROOMS, UI


def safe_parse_date(date_value) -> Optional[date]:
    """
    安全解析日期
    
    Args:
        date_value: 日期值 (可能是 str, date, datetime, None)
    
    Returns:
        date 物件或 None
    """
    if date_value is None:
        return None
    
    if isinstance(date_value, date):
        return date_value
    
    if isinstance(date_value, datetime):
        return date_value.date()
    
    try:
        return datetime.strptime(str(date_value), "%Y-%m-%d").date()
    except (ValueError, TypeError) as e:
        st.warning(f"⚠️ 日期格式錯誤: {date_value}")
        return None


@st.cache_data(ttl=300)  # 快取 5 分鐘
def calculate_metrics(df_tenants: pd.DataFrame, df_overdue: pd.DataFrame) -> Dict:
    """
    計算關鍵指標
    
    Args:
        df_tenants: 房客資料
        df_overdue: 逾期資料
    
    Returns:
        指標字典
    """
    total_rooms = len(ROOMS.ALL_ROOMS)
    occupied = len(df_tenants) if not df_tenants.empty else 0
    vacant = total_rooms - occupied
    occupancy_rate = round((occupied / total_rooms) * 100, 1) if total_rooms > 0 else 0
    
    # 計算逾期金額
    overdue_amount = df_overdue['amount'].sum() if not df_overdue.empty else 0
    overdue_count = len(df_overdue) if not df_overdue.empty else 0
    
    return {
        'total_rooms': total_rooms,
        'occupied': occupied,
        'vacant': vacant,
        'occupancy_rate': occupancy_rate,
        'overdue_amount': overdue_amount,
        'overdue_count': overdue_count
    }


def get_expiring_leases(df_tenants: pd.DataFrame, days: int = 45) -> List[Dict]:
    """
    取得即將到期的租約
    
    Args:
        df_tenants: 房客資料
        days: 提前幾天警示
    
    Returns:
        即將到期的租約列表
    """
    if df_tenants.empty:
        return []
    
    expiring = []
    today = date.today()
    warning_date = today + timedelta(days=days)
    
    for _, tenant in df_tenants.iterrows():
        lease_end = safe_parse_date(tenant.get('lease_end'))
        
        if lease_end and today <= lease_end <= warning_date:
            days_left = (lease_end - today).days
            expiring.append({
                'room': tenant['room_number'],
                'tenant': tenant['tenant_name'],
                'lease_end': lease_end,
                'days_left': days_left
            })
    
    return sorted(expiring, key=lambda x: x['days_left'])


def render_kpi_section(metrics: Dict):
    """渲染 KPI 區塊"""
    section_header("📊 關鍵指標", divider=True)
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        metric_card(
            "佔用率",
            f"{metrics['occupancy_rate']}%",
            f"{metrics['occupied']}/{metrics['total_rooms']} 房",
            "🏠",
            "success" if metrics['occupancy_rate'] >= 80 else "warning"
        )
    
    with col2:
        metric_card(
            "空房數",
            str(metrics['vacant']),
            "可出租",
            "🔓",
            "normal" if metrics['vacant'] > 0 else "success"
        )
    
    with col3:
        color = "error" if metrics['overdue_count'] > 0 else "success"
        metric_card(
            "逾期未繳",
            str(metrics['overdue_count']),
            f"金額: ${metrics['overdue_amount']:,.0f}",
            "⚠️",
            color
        )
    
    with col4:
        metric_card(
            "總房間數",
            str(metrics['total_rooms']),
            "管理中",
            "🏢",
            "normal"
        )


def render_lease_alerts(expiring_leases: List[Dict]):
    """渲染租約警示"""
    section_header("⏰ 租約到期警示", divider=True)
    
    if not expiring_leases:
        info_card(
            "✅ 無即將到期租約",
            "45 天內沒有租約到期，一切正常！",
            "✅",
            "success"
        )
        return
    
    # 分類警示
    urgent = [l for l in expiring_leases if l['days_left'] <= 14]
    warning = [l for l in expiring_leases if 14 < l['days_left'] <= 30]
    notice = [l for l in expiring_leases if l['days_left'] > 30]
    
    if urgent:
        st.error(f"🚨 緊急: {len(urgent)} 個租約 14 天內到期")
        for lease in urgent:
            st.markdown(
                f"**{lease['room']}** - {lease['tenant']} | "
                f"到期日: {lease['lease_end']} | "
                f"{status_badge(f'{lease["days_left"]} 天', 'error')}",
                unsafe_allow_html=True
            )
    
    if warning:
        st.warning(f"⚠️ 注意: {len(warning)} 個租約 30 天內到期")
        for lease in warning:
            st.markdown(
                f"**{lease['room']}** - {lease['tenant']} | "
                f"到期日: {lease['lease_end']} | "
                f"{status_badge(f'{lease["days_left"]} 天', 'warning')}",
                unsafe_allow_html=True
            )
    
    if notice:
        st.info(f"ℹ️ 提醒: {len(notice)} 個租約 45 天內到期")
        with st.expander("查看詳情"):
            for lease in notice:
                st.markdown(
                    f"**{lease['room']}** - {lease['tenant']} | "
                    f"到期日: {lease['lease_end']} | "
                    f"{status_badge(f'{lease["days_left"]} 天', 'info')}",
                    unsafe_allow_html=True
                )


def render_room_status(df_tenants: pd.DataFrame):
    """渲染房間狀態"""
    section_header("🏠 房間狀態一覽", divider=True)
    
    # 建立房間狀態字典
    room_status = {}
    today = date.today()
    warning_date = today + timedelta(days=45)
    
    for _, tenant in df_tenants.iterrows():
        room = tenant['room_number']
        lease_end = safe_parse_date(tenant.get('lease_end'))
        
        # 判斷狀態
        if lease_end and lease_end <= warning_date:
            status = 'warning'
        else:
            status = 'occupied'
        
        room_status[room] = {
            'tenant': tenant['tenant_name'],
            'status': status,
            'rent': tenant.get('base_rent', 0)
        }
    
    # 渲染房間卡片 (4 列 x 3 行)
    rows = [ROOMS.ALL_ROOMS[i:i+3] for i in range(0, len(ROOMS.ALL_ROOMS), 3)]
    
    for row_rooms in rows:
        cols = st.columns(3)
        for col, room in zip(cols, row_rooms):
            with col:
                room_info = room_status.get(room)
                
                if room_info:
                    room_status_card(
                        room,
                        room_info['tenant'],
                        room_info['status'],
                        room_info['rent']
                    )
                else:
                    room_status_card(room, None, 'vacant')


def render_memo_section(db):
    """渲染備忘錄區塊"""
    section_header("📝 待辦事項", divider=True)
    
    # 取得備忘錄
    memos = db.get_memos(include_completed=False)
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        new_memo = st.text_input(
            "新增待辦",
            placeholder="例如: 清洗冷氣 4A、檢查熱水器...",
            key="new_memo_input"
        )
    
    with col2:
        priority = st.selectbox(
            "優先級",
            ["normal", "high", "urgent"],
            format_func=lambda x: {"normal": "普通", "high": "重要", "urgent": "緊急"}[x],
            key="memo_priority"
        )
    
    if st.button("➕ 新增", key="add_memo_btn"):
        if new_memo.strip():
            if db.add_memo(new_memo, priority):
                st.success("✅ 已新增待辦事項")
                st.rerun()
            else:
                st.error("❌ 新增失敗")
        else:
            st.warning("⚠️ 請輸入待辦內容")
    
    st.divider()
    
    # 顯示待辦列表
    if not memos:
        empty_state(
            "目前沒有待辦事項",
            "✨",
            "一切都處理完畢了！"
        )
    else:
        for memo in memos:
            col1, col2, col3 = st.columns([1, 6, 1])
            
            with col1:
                priority_emoji = {
                    'urgent': '🔴',
                    'high': '🟡',
                    'normal': '⚪'
                }
                st.write(priority_emoji.get(memo['priority'], '⚪'))
            
            with col2:
                st.write(memo['memo_text'])
                st.caption(f"建立於: {memo['created_at']}")
            
            with col3:
                if st.button("✅", key=f"complete_{memo['id']}"):
                    if db.complete_memo(memo['id']):
                        st.rerun()


def render(db):
    """主渲染函數"""
    st.title(f"{UI.PAGE_ICON} 儀表板")
    
    # 載入資料
    with st.spinner("載入資料中..."):
        try:
            df_tenants = db.get_tenants()
            df_overdue = db.get_overdue_payments()
        except Exception as e:
            st.error(f"❌ 資料載入失敗: {str(e)}")
            return
    
    # 計算指標
    metrics = calculate_metrics(df_tenants, df_overdue)
    
    # 渲染各區塊
    render_kpi_section(metrics)
    
    st.divider()
    
    # 租約警示
    expiring_leases = get_expiring_leases(df_tenants)
    render_lease_alerts(expiring_leases)
    
    st.divider()
    
    # 房間狀態
    render_room_status(df_tenants)
    
    st.divider()
    
    # 備忘錄
    render_memo_section(db)