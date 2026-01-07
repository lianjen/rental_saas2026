"""
租金管理 - 完整重構版
特性:
- 批量生成應收單
- 年繳折扣自動計算
- 水費自動處理
- 視覺化報表
- 批量操作
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
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
    from config.constants import PAYMENT
except ImportError:
    class PAYMENT:
        DEFAULT_WATER_FEE = 100
        METHODS = ["月繳", "半年繳", "年繳"]

logger = logging.getLogger(__name__)

# ============== 租金計算邏輯 ==============

def calculate_rent_with_discount(base_rent: float,
                                 has_water_fee: bool,
                                 payment_method: str,
                                 annual_discount_months: int = 0) -> dict:
    """
    計算租金 (含折扣)
    
    Args:
        base_rent: 基本月租
        has_water_fee: 是否包含水費折扣
        payment_method: 繳款方式
        annual_discount_months: 年繳折扣月數
    
    Returns:
        {
            'monthly_rent': 每月應繳,
            'water_discount': 水費折扣,
            'annual_discount': 年繳折扣,
            'total_annual': 年繳總額
        }
    """
    # 1. 基本租金
    monthly_rent = base_rent
    
    # 2. 水費折扣
    water_discount = PAYMENT.DEFAULT_WATER_FEE if has_water_fee else 0
    monthly_rent -= water_discount
    
    # 3. 年繳折扣
    annual_discount = 0
    if payment_method == "年繳" and annual_discount_months > 0:
        annual_discount = monthly_rent * annual_discount_months
    
    # 4. 年繳總額
    total_annual = (monthly_rent * 12) - annual_discount
    
    return {
        'monthly_rent': monthly_rent,
        'water_discount': water_discount,
        'annual_discount': annual_discount,
        'total_annual': total_annual,
        'effective_monthly': total_annual / 12 if payment_method == "年繳" else monthly_rent
    }


def generate_schedule_list(tenant: dict,
                          start_date: date,
                          months: int) -> list:
    """
    生成應收單列表
    
    Args:
        tenant: 房客資料
        start_date: 開始日期
        months: 月數
    
    Returns:
        應收單列表
    """
    schedules = []
    
    rent_info = calculate_rent_with_discount(
        tenant['base_rent'],
        tenant.get('has_water_fee', False),
        tenant['payment_method'],
        tenant.get('annual_discount_months', 0)
    )
    
    for i in range(months):
        target_date = start_date + relativedelta(months=i)
        
        schedules.append({
            'room_number': tenant['room_number'],
            'tenant_name': tenant['tenant_name'],
            'payment_year': target_date.year,
            'payment_month': target_date.month,
            'amount': rent_info['monthly_rent'],
            'payment_method': tenant['payment_method'],
            'due_date': date(target_date.year, target_date.month, 5)
        })
    
    return schedules


# ============== Tab 1: 單筆預填 ==============

def render_single_tab(db):
    """單筆預填"""
    section_header("單筆預填應收單", "📝")
    
    # 取得房客
    try:
        df_tenants = db.get_tenants()
    except Exception as e:
        st.error(f"❌ 載入房客失敗: {e}")
        return
    
    if df_tenants.empty:
        empty_state("沒有房客資料", "👥", "請先在「房客管理」新增房客")
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
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        metric_card("房號", tenant['room_number'], icon="🏠")
    
    with col2:
        metric_card("月租", f"${tenant['base_rent']:,}", icon="💰")
    
    with col3:
        water_text = "是" if tenant.get('has_water_fee', False) else "否"
        metric_card("水費折扣", water_text, icon="💧")
    
    with col4:
        metric_card("繳款方式", tenant['payment_method'], icon="📋")
    
    # 計算租金
    rent_info = calculate_rent_with_discount(
        tenant['base_rent'],
        tenant.get('has_water_fee', False),
        tenant['payment_method'],
        tenant.get('annual_discount_months', 0)
    )
    
    st.info(f"""
