"""
租金管理 - 優化版
特性:
- 防重複生成機制
- 批量操作 + 進度條
- 財報生成
- 繳費提醒接口預留
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from typing import List, Dict, Tuple
import sys
sys.path.append('..')

from components.cards import (
    section_header, metric_card, empty_state, 
    data_table, info_card, progress_bar
)
from config.constants import ROOMS, PAYMENT


# ============== 輔助函數 ==============

def get_active_tenants(db) -> pd.DataFrame:
    """取得當前有效房客"""
    df = db.get_tenants()
    if df.empty:
        return df
    
    # 篩選租約未到期的房客
    today = date.today()
    df['lease_end_date'] = pd.to_datetime(df['lease_end']).dt.date
    df = df[df['lease_end_date'] >= today]
    
    return df


def calculate_monthly_rent(base_rent: float, has_water_fee: bool, 
                          payment_method: str) -> float:
    """
    計算月租金
    
    Args:
        base_rent: 基本租金
        has_water_fee: 是否有水費折扣
        payment_method: 繳款方式
    
    Returns:
        應收金額
    """
    amount = base_rent
    
    # 扣除水費
    if has_water_fee:
        amount -= PAYMENT.DEFAULT_WATER_FEE
    
    return amount


def check_schedule_exists(db, room: str, year: int, month: int) -> bool:
    """
    檢查應收單是否已存在
    
    Args:
        db: 資料庫實例
        room: 房號
        year: 年份
        month: 月份
    
    Returns:
        是否已存在
    """
    try:
        with db._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) FROM payment_schedule
                WHERE room_number = %s 
                AND payment_year = %s 
                AND payment_month = %s
            """, (room, year, month))
            
            count = cur.fetchone()[0]
            return count > 0
    except Exception as e:
        st.error(f"檢查失敗: {e}")
        return False


def generate_payment_schedule_batch(db, 
                                    room: str,
                                    tenant_name: str,
                                    base_rent: float,
                                    has_water_fee: bool,
                                    payment_method: str,
                                    start_date: date,
                                    months: int,
                                    skip_existing: bool = True) -> Tuple[int, int]:
    """
    批量生成應收單
    
    Args:
        db: 資料庫實例
        room: 房號
        tenant_name: 房客名稱
        base_rent: 基本租金
        has_water_fee: 是否有水費
        payment_method: 繳款方式
        start_date: 開始日期
        months: 月數
        skip_existing: 是否跳過已存在的
    
    Returns:
        (成功數, 跳過數)
    """
    success_count = 0
    skip_count = 0
    
    amount = calculate_monthly_rent(base_rent, has_water_fee, payment_method)
    
    for i in range(months):
        target_date = start_date + relativedelta(months=i)
        year = target_date.year
        month = target_date.month
        
        # 檢查是否已存在
        if skip_existing and check_schedule_exists(db, room, year, month):
            skip_count += 1
            continue
        
        # 計算到期日 (每月 5 號)
        due_date = date(year, month, 5)
        
        # 新增應收單
        ok, msg = db.add_payment_schedule(
            room, tenant_name, year, month,
            amount, payment_method, due_date
        )
        
        if ok:
            success_count += 1
    
    return success_count, skip_count


# ============== Tab 1: 單筆預填 ==============

