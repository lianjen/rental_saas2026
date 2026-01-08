import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta
from services.payment_service import PaymentService
from services.db import SupabaseDB
import logging
import time

logger = logging.getLogger(__name__)

def render_rent_page():
    """租金管理主頁面"""
    st.title("💰 租金管理系統")
    
    # 初始化 Service 和 Database (加入錯誤處理)
    try:
        service = PaymentService()
        db = SupabaseDB()
    except Exception as e:
        st.error("❌ 資料庫連線失敗，請檢查網路連線或 .env 設定檔。")
        st.error(f"詳細錯誤: {str(e)}")
        logger.error(f"Database connection error: {e}")
        return

    # 建立 Tab
    tab1, tab2, tab3, tab4 = st.tabs(["📅 建立排程", "📊 本月摘要", "💳 收款管理", "📈 報表分析"])
    
    with tab1:
        render_schedule_tab(service, db)
    
    with tab2:
        render_summary_tab(service, db)
    
    with tab3:
        render_payment_tab(service, db)
    
    with tab4:
        render_report_tab(service, db)


def render_schedule_tab(service: PaymentService, db: SupabaseDB):
    """Tab 1: 建立排程"""
    st.subheader("📅 批量建立月租金排程")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        year = st.number_input(
            "年份",
            value=datetime.now().year,
            min_value=2020,
            max_value=2030,
            key="schedule_year"
        )
    
    with col2:
        month = st.number_input(
            "月份",
            value=datetime.now().month,
            min_value=1,
            max_value=12,
            key="schedule_month"
        )
    
    with col3:
        st.empty()
    
    st.divider()
    
    # 建立排程按鈕
    if st.button("🚀 一鍵建立排程", type="primary", use_container_width=False):
        with st.spinner(f"正在建立 {year} 年 {month} 月的租金排程..."):
            try:
                results = service.create_monthly_schedule(year, month)
                
                # 顯示結果
                col_result1, col_result2, col_result3 = st.columns(3)
                with col_result1:
                    st.metric("✅ 新增筆數", results['created'])
                with col_result2:
                    st.metric("⏭️ 跳過筆數", results['skipped'])
                with col_result3:
                    st.metric("❌ 失敗筆數", results['errors'])
                
                if results['created'] > 0:
                    st.success(f"✅ 成功建立 {results['created']} 筆租金排程！")
                    st.balloons()
                
                if results['skipped'] > 0:
                    st.info(f"⏭️ 跳過 {results['skipped']} 筆已存在的排程")
                
                if results['errors'] > 0:
                    st.warning(f"⚠️ {results['errors']} 筆建立失敗，請查看日誌")
            
            except Exception as e:
                st.error(f"❌ 建立失敗：{str(e)}")
                logger.error(f"Create schedule error: {e}")
    
    st.divider()
    
    # 顯示預計建立的排程預覽
    st.subheader("📋 預計建立的排程預覽")
    
    try:
        tenants_df = db.get_tenants()
        
        if not tenants_df.empty:
            preview_data = []
            for idx, tenant in tenants_df.iterrows():
                # 簡單防呆：確保必要欄位存在
                if 'base_rent' not in tenant:
                    continue

                rent_detail = service.calculate_rent_detail(tenant.to_dict())
                preview_data.append({
                    "房號": tenant.get('room_number', '未知'),
                    "房客": tenant.get('tenant_name', '未知'),
                    "基本月租": f"${tenant.get('base_rent', 0):,.0f}",
                    "計算月租": f"${rent_detail.get('monthly_rent', 0):,.0f}",
                    "繳款方式": tenant.get('payment_method', '月繳'),
                    "狀態": "✅ 有效" if tenant.get('is_active', True) else "❌ 已停用"
                })
            
            preview_df = pd.DataFrame(preview_data)
            st.dataframe(preview_df, use_container_width=True, hide_index=True)
            st.info(f"📌 共 {len(preview_data)} 位房客")
        else:
            st.info("📌 目前沒有房客資料，請先新增房客")
    
    except Exception as e:
        st.warning(f"無法顯示預覽：{str(e)}")


