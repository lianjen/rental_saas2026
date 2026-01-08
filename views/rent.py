# views/rent.py (重構版 - 約 180 行)
"""
租金管理頁面
職責：UI 展示與使用者互動，業務邏輯委派給 PaymentService
"""
import streamlit as st
from datetime import datetime
from services.payment_service import PaymentService
from services.logger import logger
import pandas as pd

def render_rent_page():
    """渲染租金管理主頁面"""
    st.title("💰 租金管理")
    
    service = PaymentService()
    
    # 頁籤
    tab1, tab2, tab3, tab4 = st.tabs([
        "📅 批量建立排程",
        "📊 本月摘要",
        "💳 收款管理",
        "📈 報表分析"
    ])
    
    with tab1:
        render_batch_schedule_tab(service)
    
    with tab2:
        render_monthly_summary_tab(service)
    
    with tab3:
        render_payment_management_tab(service)
    
    with tab4:
        render_reports_tab(service)


def render_batch_schedule_tab(service: PaymentService):
    """批量建立排程頁籤"""
    st.subheader("📅 批量建立月租金排程")
    st.info("💡 一鍵為所有房客建立指定月份的租金記錄")
    
    col1, col2, col3 = st.columns([2, 2, 3])
    
    with col1:
        year = st.number_input(
            "年份",
            min_value=2020,
            max_value=2030,
            value=datetime.now().year,
            step=1
        )
    
    with col2:
        month = st.number_input(
            "月份",
            min_value=1,
            max_value=12,
            value=datetime.now().month,
            step=1
        )
    
    with col3:
        st.write("")  # 對齊
        st.write("")
        create_btn = st.button("🚀 一鍵建立排程", type="primary", use_container_width=True)
    
    if create_btn:
        with st.spinner(f"正在建立 {year}/{month:02d} 的租金排程..."):
            try:
                results = service.create_monthly_schedule_batch(year, month)
                
                st.success(
                    f"✅ 排程建立完成！\n\n"
                    f"• 新增：{results['created']} 筆\n"
                    f"• 跳過：{results['skipped']} 筆（已存在）\n"
                    f"• 失敗：{results['errors']} 筆"
                )
                
                if results['errors'] > 0:
                    st.warning("⚠️ 部分排程建立失敗，請檢查日誌或聯繫管理員")
                
                logger.info(f"使用者批量建立排程: {year}/{month} - {results}")
                
            except Exception as e:
                st.error(f"❌ 建立失敗: {str(e)}")
                logger.error(f"批量建立排程錯誤: {str(e)}", exc_info=True)


def render_monthly_summary_tab(service: PaymentService):
    """本月摘要頁籤"""
    st.subheader("📊 本月租金收款摘要")
    
    # 選擇期間
    col1, col2 = st.columns(2)
    with col1:
        year = st.selectbox("年份", range(2020, 2031), index=6)  # 預設 2026
    with col2:
        month = st.selectbox("月份", range(1, 13), index=datetime.now().month - 1)
    
    # 取得摘要資料
    try:
        summary = service.get_payment_summary(year, month)
        
        # 顯示關鍵指標
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "應收總額",
                f"${summary.total_expected:,.0f}",
                help="本月所有房客應繳租金總額"
            )
        
        with col2:
            st.metric(
                "實收總額",
                f"${summary.total_received:,.0f}",
                delta=f"{summary.collection_rate:.1%}",
                help="已收到的租金金額與收款率"
            )
        
        with col3:
            st.metric(
                "待收",
                f"{summary.unpaid_count} 筆",
                help="尚未繳款的租金記錄數"
            )
        
        with col4:
            st.metric(
                "逾期",
                f"{summary.overdue_count} 筆",
                delta="-" if summary.overdue_count > 0 else "正常",
                delta_color="inverse",
                help="已超過到期日的未繳款記錄"
            )
        
        # 進度條
        st.progress(summary.collection_rate)
        st.caption(f"收款進度：{summary.collection_rate:.1%}")
        
    except Exception as e:
        st.error(f"❌ 載入摘要失敗: {str(e)}")
        logger.error(f"載入摘要錯誤: {str(e)}", exc_info=True)