def render_single_tab(db):
    """單筆預填 Tab"""
    section_header("單筆預填應收單", "📝")
    
    df_tenants = get_active_tenants(db)
    
    if df_tenants.empty:
        empty_state(
            "沒有可預填的房客",
            "👥",
            "請先在「房客管理」新增房客"
        )
        return
    
    # 選擇房客
    tenant_options = {
        f"{row['room_number']} - {row['tenant_name']}": row
        for _, row in df_tenants.iterrows()
    }
    
    selected = st.selectbox(
        "選擇房客",
        list(tenant_options.keys()),
        key="single_tenant"
    )
    
    tenant = tenant_options[selected]
    
    st.divider()
    
    # 顯示房客資訊
    col1, col2, col3 = st.columns(3)
    
    with col1:
        metric_card("房號", tenant['room_number'], icon="🏠")
    
    with col2:
        metric_card("房客", tenant['tenant_name'], icon="👤")
    
    with col3:
        metric_card("月租", f"${tenant['base_rent']:,}", icon="💰")
    
    st.divider()
    
    # 輸入資訊
    col_a, col_b, col_c = st.columns(3)
    
    with col_a:
        year = st.number_input(
            "年份",
            min_value=2020,
            max_value=2030,
            value=date.today().year,
            key="single_year"
        )
    
    with col_b:
        month = st.selectbox(
            "月份",
            list(range(1, 13)),
            index=date.today().month - 1,
            key="single_month"
        )
    
    with col_c:
        due_day = st.number_input(
            "到期日 (日)",
            min_value=1,
            max_value=28,
            value=5,
            key="single_due_day"
        )
    
    # 計算金額
    amount = calculate_monthly_rent(
        tenant['base_rent'],
        tenant.get('has_water_fee', False),
        tenant['payment_method']
    )
    
    st.info(f"💰 應收金額: **${amount:,}** 元")
    
    if tenant.get('has_water_fee', False):
        st.caption(f"(已扣除水費 ${PAYMENT.DEFAULT_WATER_FEE})")
    
    # 檢查是否已存在
    already_exists = check_schedule_exists(
        db, tenant['room_number'], year, month
    )
    
    if already_exists:
        st.warning(f"⚠️ {year}/{month} 的應收單已存在")
    
    st.divider()
    
    # 預填按鈕
    if st.button("✅ 預填應收單", type="primary", disabled=already_exists):
        due_date = date(year, month, due_day)
        
        ok, msg = db.add_payment_schedule(
            tenant['room_number'],
            tenant['tenant_name'],
            year,
            month,
            amount,
            tenant['payment_method'],
            due_date
        )
        
        if ok:
            st.success(msg)
            st.balloons()
        else:
            st.error(msg)


# ============== Tab 2: 批量預填 ==============

def render_batch_tab(db):
    """批量預填 Tab"""
    section_header("批量預填應收單", "📋")
    
    df_tenants = get_active_tenants(db)
    
    if df_tenants.empty:
        empty_state("沒有可預填的房客", "👥")
        return
    
    st.info(f"📊 當前有 **{len(df_tenants)}** 個房客可預填")
    
    # 批量設定
    col1, col2, col3 = st.columns(3)
    
    with col1:
        start_year = st.number_input(
            "開始年份",
            min_value=2020,
            max_value=2030,
            value=date.today().year,
            key="batch_year"
        )
    
    with col2:
        start_month = st.selectbox(
            "開始月份",
            list(range(1, 13)),
            index=date.today().month - 1,
            key="batch_month"
        )
    
    with col3:
        months_count = st.number_input(
            "產生月數",
            min_value=1,
            max_value=12,
            value=6,
            key="batch_months"
        )
    
    skip_existing = st.checkbox(
        "跳過已存在的應收單",
        value=True,
        help="勾選後會自動跳過已建立的應收單",
        key="batch_skip"
    )
    
    st.divider()
    
    # 預覽將要生成的期間
    st.write("**將要生成的期間:**")
    
    preview_periods = []
    start_date = date(start_year, start_month, 1)
    
    for i in range(months_count):
        target_date = start_date + relativedelta(months=i)
        preview_periods.append(f"{target_date.year}/{target_date.month}")
    
    st.write(" → ".join(preview_periods))
    
    st.divider()
    
    # 批量生成按鈕
    if st.button("🚀 開始批量生成", type="primary"):
        start_date = date(start_year, start_month, 1)
        
        # 進度容器
        progress_container = st.empty()
        status_container = st.empty()
        
        total_success = 0
        total_skip = 0
        
        # 逐個房客處理
        for idx, (_, tenant) in enumerate(df_tenants.iterrows()):
            progress_container.progress(
                (idx + 1) / len(df_tenants),
                text=f"處理中: {tenant['room_number']} - {tenant['tenant_name']}"
            )
            
            success, skip = generate_payment_schedule_batch(
                db,
                tenant['room_number'],
                tenant['tenant_name'],
                tenant['base_rent'],
                tenant.get('has_water_fee', False),
                tenant['payment_method'],
                start_date,
                months_count,
                skip_existing
            )
            
            total_success += success
            total_skip += skip
        
        # 清除進度條
        progress_container.empty()
        
        # 顯示結果
        st.success(
            f"✅ 批量生成完成！\n\n"
            f"- 成功建立: **{total_success}** 筆\n"
            f"- 跳過已存在: **{total_skip}** 筆"
        )
        
        st.balloons()