💰 **租金計算明細**
- 基本月租: ${tenant['base_rent']:,}
- 水費折扣: -${rent_info['water_discount']}
- 實際月租: ${rent_info['monthly_rent']:,}
{f"- 年繳折扣: -{rent_info['annual_discount']:,} ({tenant.get('annual_discount_months', 0)} 個月)" if rent_info['annual_discount'] > 0 else ""}
{f"- 年繳總額: ${rent_info['total_annual']:,}" if tenant['payment_method'] == "年繳" else ""}
""")
    
    st.divider()
    
    # 輸入期間
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
            range(1, 13),
            index=date.today().month - 1,
            key="single_month"
        )
    
    with col_c:
        due_day = st.number_input(
            "到期日",
            min_value=1,
            max_value=28,
            value=5,
            key="single_due"
        )
    
    # 檢查是否已存在
    already_exists = db.check_payment_exists(tenant['room_number'], year, month)
    
    if already_exists:
        st.warning(f"⚠️ {year}/{month} 的應收單已存在")
    
    # 預填按鈕
    if st.button("✅ 預填應收單", type="primary", disabled=already_exists):
        due_date = date(year, month, due_day)
        
        ok, msg = db.add_payment_schedule(
            tenant['room_number'],
            tenant['tenant_name'],
            year,
            month,
            rent_info['monthly_rent'],
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
    """批量預填"""
    section_header("批量預填應收單", "📋")
    
    # 取得房客
    try:
        df_tenants = db.get_tenants()
    except Exception as e:
        st.error(f"❌ 載入房客失敗: {e}")
        return
    
    if df_tenants.empty:
        empty_state("沒有房客資料", "👥")
        return
    
    st.info(f"📊 當前有 **{len(df_tenants)}** 個房客")
    
    # 設定
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
            range(1, 13),
            index=date.today().month - 1,
            key="batch_month"
        )
    
    with col3:
        months_count = st.number_input(
            "產生月數",
            min_value=1,
            max_value=24,
            value=6,
            key="batch_months"
        )
    
    # 選項
    col_a, col_b = st.columns(2)
    
    with col_a:
        skip_existing = st.checkbox(
            "跳過已存在的應收單",
            value=True,
            key="batch_skip"
        )
    
    with col_b:
        filter_rooms = st.multiselect(
            "僅處理特定房號 (不選則全部)",
            df_tenants['room_number'].tolist(),
            key="batch_rooms"
        )
    
    st.divider()
    
    # 預覽
    start_date = date(start_year, start_month, 1)
    preview_periods = []
    
    for i in range(min(months_count, 6)):  # 最多預覽 6 個月
        target_date = start_date + relativedelta(months=i)
        preview_periods.append(f"{target_date.year}/{target_date.month}")
    
    if months_count > 6:
        preview_periods.append("...")
    
    st.write(f"**將生成期間:** {' → '.join(preview_periods)}")
    
    # 過濾房客
    filtered_tenants = df_tenants.copy()
    if filter_rooms:
        filtered_tenants = filtered_tenants[filtered_tenants['room_number'].isin(filter_rooms)]
    
    st.write(f"**將處理房客數:** {len(filtered_tenants)} 個")
    
    st.divider()
    
    # 批量生成
    if st.button("🚀 開始批量生成", type="primary"):
        with st.spinner("處理中..."):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            all_schedules = []
            
            # 生成所有應收單
            for idx, (_, tenant) in enumerate(filtered_tenants.iterrows()):
                status_text.text(f"準備資料: {tenant['room_number']} - {tenant['tenant_name']}")
                
                schedules = generate_schedule_list(
                    tenant,
                    start_date,
                    months_count
                )
                
                all_schedules.extend(schedules)
                
                progress_bar.progress((idx + 1) / len(filtered_tenants) * 0.5)
            
            # 批量插入
            status_text.text("批量寫入資料庫...")
            
            if skip_existing:
                # 過濾已存在的
                filtered_schedules = []
                for schedule in all_schedules:
                    if not db.check_payment_exists(
                        schedule['room_number'],
                        schedule['payment_year'],
                        schedule['payment_month']
                    ):
                        filtered_schedules.append(schedule)
                
                skipped = len(all_schedules) - len(filtered_schedules)
                all_schedules = filtered_schedules
            else:
                skipped = 0
            
            # 執行批量插入
            success, skip, fail = db.batch_create_payment_schedule(all_schedules)
            
            progress_bar.progress(1.0)
            status_text.empty()
            progress_bar.empty()
            
            # 顯示結果
            st.success(f"""
✅ **批量生成完成！**