def render_summary_tab(service: PaymentService, db: SupabaseDB):
    """Tab 2: 本月摘要"""
    st.subheader("📊 本月收款摘要")
    
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    try:
        summary = service.get_payment_summary(current_year, current_month)
        
        # 顯示四個關鍵指標
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "💰 應收總額",
                f"${summary['total_expected']:,.0f}"
            )
        
        with col2:
            delta_value = summary['total_expected'] - summary['total_received']
            st.metric(
                "✅ 實收總額",
                f"${summary['total_received']:,.0f}",
                delta=f"差 ${delta_value:,.0f}"
            )
        
        with col3:
            st.metric(
                "📊 收款率",
                f"{summary['collection_rate']:.1%}"
            )
        
        with col4:
            unpaid_total = summary['unpaid_count'] + summary['overdue_count']
            st.metric(
                "⚠️ 待繳筆數",
                f"{unpaid_total}",
                delta=f"逾期 {summary['overdue_count']}"
            )
        
        st.divider()
        
        # 詳細數據表
        st.subheader("📋 待繳清單")
        
        unpaid_df = db.get_payment_schedule(
            year=current_year,
            month=current_month,
            status='unpaid'
        )
        
        if not unpaid_df.empty:
            display_df = unpaid_df[['room_number', 'tenant_name', 'amount', 'due_date', 'status']].copy()
            display_df.columns = ['房號', '房客', '金額', '到期日期', '狀態']
            display_df['金額'] = display_df['金額'].apply(lambda x: f"${x:,.0f}")
            display_df['狀態'] = display_df['狀態'].apply(lambda x: '⏰ 待繳' if x == 'unpaid' else '⚠️ 逾期')
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.success("✅ 本月所有租金都已收齊！")
        
        # 逾期清單
        st.subheader("⚠️ 逾期清單")
        overdue_df = db.get_payment_schedule(
            year=current_year,
            month=current_month,
            status='overdue'
        )
        
        if not overdue_df.empty:
            overdue_display = overdue_df[['room_number', 'tenant_name', 'amount', 'due_date']].copy()
            overdue_display.columns = ['房號', '房客', '金額', '到期日期']
            overdue_display['金額'] = overdue_display['金額'].apply(lambda x: f"${x:,.0f}")
            
            st.dataframe(overdue_display, use_container_width=True, hide_index=True)
        else:
            st.success("✅ 沒有逾期記錄")
    
    except Exception as e:
        st.error(f"❌ 獲取摘要資料失敗：{str(e)}")
        logger.error(f"Get summary error: {e}")


