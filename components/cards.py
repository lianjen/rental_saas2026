"""
UI 元件庫 - 統一視覺風格
✅ [FIX v1.1] data_table: use_container_width → width="stretch" (移除棄用警告)
"""

import streamlit as st
from typing import Optional


def section_header(title: str, icon: str = "📌", divider: bool = True):
    """
    區段標題

    Args:
        title: 標題文字
        icon: 圖示 emoji
        divider: 是否顯示分隔線

    Usage:
        section_header("房客管理", "👥")
    """
    st.markdown(f"### {icon} {title}")
    if divider:
        st.divider()


def metric_card(label: str, value: str, delta: Optional[str] = None,
                icon: str = "📊", color: str = "normal"):
    """
    指標卡片

    Args:
        label: 標籤
        value: 數值
        delta: 變化量 (可選)
        icon: 圖示
        color: 顏色主題 ('normal', 'success', 'warning', 'error')
    """
    color_map = {
        'normal': '#1f77b4',
        'success': '#2ca02c',
        'warning': '#ff7f0e',
        'error': '#d62728'
    }

    bg_color = color_map.get(color, color_map['normal'])

    st.markdown(f"""
        <div style="
            background: linear-gradient(135deg, {bg_color}22 0%, {bg_color}11 100%);
            border-left: 4px solid {bg_color};
            padding: 1rem;
            border-radius: 8px;
            margin: 0.5rem 0;
        ">
            <div style="color: #666; font-size: 0.9rem; margin-bottom: 0.3rem;">
                {icon} {label}
            </div>
            <div style="font-size: 1.8rem; font-weight: bold; color: {bg_color};">
                {value}
            </div>
            {f'<div style="color: #888; font-size: 0.85rem; margin-top: 0.3rem;">{delta}</div>' if delta else ''}
        </div>
    """, unsafe_allow_html=True)


def status_badge(text: str, status: str = "default"):
    """
    狀態徽章

    Args:
        text: 顯示文字
        status: 'success', 'warning', 'error', 'info', 'default'
    """
    colors = {
        'success': ('#d4edda', '#155724'),
        'warning': ('#fff3cd', '#856404'),
        'error': ('#f8d7da', '#721c24'),
        'info': ('#d1ecf1', '#0c5460'),
        'default': ('#e2e3e5', '#383d41')
    }

    bg, fg = colors.get(status, colors['default'])

    return f"""
        <span style="
            background-color: {bg};
            color: {fg};
            padding: 0.25rem 0.6rem;
            border-radius: 12px;
            font-size: 0.85rem;
            font-weight: 500;
            display: inline-block;
        ">{text}</span>
    """


def info_card(title: str, content: str, icon: str = "ℹ️",
              type: str = "info"):
    """
    資訊卡片

    Args:
        title: 標題
        content: 內容
        icon: 圖示
        type: 'info', 'success', 'warning', 'error'
    """
    type_colors = {
        'info': ('#cfe2ff', '#084298'),
        'success': ('#d1e7dd', '#0f5132'),
        'warning': ('#fff3cd', '#664d03'),
        'error': ('#f8d7da', '#842029')
    }

    bg, border = type_colors.get(type, type_colors['info'])

    st.markdown(f"""
        <div style="
            background-color: {bg};
            border-left: 4px solid {border};
            padding: 1rem;
            border-radius: 6px;
            margin: 1rem 0;
        ">
            <div style="font-weight: 600; color: {border}; margin-bottom: 0.5rem;">
                {icon} {title}
            </div>
            <div style="color: #333; line-height: 1.5;">
                {content}
            </div>
        </div>
    """, unsafe_allow_html=True)


def room_status_card(room: str, tenant_name: Optional[str],
                     status: str, rent: Optional[float] = None):
    """
    房間狀態卡片

    Args:
        room: 房號
        tenant_name: 房客名稱
        status: 'occupied', 'vacant', 'warning'
        rent: 租金
    """
    status_config = {
        'occupied': ('🟢', '已出租', '#d4edda', '#155724'),
        'vacant': ('⚪', '空房', '#e2e3e5', '#6c757d'),
        'warning': ('🟡', '即將到期', '#fff3cd', '#856404')
    }

    icon, status_text, bg, border = status_config.get(status, status_config['vacant'])

    tenant_info = f"""
        <div style="font-size: 1rem; font-weight: 500; margin: 0.5rem 0;">
            {tenant_name}
        </div>
        <div style="font-size: 0.9rem; color: #666;">
            月租: ${rent:,} 元
        </div>
    """ if tenant_name else '<div style="color: #999; font-style: italic;">待出租</div>'

    st.markdown(f"""
        <div style="
            background-color: {bg};
            border: 2px solid {border};
            border-radius: 10px;
            padding: 1rem;
            height: 100%;
            transition: transform 0.2s;
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                <div style="font-size: 1.3rem; font-weight: bold; color: {border};">
                    {room}
                </div>
                <div style="font-size: 0.85rem; color: {border};">
                    {icon} {status_text}
                </div>
            </div>
            {tenant_info}
        </div>
    """, unsafe_allow_html=True)


def data_table(df, key: str = "table"):
    """
    美化的資料表格

    Args:
        df: pandas DataFrame
        key: unique key for the table
    """
    st.dataframe(
        df,
        width="stretch",                         # ✅ FIX: use_container_width=True → width="stretch"
        height=min(400, len(df) * 35 + 38),
        key=key
    )


def empty_state(message: str, icon: str = "📭", suggestion: Optional[str] = None):
    """
    空狀態提示

    Args:
        message: 提示訊息
        icon: 圖示
        suggestion: 建議操作 (可選)
    """
    st.markdown(f"""
        <div style="
            text-align: center;
            padding: 3rem 1rem;
            color: #999;
        ">
            <div style="font-size: 4rem; margin-bottom: 1rem;">
                {icon}
            </div>
            <div style="font-size: 1.2rem; font-weight: 500; margin-bottom: 0.5rem;">
                {message}
            </div>
            {f'<div style="font-size: 0.95rem;">{suggestion}</div>' if suggestion else ''}
        </div>
    """, unsafe_allow_html=True)


def loading_spinner(text: str = "載入中..."):
    """
    載入指示器

    Args:
        text: 提示文字
    """
    return st.spinner(text)


def confirm_dialog(message: str, key: str) -> bool:
    """
    確認對話框 (需配合 session_state)

    Args:
        message: 確認訊息
        key: session_state key

    Returns:
        bool: 是否已確認

    Usage:
        if st.button("刪除"):
            if confirm_dialog("確定要刪除嗎?", "delete_confirm"):
                # 執行刪除
                del st.session_state.delete_confirm
    """
    if st.session_state.get(key):
        st.warning(f"⚠️ {message}")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ 確認", key=f"{key}_yes"):
                return True
        with col2:
            if st.button("❌ 取消", key=f"{key}_no"):
                del st.session_state[key]
        return False
    else:
        st.session_state[key] = True
        return False


def progress_bar(current: int, total: int, label: str = ""):
    """
    進度條

    Args:
        current: 當前進度
        total: 總數
        label: 標籤
    """
    percentage = current / total if total > 0 else 0
    st.progress(percentage, text=f"{label} ({current}/{total})")