- 成功建立: **{success}** 筆
- 跳過已存在: **{skip + skipped}** 筆
- 失敗: **{fail}** 筆
""")
            
            if success > 0:
                st.balloons()


# ============== Tab 3: 繳費確認 ==============

def render_payment_tab(db):
    """繳費確認"""
    section_header("繳費確認", "✅")
    
    # 篩選
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        filter_year = st.selectbox(
            "年份",
            [None] + list(range(2020, 2031)),
            format_func=lambda x: "全部" if x is None else str(x),
            key="pay_year"
        )
    
    with col2:
        filter_month = st.selectbox(
            "月份",
            [None] + list(range(1, 13)),
            format_func=lambda x: "全部" if x is None else str(x),
            key="pay_month"
        )
    
    with col3:
        filter_status = st.selectbox(
            "狀態",
            [None, "未繳", "已繳"],
            format_func=lambda x: "全部" if x is None else x,
            key="pay_status"
        )
    
    with col4:
        filter_room = st.selectbox(
            "房號",
            [None] + db.get_tenants()['room_number'].tolist() if not db.get_tenants().empty else [None],
            format_func=lambda x: "全部" if x is None else x,
            key="pay_room"
        )
    
    # 查詢
    df = db.get_payment_schedule(
        year=filter_year,
        month=filter_month,
        room=filter_room,
        status=filter_status
    )
    
    if df.empty:
        empty_state("沒有符合條件的應收單", "📭")
        return
    
    # 統計
    stats = db.get_payment_statistics(filter_year, filter_month)
    
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    
    with col_s1:
        metric_card(
            "應收總額",
            f"${stats.get('total_amount', 0):,.0f}",
            icon="💰",
            color="normal"
        )
    
    with col_s2:
        metric_card(
            "已收金額",
            f"${stats.get('paid_amount', 0):,.0f}",
            icon="✅",
            color="success"
        )
    
    with col_s3:
        metric_card(
            "未收金額",
            f"${stats.get('unpaid_amount', 0):,.0f}",
            icon="⚠️",
            color="warning"
        )
    
    with col_s4:
        metric_card(
            "收款率",
            f"{stats.get('payment_rate', 0):.1f}%",
            icon="📊",
            color="normal"
        )
    
    st.divider()
    
    # 批量操作
    unpaid_df = df[df['status'] == '未繳']
    
    if not unpaid_df.empty:
        section_header("批量操作", "⚡", divider=False)
        
        selected_ids = st.multiselect(
            "選擇要標記的應收單",
            unpaid_df['id'].tolist(),
            format_func=lambda x: f"{unpaid_df[unpaid_df['id']==x]['room_number'].values[0]} - {unpaid_df[unpaid_df['id']==x]['payment_year'].values[0]}/{unpaid_df[unpaid_df['id']==x]['payment_month'].values[0]}",
            key="batch_mark_ids"
        )
        
        col_mark, col_clear = st.columns([1, 3])
        
        with col_mark:
            if st.button("✅ 批量標記已繳", disabled=len(selected_ids) == 0):
                success, fail = db.batch_mark_paid(selected_ids)
                
                if success > 0:
                    st.success(f"✅ 成功標記 {success} 筆")
                    st.rerun()
                if fail > 0:
                    st.error(f"❌ 失敗 {fail} 筆")
        
        st.divider()
    
    # 列表
    section_header("應收單列表", "📋", divider=False)
    
    st.write(f"共 {len(df)} 筆")
    
    # 格式化
    display_df = df.copy()
    display_df['期間'] = display_df.apply(
        lambda x: f"{x['payment_year']}/{x['payment_month']}", axis=1
    )
    display_df['應收'] = display_df['amount'].apply(lambda x: f"${x:,.0f}")
    display_df['實收'] = display_df['paid_amount'].apply(lambda x: f"${x:,.0f}")
    
    cols_to_show = ['id', '房號', '房客名稱', '期間', '應收', '實收', '繳款方式', '狀態']
    rename = {
        'room_number': '房號',
        'tenant_name': '房客名稱',
        'payment_method': '繳款方式',
        'status': '狀態'
    }
    
    display_df = display_df.rename(columns=rename)
    
    # 顯示表格
    data_table(display_df[cols_to_show], key="payment_list")
    
    # 快速標記
    st.divider()
    section_header("快速標記", "⚡", divider=False)
    
    if not unpaid_df.empty:
        for _, row in unpaid_df.head(10).iterrows():  # 只顯示前 10 筆
            col_info, col_btn1, col_btn2 = st.columns([3, 1, 1])
            
            with col_info:
                st.write(
                    f"**{row['room_number']}** {row['tenant_name']} | "
                    f"{row['payment_year']}/{row['payment_month']} | "
                    f"${row['amount']:,}"
                )
            
            with col_btn1:
                if st.button("✅", key=f"mark_{row['id']}"):
                    if db.mark_payment_done(row['id']):
                        st.success("✅")
                        st.rerun()
            
            with col_btn2:
                if st.button("🗑️", key=f"del_{row['id']}"):
                    if st.session_state.get(f'confirm_del_{row["id"]}'):
                        ok, msg = db.delete_payment_schedule(row['id'])
                        if ok:
                            st.success("✅")
                            del st.session_state[f'confirm_del_{row["id"]}']
                            st.rerun()
                    else:
                        st.session_state[f'confirm_del_{row["id"]}'] = True
                        st.warning("再按一次確認")
    else:
        st.success("✅ 全部已繳清")


# ============== Tab 4: 財報統計 ==============

def render_report_tab(db):
    """財報統計"""
    section_header("財務報表", "📊")
    
    # 選擇年份
    col1, col2 = st.columns(2)
    
    with col1:
        report_year = st.selectbox(
            "年份",
            range(2020, 2031),
            index=date.today().year - 2020,
            key="report_year"
        )
    
    with col2:
        report_type = st.radio(
            "報表類型",
            ["月度報表", "年度趨勢"],
            horizontal=True,
            key="report_type"
        )
    
    st.divider()
    
    if report_type == "月度報表":
        # 月度報表
        month = st.selectbox("月份", range(1, 13), index=date.today().month - 1, key="report_month")
        
        stats = db.get_payment_statistics(report_year, month)
        
        if stats.get('total_count', 0) == 0:
            empty_state(f"{report_year}/{month} 沒有應收單", "📭")
            return
        
        # 統計卡片
        col_a, col_b, col_c = st.columns(3)
        
        with col_a:
            metric_card("應收總額", f"${stats['total_amount']:,.0f}", icon="💰")
        
        with col_b:
            metric_card("已收金額", f"${stats['paid_amount']:,.0f}", icon="✅", color="success")
        
        with col_c:
            metric_card("收款率", f"{stats['payment_rate']:.1f}%", icon="📊")
        
        # 取得明細
        df = db.get_payment_schedule(year=report_year, month=month)
        
        if not df.empty:
            st.divider()
            st.write("**各房號明細**")
            
            summary = df.groupby('room_number').agg({
                'amount': 'sum',
                'paid_amount': 'sum'
            }).reset_index()
            
            summary['未收'] = summary['amount'] - summary['paid_amount']
            summary.columns = ['房號', '應收', '已收', '未收']
            
            # 圖表
            st.bar_chart(summary.set_index('房號')[['已收', '未收']])
            
            # 表格
            data_table(summary, key="monthly_detail")
    
    else:
        # 年度趨勢
        trends = db.get_payment_trends(report_year)
        
        if not trends:
            empty_state(f"{report_year} 年沒有資料", "📭")
            return
        
        # 年度統計
        stats = db.get_payment_statistics(report_year)
        
        col_a, col_b, col_c = st.columns(3)
        
        with col_a:
            metric_card("年度應收", f"${stats['total_amount']:,.0f}", icon="💰")
        
        with col_b:
            metric_card("年度實收", f"${stats['paid_amount']:,.0f}", icon="✅", color="success")
        
        with col_c:
            metric_card("年度收款率", f"{stats['payment_rate']:.1f}%", icon="📊")
        
        st.divider()
        
        # 趨勢圖
        df_trends = pd.DataFrame(trends)
        
        st.write("**月度收款趨勢**")
        st.line_chart(df_trends.set_index('month')[['total_amount', 'paid_amount']])
        
        st.divider()
        
        st.write("**月度收款率**")
        st.bar_chart(df_trends.set_index('month')['payment_rate'])
        
        st.divider()
        
        # 表格
        df_trends['應收'] = df_trends['total_amount'].apply(lambda x: f"${x:,.0f}")
        df_trends['已收'] = df_trends['paid_amount'].apply(lambda x: f"${x:,.0f}")
        df_trends['收款率'] = df_trends['payment_rate'].apply(lambda x: f"{x:.1f}%")
        
        data_table(df_trends[['month', '應收', '已收', '收款率']], key="yearly_trends")


# ============== 主函數 ==============

def render(db):
    """主渲染函數"""
    st.title("💰 租金管理")
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "📝 單筆預填",
        "📋 批量預填",
        "✅ 繳費確認",
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