def render_payment_tab(service: PaymentService, db: SupabaseDB):
    """Tab 3: 收款管理"""
    st.subheader("💳 收款管理")
    
    # 篩選器
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
            [None, 'unpaid', 'paid', 'overdue'],
            format_func=lambda x: "全部" if x is None else {'unpaid': '待繳', 'paid': '已繳', 'overdue': '逾期'}.get(x),
            key="pay_status"
        )
    
    with col4:
        try:
            tenants_list = db.get_tenants()
            room_options = [None] + (tenants_list['room_number'].tolist() if not tenants_list.empty else [])
        except:
            room_options = [None]
            
        filter_room = st.selectbox(
            "房號",
            room_options,
            format_func=lambda x: "全部" if x is None else str(x),
            key="pay_room"
        )
    
    st.divider()
    
    try:
        # 取得篩選後的資料
        df = db.get_payment_schedule(
            year=filter_year,
            month=filter_month,
            status=filter_status,
            room=filter_room
        )
        
        if df.empty:
            st.info("📌 沒有符合條件的記錄")
            return
        
        # 顯示統計資訊
        stats = service.get_payment_summary(
            filter_year or datetime.now().year,
            filter_month or datetime.now().month
        )
        
        col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
        with col_stat1:
            st.metric("應收", f"${stats['total_expected']:,.0f}")
        with col_stat2:
            st.metric("實收", f"${stats['total_received']:,.0f}")
        with col_stat3:
            st.metric("待繳", f"${stats['total_expected'] - stats['total_received']:,.0f}")
        with col_stat4:
            st.metric("收款率", f"{stats['collection_rate']:.1%}")
        
        st.divider()
        
        # 顯示詳細列表
        st.subheader("📋 詳細清單")
        
        display_df = df[['id', 'room_number', 'tenant_name', 'payment_year', 'payment_month', 'amount', 'due_date', 'status']].copy()
        display_df.columns = ['ID', '房號', '房客', '年', '月', '金額', '到期日', '狀態']
        display_df['金額'] = display_df['金額'].apply(lambda x: f"${x:,.0f}")
        display_df['狀態'] = display_df['狀態'].apply(lambda x: {'unpaid': '⏰ 待繳', 'paid': '✅ 已繳', 'overdue': '⚠️ 逾期'}.get(x, x))
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        # 批量標記為已繳
        st.divider()
        st.subheader("✅ 批量標記為已繳")
        
        unpaid_df = db.get_payment_schedule(status='unpaid')
        
        if not unpaid_df.empty:
            # 建立選項標籤
            options_map = {
                row['id']: f"{row['room_number']} - {row['tenant_name']} ({row['payment_year']}/{row['payment_month']})"
                for _, row in unpaid_df.iterrows()
            }
            
            selected_ids = st.multiselect(
                "選擇要標記的記錄",
                options=list(options_map.keys()),
                format_func=lambda x: options_map.get(x, str(x)),
                key="batch_mark_ids"
            )
            
            col_mark_btn, col_paid_amount, col_paid_date = st.columns(3)
            
            with col_mark_btn:
                # 按鈕邏輯
                if st.button("✅ 確認標記", type="primary"):
                    if len(selected_ids) > 0:
                        # 這裡要小心，如果是批量不同金額，應該要自動帶入該筆應繳金額
                        # 但介面設計是統一輸入一個金額，這裡假設是「全額繳清」或手動輸入
                        # 使用 session_state 來取得右側輸入框的值可能會比較慢更新，直接取值
                        pass
                    else:
                        st.warning("請先選擇要標記的記錄")

            # 輸入框移到外面確保值能被讀取，或者在button內讀取session_state
            # 為了簡單起見，直接渲染輸入框
            with col_paid_amount:
                paid_amount = st.number_input("繳款金額 (0=自動帶入應繳額)", min_value=0, step=100, key="paid_amt")
                st.caption("若輸入 0，系統將自動填入該筆記錄的應繳金額")
                
            with col_paid_date:
                paid_date = st.date_input("繳款日期", value=date.today(), key="paid_dt")
            
            # 實際執行邏輯 (檢查完輸入後)
            if st.session_state.get("batch_mark_ids") and st.button("🚀 執行標記", key="confirm_pay"):
                 with st.spinner("正在標記..."):
                    success_count = 0
                    fail_count = 0
                    
                    for payment_id in selected_ids:
                        try:
                            # 獲取該筆記錄的應繳金額 (如果使用者輸入0)
                            final_amount = paid_amount
                            if final_amount == 0:
                                current_record = unpaid_df[unpaid_df['id'] == payment_id]
                                if not current_record.empty:
                                    final_amount = current_record.iloc[0]['amount']
                            
                            result = service.mark_as_paid(
                                payment_id,
                                final_amount,
                                datetime.combine(paid_date, datetime.min.time())
                            )
                            if result:
                                success_count += 1
                            else:
                                fail_count += 1
                        except Exception as e:
                            fail_count += 1
                            logger.error(f"Mark payment {payment_id} failed: {e}")
                    
                    # --- 這裡是你原本發生縮排錯誤的地方 (已修復) ---
                    if success_count > 0:
                        st.success(f"✅ 成功標記 {success_count} 筆為已繳！")
                    
                    if fail_count > 0:
                        st.warning(f"⚠️ {fail_count} 筆標記失敗")
                    
                    time.sleep(1)
                    st.rerun()

        else:
            st.success("✅ 所有租金都已收齊！")
    
    except Exception as e:
        st.error(f"❌ 獲取資料失敗：{str(e)}")
        logger.error(f"Get payment data error: {e}")


