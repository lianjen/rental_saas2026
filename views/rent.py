# views/rent.py (完整版 - 含房號篩選功能)
"""
租金管理頁面
職責：UI 展示與使用者互動，業務邏輯委派給 PaymentService
"""
import streamlit as st
from datetime import datetime
from services.payment_service import PaymentService
from services.logger import logger
from repository.tenant_repository import TenantRepository
import pandas as pd

# ============================================
# 主入口（供 main.py 呼叫）
# ============================================
def render(db):
    """主入口函式（供 main.py 動態載入使用）
    Args:
        db: SupabaseDB 實例（由 main.py 傳入）
    """
    render_rent_page()

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
        create_btn = st.button("🚀 一鍵建立排程", type="primary", width="stretch")
    
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
    """本月摘要頁籤（含房號篩選和單獨標記）"""
    st.subheader("📊 本月租金收款摘要")
    
    # === 期間與篩選 ===
    col1, col2, col3 = st.columns([2, 2, 3])
    
    with col1:
        year = st.selectbox("年份", range(2020, 2031), index=6)  # 預設 2026
    
    with col2:
        month = st.selectbox("月份", range(1, 13), index=datetime.now().month - 1)
    
    with col3:
        # 取得所有房間列表
        try:
            tenant_repo = TenantRepository()
            tenants = tenant_repo.get_active_tenants()
            room_list = sorted(set([t['room_number'] for t in tenants]))
            
            # 房號篩選（含「全部」選項）
            selected_room = st.selectbox(
                "🏠 房號篩選",
                options=["全部"] + room_list,
                key="monthly_room_filter"
            )
        except Exception as e:
            st.error(f"❌ 載入房間列表失敗: {str(e)}")
            selected_room = "全部"
    
    # === 取得資料 ===
    try:
        # 根據篩選條件取得資料
        if selected_room == "全部":
            summary = service.get_payment_summary(year, month)
            payments = service.payment_repo.get_by_period(year, month)
        else:
            # 取得單一房間的資料
            payments = service.payment_repo.get_by_room_and_period(selected_room, year, month)
            
            # 計算單一房間的摘要
            df = pd.DataFrame(payments) if payments else pd.DataFrame()
            if not df.empty:
                from dataclasses import dataclass
                @dataclass
                class RoomSummary:
                    total_expected: float
                    total_received: float
                    unpaid_count: int
                    overdue_count: int
                    collection_rate: float
                
                total_expected = df['amount'].sum()
                paid_df = df[df['status'] == 'paid']
                total_received = paid_df['paid_amount'].sum() if not paid_df.empty else 0
                unpaid_count = len(df[df['status'] == 'unpaid'])
                overdue_count = len(df[df['status'] == 'overdue'])
                collection_rate = total_received / total_expected if total_expected > 0 else 0
                
                summary = RoomSummary(
                    total_expected=total_expected,
                    total_received=total_received,
                    unpaid_count=unpaid_count,
                    overdue_count=overdue_count,
                    collection_rate=collection_rate
                )
            else:
                # 無資料時的空摘要
                from dataclasses import dataclass
                @dataclass
                class RoomSummary:
                    total_expected: float = 0
                    total_received: float = 0
                    unpaid_count: int = 0
                    overdue_count: int = 0
                    collection_rate: float = 0
                
                summary = RoomSummary()
        
        # === 顯示指標 ===
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "應收總額",
                f"${summary.total_expected:,.0f}",
                help="本月應繳租金總額"
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
        
        st.divider()
        
        # === 詳細列表 ===
        if selected_room == "全部":
            st.subheader("📋 本月繳費明細")
        else:
            st.subheader(f"📋 {selected_room} 房繳費明細")
        
        if not payments:
            st.info("📭 本月尚無租金記錄")
            return
        
        # 轉換為 DataFrame
        df = pd.DataFrame(payments)
        
        # 格式化日期
        if 'due_date' in df.columns:
            df['due_date'] = pd.to_datetime(df['due_date']).dt.strftime('%Y-%m-%d')
        if 'paid_date' in df.columns:
            df['paid_date'] = pd.to_datetime(df['paid_date'], errors='coerce').dt.strftime('%Y-%m-%d')
        
        # 狀態標記
        status_map = {'unpaid': '⏳ 未繳', 'paid': '✅ 已繳', 'overdue': '🚨 逾期'}
        df['status_display'] = df['status'].map(status_map).fillna(df['status'])
        
        # 顯示表格
        st.dataframe(
            df[[
                'room_number', 'tenant_name', 'amount',
                'due_date', 'status_display', 'payment_method'
            ]].rename(columns={
                'room_number': '房號',
                'tenant_name': '房客',
                'amount': '應繳金額',
                'due_date': '到期日',
                'status_display': '狀態',
                'payment_method': '繳款方式'
            }),
            use_container_width=True,
            hide_index=True
        )
        
        # === 標記功能 ===
        unpaid_df = df[df['status'] == 'unpaid']
        
        if not unpaid_df.empty:
            st.divider()
            
            if selected_room == "全部":
                st.subheader("✅ 批量標記已繳")
            else:
                st.subheader(f"✅ {selected_room} 房標記已繳")
            
            col1, col2, col3 = st.columns([4, 2, 2])
            
            with col1:
                # 初始化 session state
                if 'selected_monthly' not in st.session_state:
                    st.session_state.selected_monthly = []
                
                selected_ids = st.multiselect(
                    "選擇要標記為已繳的項目（可多選）",
                    options=unpaid_df['id'].tolist(),
                    default=st.session_state.selected_monthly,
                    format_func=lambda x: (
                        f"{unpaid_df[unpaid_df['id']==x]['room_number'].values[0]} - "
                        f"{unpaid_df[unpaid_df['id']==x]['tenant_name'].values[0]} "
                        f"(${unpaid_df[unpaid_df['id']==x]['amount'].values[0]:,.0f})"
                    ),
                    key="monthly_multiselect"
                )
                
                st.session_state.selected_monthly = selected_ids
            
            with col2:
                paid_amount = st.number_input(
                    "繳款金額",
                    min_value=0.0,
                    step=100.0,
                    help="留空則使用應繳金額",
                    key="monthly_paid_amount"
                )
            
            with col3:
                st.write("")
                st.write("")
            
            # 快速選擇按鈕
            col_btn1, col_btn2, col_btn3 = st.columns(3)
            
            with col_btn1:
                if st.button("📌 全選", use_container_width=True):
                    st.session_state.selected_monthly = unpaid_df['id'].tolist()
                    st.rerun()
            
            with col_btn2:
                if st.button("🔄 清除", use_container_width=True):
                    st.session_state.selected_monthly = []
                    st.rerun()
            
            # 標記按鈕
            with col_btn3:
                if st.button(
                    f"✅ 標記 ({len(selected_ids)})",
                    type="primary",
                    disabled=len(selected_ids) == 0,
                    use_container_width=True
                ):
                    with st.spinner("處理中..."):
                        try:
                            results = service.batch_mark_paid(
                                selected_ids,
                                paid_amount if paid_amount > 0 else None
                            )
                            
                            if results['success'] > 0:
                                st.success(f"✅ 成功標記 {results['success']} 筆")
                                st.session_state.selected_monthly = []
                                st.rerun()
                            
                            if results['failed'] > 0:
                                st.error(f"❌ 失敗 {results['failed']} 筆")
                        except Exception as e:
                            st.error(f"❌ 標記失敗: {str(e)}")
                            logger.error(f"批量標記失敗: {str(e)}", exc_info=True)
    
    except Exception as e:
        st.error(f"❌ 載入摘要失敗: {str(e)}")
        logger.error(f"載入摘要錯誤: {str(e)}", exc_info=True)

