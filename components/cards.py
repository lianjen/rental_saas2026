"""
UI 元件庫 - 統一視覺風格
✅ [FIX v1.1] data_table: use_container_width → width="stretch" (移除棄用警告)
✅ [FIX v1.2] data_table: index 從 1 開始（全局生效）
✅ [NEW v1.3] room_status_card 加入 payment_cycle 繳費方式標籤
"""

import streamlit as st
from typing import Optional


def section_header(title: str, icon: str = "📌", divider: bool = True):
    st.markdown(f"### {icon} {title}")
    if divider:
        st.divider()


def metric_card(label: str, value: str, delta: Optional[str] = None,
                icon: str = "📊", color: str = "normal"):
    color_map = {
        'normal':  '#1f77b4',
        'success': '#2ca02c',
        'warning': '#ff7f0e',
        'error':   '#d62728'
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
    colors = {
        'success': ('#d4edda', '#155724'),
        'warning': ('#fff3cd', '#856404'),
        'error':   ('#f8d7da', '#721c24'),
        'info':    ('#d1ecf1', '#0c5460'),
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
    type_colors = {
        'info':    ('#cfe2ff', '#084298'),
        'success': ('#d1e7dd', '#0f5132'),
        'warning': ('#fff3cd', '#664d03'),
        'error':   ('#f8d7da', '#842029')
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


# ── 繳費方式設定（badge 顏色 & 圖示）────────────────────────────
_CYCLE_STYLE = {
    "月繳":  {"bg": "#e3f2fd", "fg": "#1565c0", "icon": "📅"},
    "半年繳": {"bg": "#e8f5e9", "fg": "#2e7d32", "icon": "📆"},
    "年繳":  {"bg": "#f3e5f5", "fg": "#6a1b9a", "icon": "🏷️"},
}


def _cycle_badge_html(payment_cycle: Optional[str]) -> str:
    """產生繳費方式 badge HTML"""
    if not payment_cycle:
        return ""
    style = _CYCLE_STYLE.get(payment_cycle, {"bg": "#f5f5f5", "fg": "#757575", "icon": ""})
    return (
        f'<span style="'
        f'background:{style["bg"]};'
        f'color:{style["fg"]};'
        f'padding:2px 8px;'
        f'border-radius:10px;'
        f'font-size:0.75rem;'
        f'font-weight:600;'
        f'display:inline-block;'
        f'">{style["icon"]} {payment_cycle}</span>'
    )


def room_status_card(
    room: str,
    tenant_name: Optional[str],
    status: str,
    rent: Optional[float] = None,
    payment_cycle: Optional[str] = None,   # ✅ [NEW v1.3] 繳費方式
):
    """
    房間狀態卡片

    Args:
        room:          房號
        tenant_name:   房客名稱
        status:        'occupied' | 'vacant' | 'warning'
        rent:          月租金（折扣後有效月租）
        payment_cycle: 繳費方式，'月繳' | '半年繳' | '年繳'
    """
    status_config = {
        'occupied': ('🟢', '已出租',    '#d4edda', '#155724'),
        'vacant':   ('⚪', '空房',      '#e2e3e5', '#6c757d'),
        'warning':  ('🟡', '即將到期',  '#fff3cd', '#856404')
    }
    icon, status_text, bg, border = status_config.get(status, status_config['vacant'])

    if tenant_name:
        cycle_html = _cycle_badge_html(payment_cycle)
        tenant_info = f"""
            <div style="font-size: 1rem; font-weight: 500; margin: 0.5rem 0;">
                {tenant_name}
            </div>
            <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                <span style="font-size: 0.9rem; color: #555;">
                    月租: <b>${rent:,}</b> 元
                </span>
                {cycle_html}
            </div>
        """
    else:
        tenant_info = '<div style="color: #999; font-style: italic;">待出租</div>'

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
    ✅ [v1.2] index 自動從 1 開始，全局生效
    """
    display = df.copy()
    display.index = range(1, len(display) + 1)
    st.dataframe(
        display,
        width="stretch",
        height=min(400, len(display) * 35 + 38),
        key=key
    )


def empty_state(message: str, icon: str = "📭", suggestion: Optional[str] = None):
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
    return st.spinner(text)


def confirm_dialog(message: str, key: str) -> bool:
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
    percentage = current / total if total > 0 else 0
    st.progress(percentage, text=f"{label} ({current}/{total})")