# ============== Tab 3: 確認繳費 ==============

def render_payment_tab(db):
    """確認繳費 Tab"""
    section_header("確認繳費", "✅")
    
    # 篩選條件
    col1, col2, col3 = st.columns(3)
    
    with col1:
        filter_year = st.selectbox(
            "年份",
            [None] + list(range(2020, 2031)),
            format_func=lambda x: "全部" if x is None else str(x),
            key="payment_year"
        )
    
    with col2:
        filter_month = st.selectbox(
            "月份",
            [None] + list(range(1, 13)),
            format_func=lambda x: "全部" if x is None else str(x),
            key="payment_month"
        )
    
    with col3:
        filter_status = st.selectbox(
            "狀態",
            [None, "未繳", "已繳"],
            format_func=lambda x: "全部" if x is None else x,
            key="payment_status"
        )
    
    # 查詢
    df = db.get_payment_schedule(
        year=filter_year,
        month=filter_month,
        status=filter_status
    )
    
    if df.empty:
        empty_state("沒有符合條件的應收單", "📭")
        return
    
    st.write(f"共 {len(df)} 筆應收單")
    
    # 顯示統計
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    
    unpaid_df = df[df['status'] == '未繳']
    paid_df = df[df['status'] == '已繳']
    
    with col_stat1:
        metric_card(
            "未繳",
            str(len(unpaid_df)),
            f"金額: ${unpaid_df['amount'].sum():,.0f}",
            "⚠️",
            "warning"
        )
    
    with col_stat2:
        metric_card(
            "已繳",
            str(len(paid_df)),
            f"金額: ${paid_df['paid_amount'].sum():,.0f}",
            "✅",
            "success"
        )
    
    with col_stat3:
        metric_card(
            "收款率",
            f"{(len(paid_df) / len(df) * 100):.1f}%",
            f"{len(paid_df)}/{len(df)}",
            "📊",
            "normal"
        )
    
    st.divider()
    
    # 快速標記區 (只顯示未繳)
    if len(unpaid_df) > 0:
        section_header("快速標記已繳", "⚡", divider=False)
        
        # 分頁顯示
        items_per_page = 10
        total_pages = (len(unpaid_df) - 1) // items_per_page + 1
        
        if 'payment_page' not in st.session_state:
            st.session_state.payment_page = 0
        
        # 分頁控制
        col_prev, col_page, col_next = st.columns([1, 2, 1])
        
        with col_prev:
            if st.button("⬅️ 上一頁", disabled=st.session_state.payment_page == 0):
                st.session_state.payment_page -= 1
                st.rerun()
        
        with col_page:
            st.write(f"第 {st.session_state.payment_page + 1} / {total_pages} 頁")
        
        with col_next:
            if st.button("➡️ 下一頁", disabled=st.session_state.payment_page >= total_pages - 1):
                st.session_state.payment_page += 1
                st.rerun()
        
        # 顯示當前頁的項目
        start_idx = st.session_state.payment_page * items_per_page
        end_idx = start_idx + items_per_page
        page_df = unpaid_df.iloc[start_idx:end_idx]
        
        for _, row in page_df.iterrows():
            col_info, col_btn = st.columns([4, 1])
            
            with col_info:
                st.write(
                    f"**{row['room_number']}** - {row['tenant_name']} | "
                    f"{row['payment_year']}/{row['payment_month']} | "
                    f"${row['amount']:,} 元"
                )
            
            with col_btn:
                if st.button("✅ 已繳", key=f"mark_{row['id']}"):
                    if db.mark_payment_done(row['id']):
                        st.success("✅ 已標記")
                        st.rerun()
    
    st.divider()
    
    # 完整列表
    section_header("應收單列表", "📋", divider=False)
    
    # 格式化顯示
    display_df = df.copy()
    display_df['期間'] = display_df.apply(
        lambda x: f"{x['payment_year']}/{x['payment_month']}", axis=1
    )
    display_df['應收金額'] = display_df['amount'].apply(lambda x: f"${x:,}")
    display_df['實收金額'] = display_df['paid_amount'].apply(lambda x: f"${x:,}")
    
    show_cols = ['房號', '房客名稱', '期間', '應收金額', '實收金額', '繳款方式', '狀態']
    rename_cols = {
        'room_number': '房號',
        'tenant_name': '房客名稱',
        'payment_method': '繳款方式',
        'status': '狀態'
    }
    
    display_df = display_df.rename(columns=rename_cols)
    data_table(display_df[show_cols], key="payment_list")