def render_report_tab(service: PaymentService, db: SupabaseDB):
    """Tab 4: 報表分析"""
    st.subheader("📈 收款報表分析")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        report_year = st.selectbox(
            "選擇年份",
            range(2020, 2031),
            index=datetime.now().year - 2020,
            key="report_year"
        )
    
    with col2:
        report_month = st.selectbox(
            "選擇月份",
            range(1, 13),
            index=datetime.now().month - 1,
            key="report_month"
        )
    
    with col3:
        report_type = st.radio(
            "報表類型",
            ["月度摘要", "年度趨勢", "房客對比"],
            horizontal=True,
            key="report_type"
        )
    
    st.divider()
    
    try:
        if report_type == "月度摘要":
            render_monthly_report(service, db, report_year, report_month)
        
        elif report_type == "年度趨勢":
            render_annual_report(service, db, report_year)
        
        elif report_type == "房客對比":
            render_tenant_comparison(service, db, report_year, report_month)
    
    except Exception as e:
        st.error(f"❌ 報表生成失敗：{str(e)}")
        logger.error(f"Report generation error: {e}")


def render_monthly_report(service: PaymentService, db: SupabaseDB, year: int, month: int):
    """月度摘要報表"""
    st.subheader(f"📊 {year} 年 {month} 月 收款摘要")
    
    summary = service.get_payment_summary(year, month)
    
    if summary['total_expected'] == 0:
        st.info("📌 該月份沒有資料")
        return
    
    # 關鍵指標
    col_k1, col_k2, col_k3, col_k4 = st.columns(4)
    
    with col_k1:
        st.metric("💰 應收總額", f"${summary['total_expected']:,.0f}")
    
    with col_k2:
        st.metric("✅ 實收總額", f"${summary['total_received']:,.0f}")
    
    with col_k3:
        st.metric("⏰ 待繳金額", f"${summary['total_expected'] - summary['total_received']:,.0f}")
    
    with col_k4:
        st.metric("📊 收款率", f"{summary['collection_rate']:.1%}")
    
    st.divider()
    
    # 清單
    st.subheader("詳細清單")
    df = db.get_payment_schedule(year=year, month=month)
    
    if not df.empty:
        display_df = df[['room_number', 'tenant_name', 'amount', 'paid_amount', 'due_date', 'status']].copy()
        display_df.columns = ['房號', '房客', '應繳金額', '實繳金額', '到期日', '狀態']
        display_df['應繳金額'] = display_df['應繳金額'].apply(lambda x: f"${x:,.0f}")
        display_df['實繳金額'] = display_df['實繳金額'].apply(lambda x: f"${x:,.0f}" if x else "$0")
        display_df['狀態'] = display_df['狀態'].apply(lambda x: {'unpaid': '⏰ 待繳', 'paid': '✅ 已繳', 'overdue': '⚠️ 逾期'}.get(x, x))
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    # 下載報表
    if not df.empty:
        csv = df.to_csv(index=False)
        st.download_button(
            label="📥 下載 CSV 報表",
            data=csv,
            file_name=f"rent_report_{year}_{month:02d}.csv",
            mime="text/csv"
        )


def render_annual_report(service: PaymentService, db: SupabaseDB, year: int):
    """年度趨勢報表"""
    st.subheader(f"📈 {year} 年 收款趨勢")
    
    # 收集全年數據
    monthly_data = []
    for month in range(1, 13):
        summary = service.get_payment_summary(year, month)
        if summary['total_expected'] > 0:
            monthly_data.append({
                '月份': month,
                '應收': summary['total_expected'],
                '實收': summary['total_received'],
                '待繳': summary['total_expected'] - summary['total_received'],
                '收款率': summary['collection_rate']
            })
    
    if not monthly_data:
        st.info("📌 該年份沒有資料")
        return
    
    trend_df = pd.DataFrame(monthly_data)
    
    # 顯示關鍵指標
    col_annual1, col_annual2, col_annual3 = st.columns(3)
    
    with col_annual1:
        st.metric("全年應收", f"${trend_df['應收'].sum():,.0f}")
    
    with col_annual2:
        st.metric("全年實收", f"${trend_df['實收'].sum():,.0f}")
    
    with col_annual3:
        avg_rate = (trend_df['實收'].sum() / trend_df['應收'].sum()) if trend_df['應收'].sum() > 0 else 0
        st.metric("平均收款率", f"{avg_rate:.1%}")
    
    st.divider()
    
    # 趨勢圖表
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.subheader("💰 應收 vs 實收趨勢")
        st.line_chart(trend_df.set_index('月份')[['應收', '實收']])
    
    with col_chart2:
        st.subheader("📊 收款率趨勢")
        rate_data = trend_df[['月份', '收款率']].copy()
        rate_data['收款率'] = rate_data['收款率'] * 100
        st.line_chart(rate_data.set_index('月份'))
    
    st.divider()
    
    # 月份對比表
    st.subheader("📋 月份對比表")
    display_annual = trend_df.copy()
    display_annual['應收'] = display_annual['應收'].apply(lambda x: f"${x:,.0f}")
    display_annual['實收'] = display_annual['實收'].apply(lambda x: f"${x:,.0f}")
    display_annual['待繳'] = display_annual['待繳'].apply(lambda x: f"${x:,.0f}")
    display_annual['收款率'] = display_annual['收款率'].apply(lambda x: f"{x:.1%}")
    
    st.dataframe(display_annual, use_container_width=True, hide_index=True)