def render_payment_management_tab(service: PaymentService):
    """收款管理頁籤"""
    st.subheader("💳 收款管理")
    
    # 篩選條件
    status_filter = st.radio(
        "篩選狀態",
        ["全部", "未繳", "已繳", "逾期"],
        horizontal=True
    )
    
    # 載入資料
    try:
        if status_filter == "未繳":
            payments = service.get_unpaid_payments()
        elif status_filter == "逾期":
            payments = service.get_overdue_payments()
        else:
            # 全部或已繳需要額外實作
            st.info("此篩選尚未完整實作，請選擇「未繳」或「逾期」")
            return
        
        if not payments:
            st.info("✅ 沒有符合條件的記錄")
            return
        
        # 轉換為 DataFrame
        df = pd.DataFrame(payments)
        df['due_date'] = pd.to_datetime(df['due_date']).dt.strftime('%Y-%m-%d')
        
        # 顯示表格
        st.dataframe(
            df[[
                'room_number', 'tenant_name', 'payment_year', 
                'payment_month', 'amount', 'due_date', 'status'
            ]],
            use_container_width=True,
            hide_index=True
        )
        
        # 批量標記功能
        st.divider()
        st.subheader("批量標記已繳")
        
        col1, col2, col3 = st.columns([3, 2, 2])
        
        with col1:
            selected_ids = st.multiselect(
                "選擇要標記的記錄（可多選）",
                options=df['id'].tolist(),
                format_func=lambda x: f"{df[df['id']==x]['room_number'].values[0]} - "
                                     f"{df[df['id']==x]['payment_year'].values[0]}/"
                                     f"{df[df['id']==x]['payment_month'].values[0]:02d}"
            )
        
        with col2:
            paid_amount = st.number_input("繳款金額", min_value=0.0, step=100.0)
        
        with col3:
            st.write("")
            st.write("")
            if st.button("✅ 標記為已繳", disabled=len(selected_ids) == 0):
                with st.spinner("處理中..."):
                    results = service.batch_mark_paid(selected_ids, paid_amount)
                    st.success(
                        f"✅ 完成！成功 {results['success']} 筆，失敗 {results['failed']} 筆"
                    )
                    st.rerun()
        
    except Exception as e:
        st.error(f"❌ 載入資料失敗: {str(e)}")
        logger.error(f"收款管理錯誤: {str(e)}", exc_info=True)


def render_reports_tab(service: PaymentService):
    """報表分析頁籤"""
    st.subheader("📈 報表分析")
    
    report_type = st.selectbox(
        "報表類型",
        ["月度收款趨勢", "房客繳款歷史", "年度統計"]
    )
    
    if report_type == "月度收款趨勢":
        render_monthly_trend_report(service)
    elif report_type == "房客繳款歷史":
        render_tenant_history_report(service)
    elif report_type == "年度統計":
        render_annual_report(service)


def render_monthly_trend_report(service: PaymentService):
    """月度趨勢報表"""
    st.info("🚧 月度趨勢報表開發中...")
    # TODO: 實作最近 6 個月的收款趨勢圖表


def render_tenant_history_report(service: PaymentService):
    """房客繳款歷史"""
    from repository.tenant_repository import TenantRepository
    
    tenant_repo = TenantRepository()
    tenants = tenant_repo.get_active_tenants()
    
    if not tenants:
        st.warning("沒有活躍房客")
        return
    
    # 選擇房客
    tenant_options = {
        t['room_number']: f"{t['room_number']} - {t['tenant_name']}"
        for t in tenants
    }
    
    selected_room = st.selectbox(
        "選擇房客",
        options=list(tenant_options.keys()),
        format_func=lambda x: tenant_options[x]
    )
    
    # 載入歷史
    history = service.get_tenant_payment_history(selected_room, limit=12)
    
    if history:
        df = pd.DataFrame(history)
        st.dataframe(
            df[[
                'payment_year', 'payment_month', 'amount', 
                'status', 'paid_date', 'due_date'
            ]],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("此房客尚無繳款記錄")


def render_annual_report(service: PaymentService):
    """年度統計報表"""
    st.info("🚧 年度統計報表開發中...")
    # TODO: 實作年度總收入、收款率等統計


# 主入口（供 main.py 呼叫）
if __name__ == "__main__":
    render_rent_page()