def render_payment_management_tab(service: PaymentService):
    """收款管理頁籤（含房號篩選）"""
    st.subheader("💳 收款管理")
    
    # === 篩選條件 ===
    col1, col2 = st.columns([3, 3])
    
    with col1:
        status_filter = st.radio(
            "篩選狀態",
            ["全部", "未繳", "已繳", "逾期"],
            horizontal=True
        )
    
    with col2:
        # 房號篩選
        try:
            tenant_repo = TenantRepository()
            tenants = tenant_repo.get_active_tenants()
            room_list = sorted(set([t['room_number'] for t in tenants]))
            
            selected_room = st.selectbox(
                "🏠 房號篩選",
                options=["全部"] + room_list,
                key="management_room_filter"
            )
        except Exception as e:
            st.error(f"❌ 載入房間列表失敗: {str(e)}")
            selected_room = "全部"
    
    # === 載入資料 ===
    try:
        # 先根據狀態取得資料
        if status_filter == "未繳":
            payments = service.get_unpaid_payments()
        elif status_filter == "逾期":
            payments = service.get_overdue_payments()
        elif status_filter == "已繳":
            payments = service.payment_repo.get_by_status('paid')
        else:
            payments = service.payment_repo.get_all_payments()
        
        # 再根據房號篩選
        if selected_room != "全部":
            payments = [p for p in payments if p['room_number'] == selected_room]
        
        if not payments:
            st.info("✅ 沒有符合條件的記錄")
            return
        
        # 轉換為 DataFrame
        df = pd.DataFrame(payments)
        df['due_date'] = pd.to_datetime(df['due_date']).dt.strftime('%Y-%m-%d')
        
        # 狀態顯示
        status_map = {'unpaid': '⏳ 未繳', 'paid': '✅ 已繳', 'overdue': '🚨 逾期'}
        df['status_display'] = df['status'].map(status_map).fillna(df['status'])
        
        # 顯示表格
        st.dataframe(
            df[[
                'room_number', 'tenant_name', 'payment_year',
                'payment_month', 'amount', 'due_date', 'status_display'
            ]].rename(columns={
                'room_number': '房號',
                'tenant_name': '房客',
                'payment_year': '年份',
                'payment_month': '月份',
                'amount': '金額',
                'due_date': '到期日',
                'status_display': '狀態'
            }),
            use_container_width=True,
            hide_index=True
        )
        
        # === 批量標記功能（只在「未繳」或「逾期」時顯示）===
        if status_filter in ["未繳", "逾期"]:
            st.divider()
            st.subheader("批量標記已繳")
            
            col1, col2, col3 = st.columns([3, 2, 2])
            
            with col1:
                selected_ids = st.multiselect(
                    "選擇要標記的記錄（可多選）",
                    options=df['id'].tolist(),
                    format_func=lambda x: (
                        f"{df[df['id']==x]['room_number'].values[0]} - "
                        f"{df[df['id']==x]['payment_year'].values[0]}/"
                        f"{df[df['id']==x]['payment_month'].values[0]:02d}"
                    )
                )
            
            with col2:
                paid_amount = st.number_input("繳款金額", min_value=0.0, step=100.0)
            
            with col3:
                st.write("")
                st.write("")
                if st.button("✅ 標記為已繳", disabled=len(selected_ids) == 0):
                    with st.spinner("處理中..."):
                        results = service.batch_mark_paid(selected_ids, paid_amount if paid_amount > 0 else None)
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

def render_tenant_history_report(service: PaymentService):
    """房客繳款歷史"""
    try:
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
    
    except Exception as e:
        st.error(f"❌ 載入失敗: {str(e)}")
        logger.error(f"房客歷史報表錯誤: {str(e)}", exc_info=True)

def render_annual_report(service: PaymentService):
    """年度統計報表"""
    st.info("🚧 年度統計報表開發中...")

# ============================================
# 本機測試入口
# ============================================
if __name__ == "__main__":
    render_rent_page()