# ============== Tab 4: 財報統計 ==============

def render_report_tab(db):
    """財報統計 Tab"""
    section_header("財務報表", "📊")
    
    # 選擇期間
    col1, col2 = st.columns(2)
    
    with col1:
        report_year = st.selectbox(
            "年份",
            list(range(2020, 2031)),
            index=date.today().year - 2020,
            key="report_year"
        )
    
    with col2:
        report_type = st.radio(
            "報表類型",
            ["月報", "年報"],
            horizontal=True,
            key="report_type"
        )
    
    st.divider()
    
    if report_type == "月報":
        # 月報
        month = st.selectbox(
            "月份",
            list(range(1, 13)),
            index=date.today().month - 1,
            key="report_month"
        )
        
        df = db.get_payment_schedule(year=report_year, month=month)
        
        if df.empty:
            empty_state(f"{report_year}/{month} 沒有應收單", "📭")
            return
        
        # 統計
        total_amount = df['amount'].sum()
        paid_amount = df[df['status'] == '已繳']['paid_amount'].sum()
        unpaid_amount = df[df['status'] == '未繳']['amount'].sum()
        
        col_a, col_b, col_c = st.columns(3)
        
        with col_a:
            metric_card("應收總額", f"${total_amount:,}", icon="💰", color="normal")
        
        with col_b:
            metric_card("已收金額", f"${paid_amount:,}", icon="✅", color="success")
        
        with col_c:
            metric_card("未收金額", f"${unpaid_amount:,}", icon="⚠️", color="warning")
        
        # 按房號統計
        st.divider()
        section_header("各房間明細", "🏠", divider=False)
        
        summary = df.groupby('room_number').agg({
            'amount': 'sum',
            'paid_amount': 'sum'
        }).reset_index()
        
        summary['未收'] = summary['amount'] - summary['paid_amount']
        summary.columns = ['房號', '應收', '已收', '未收']
        
        # 使用 Streamlit 內建圖表
        st.bar_chart(summary.set_index('房號')[['已收', '未收']])
        
        data_table(summary, key="monthly_summary")
    
    else:
        # 年報
        df = db.get_payment_schedule(year=report_year)
        
        if df.empty:
            empty_state(f"{report_year} 年沒有應收單", "📭")
            return
        
        # 年度統計
        total_amount = df['amount'].sum()
        paid_amount = df[df['status'] == '已繳']['paid_amount'].sum()
        unpaid_amount = df[df['status'] == '未繳']['amount'].sum()
        
        col_a, col_b, col_c = st.columns(3)
        
        with col_a:
            metric_card("年度應收", f"${total_amount:,}", icon="💰", color="normal")
        
        with col_b:
            metric_card("年度實收", f"${paid_amount:,}", icon="✅", color="success")
        
        with col_c:
            metric_card("收款率", f"{(paid_amount/total_amount*100):.1f}%", icon="📊", color="normal")
        
        # 按月份統計
        st.divider()
        section_header("月度趨勢", "📈", divider=False)
        
        monthly = df.groupby('payment_month').agg({
            'amount': 'sum',
            'paid_amount': 'sum'
        }).reset_index()
        
        monthly.columns = ['月份', '應收', '已收']
        monthly = monthly.sort_values('月份')
        
        st.line_chart(monthly.set_index('月份'))
        
        data_table(monthly, key="yearly_summary")


# ============== 主渲染函數 ==============

def render(db):
    """主渲染函數"""
    st.title("💰 租金管理")
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "📝 單筆預填",
        "📋 批量預填", 
        "✅ 確認繳費",
        "📊 財務報表"
    ])
    
    with tab1:
        render_single_tab(db)
    
    with tab2:
        render_batch_tab(db)
    
    with tab3:
        render_payment_tab(db)
    
    with tab4:
        render_report_tab(db)