def render_tenant_comparison(service: PaymentService, db: SupabaseDB, year: int, month: int):
    """房客對比報表"""
    st.subheader(f"👥 {year} 年 {month} 月 房客對比分析")
    
    df = db.get_payment_schedule(year=year, month=month)
    
    if df.empty:
        st.info("📌 該月份沒有資料")
        return
    
    # 按房客統計
    tenant_stats = df.groupby('tenant_name').agg({
        'room_number': 'first',
        'amount': 'sum',
        'paid_amount': lambda x: x.sum() if x.sum() else 0,
        'status': lambda x: 'paid' if all(s == 'paid' for s in x) else ('overdue' if any(s == 'overdue' for s in x) else 'unpaid')
    }).reset_index()
    
    tenant_stats['待繳'] = tenant_stats['amount'] - tenant_stats['paid_amount']
    # 處理除以零的情況
    tenant_stats['完成度'] = tenant_stats.apply(lambda x: (x['paid_amount'] / x['amount']) if x['amount'] > 0 else 0, axis=1)
    tenant_stats['完成度_fmt'] = tenant_stats['完成度'].apply(lambda x: f"{x:.1%}")
    
    # 按待繳金額排序
    tenant_stats = tenant_stats.sort_values('待繳', ascending=False)
    
    # 關鍵指標
    col_t1, col_t2, col_t3 = st.columns(3)
    
    with col_t1:
        st.metric("📌 總房客數", len(tenant_stats))
    
    with col_t2:
        paid_count = (tenant_stats['待繳'] == 0).sum()
        st.metric("✅ 已繳房客", paid_count)
    
    with col_t3:
        unpaid_count = (tenant_stats['待繳'] > 0).sum()
        st.metric("⏰ 待繳房客", unpaid_count)
    
    st.divider()
    
    # 顯示對比表
    st.subheader("📊 房客繳款情況")
    
    display_tenant = tenant_stats[['room_number', 'tenant_name', 'amount', 'paid_amount', '待繳', '完成度_fmt', 'status']].copy()
    display_tenant.columns = ['房號', '房客', '應繳', '實繳', '待繳', '完成度', '狀態']
    display_tenant['應繳'] = display_tenant['應繳'].apply(lambda x: f"${x:,.0f}")
    display_tenant['實繳'] = display_tenant['實繳'].apply(lambda x: f"${x:,.0f}")
    display_tenant['待繳'] = display_tenant['待繳'].apply(lambda x: f"${x:,.0f}")
    display_tenant['狀態'] = display_tenant['狀態'].apply(lambda x: {'paid': '✅ 已繳', 'unpaid': '⏰ 待繳', 'overdue': '⚠️ 逾期'}.get(x, x))
    
    st.dataframe(display_tenant[['房號', '房客', '應繳', '實繳', '待繳', '完成度', '狀態']], use_container_width=True, hide_index=True)
    
    # 視覺化
    st.divider()
    st.subheader("📈 待繳金額排行")
    
    chart_data = tenant_stats[['room_number', '待繳']].copy()
    chart_data.columns = ['房號', '待繳金額']
    chart_data = chart_data.sort_values('待繳金額', ascending=True)
    
    if not chart_data.empty and chart_data['待繳金額'].sum() > 0:
        st.bar_chart(chart_data.set_index('房號'))
    else:
        st.success("✅ 所有房客都已繳清！")


# Main 執行區
if __name__ == "__main__":
    st.set_page_config(page_title="💰 租金管理", layout="wide")
    render_rent_page()

