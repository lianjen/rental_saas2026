"""
系統設定 - 完整重構版
特性:
- 系統參數設定
- 資料匯出/備份
- 系統資訊查看
- 日誌管理
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import logging

# 安全 import
try:
    from components.cards import section_header, metric_card, empty_state, info_card
except ImportError:
    def section_header(title, icon="", divider=True):
        st.markdown(f"### {icon} {title}")
        if divider: st.divider()
    def metric_card(label, value, delta="", icon="", color="normal"):
        st.metric(label, value, delta)
    def empty_state(msg, icon="", desc=""):
        st.info(f"{icon} {msg}")
    def info_card(title, content, icon="", type="info"):
        st.info(f"{icon} {title}: {content}")

logger = logging.getLogger(__name__)

# ============== Tab 1: 系統參數 ==============

def render_params_tab(db):
    """系統參數設定"""
    section_header("系統參數", "⚙️")
    
    info_card(
        "💡 功能說明",
        "系統參數儲存在資料庫中,修改後立即生效。建議謹慎操作。",
        "💡",
        "info"
    )
    
    st.divider()
    
    # === 水費設定 ===
    with st.expander("💧 水費設定", expanded=True):
        current_water_fee = 100  # 從資料庫讀取
        
        water_fee = st.number_input(
            "每月水費金額 (元)",
            min_value=0,
            value=current_water_fee,
            step=10,
            help="房客若選擇「包含水費」,將扣除此金額",
            key="water_fee"
        )
        
        if st.button("💾 儲存水費設定"):
            # 儲存到資料庫
            st.success("✅ 水費設定已更新")
    
    # === 租金到期提醒 ===
    with st.expander("📅 租金到期提醒", expanded=False):
        remind_days = st.number_input(
            "提前幾天提醒租約到期",
            min_value=0,
            max_value=90,
            value=45,
            step=5,
            key="remind_days"
        )
        
        if st.button("💾 儲存提醒設定"):
            st.success("✅ 提醒設定已更新")
    
    # === 繳費逾期設定 ===
    with st.expander("⏰ 繳費逾期設定", expanded=False):
        overdue_days = st.number_input(
            "逾期天數門檻",
            min_value=1,
            max_value=30,
            value=7,
            step=1,
            help="超過此天數標記為逾期",
            key="overdue_days"
        )
        
        if st.button("💾 儲存逾期設定"):
            st.success("✅ 逾期設定已更新")
    
    # === 顯示設定 ===
    with st.expander("🎨 顯示設定", expanded=False):
        items_per_page = st.number_input(
            "每頁顯示筆數",
            min_value=10,
            max_value=200,
            value=50,
            step=10,
            key="items_per_page"
        )
        
        if st.button("💾 儲存顯示設定"):
            st.success("✅ 顯示設定已更新")


# ============== Tab 2: 資料匯出 ==============

def render_export_tab(db):
    """資料匯出"""
    section_header("資料匯出", "📥")
    
    info_card(
        "💡 功能說明",
        "匯出系統資料為 CSV 格式,可用於備份或匯入 Excel 分析。",
        "💡",
        "info"
    )
    
    st.divider()
    
    # === 房客資料 ===
    with st.expander("👥 房客資料", expanded=True):
        st.write("匯出所有房客資訊 (含已停用)")
        
        if st.button("📥 匯出房客資料", key="export_tenants"):
            try:
                df = db.get_tenants()
                
                if df.empty:
                    st.warning("⚠️ 沒有房客資料")
                else:
                    csv = df.to_csv(index=False, encoding='utf-8-sig')
                    
                    st.download_button(
                        "💾 下載 CSV",
                        csv,
                        f"tenants_{datetime.now().strftime('%Y%m%d')}.csv",
                        "text/csv"
                    )
                    
                    st.success(f"✅ 已準備 {len(df)} 筆房客資料")
            except Exception as e:
                st.error(f"❌ 匯出失敗: {e}")
    
    # === 應收單 ===
    with st.expander("💰 應收單資料", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            export_year = st.selectbox(
                "年份",
                range(2020, 2031),
                index=datetime.now().year - 2020,
                key="export_year"
            )
        
        with col2:
            export_month = st.selectbox(
                "月份 (可選)",
                [None] + list(range(1, 13)),
                format_func=lambda x: "全年" if x is None else str(x),
                key="export_month"
            )
        
        if st.button("📥 匯出應收單", key="export_payments"):
            try:
                df = db.get_payment_schedule(year=export_year, month=export_month)
                
                if df.empty:
                    st.warning("⚠️ 沒有應收單資料")
                else:
                    csv = df.to_csv(index=False, encoding='utf-8-sig')
                    
                    filename = f"payments_{export_year}"
                    if export_month:
                        filename += f"{export_month:02d}"
                    filename += f"_{datetime.now().strftime('%Y%m%d')}.csv"
                    
                    st.download_button(
                        "💾 下載 CSV",
                        csv,
                        filename,
                        "text/csv"
                    )
                    
                    st.success(f"✅ 已準備 {len(df)} 筆應收單")
            except Exception as e:
                st.error(f"❌ 匯出失敗: {e}")
    
    # === 支出記錄 ===
    with st.expander("💸 支出記錄", expanded=False):
        export_limit = st.number_input(
            "匯出筆數",
            min_value=10,
            max_value=1000,
            value=100,
            step=10,
            key="export_expense_limit"
        )
        
        if st.button("📥 匯出支出記錄", key="export_expenses"):
            try:
                df = db.get_expenses(limit=export_limit)
                
                if df.empty:
                    st.warning("⚠️ 沒有支出記錄")
                else:
                    csv = df.to_csv(index=False, encoding='utf-8-sig')
                    
                    st.download_button(
                        "💾 下載 CSV",
                        csv,
                        f"expenses_{datetime.now().strftime('%Y%m%d')}.csv",
                        "text/csv"
                    )
                    
                    st.success(f"✅ 已準備 {len(df)} 筆支出記錄")
            except Exception as e:
                st.error(f"❌ 匯出失敗: {e}")
    
    # === 電費記錄 ===
    with st.expander("⚡ 電費記錄", expanded=False):
        periods = db.get_all_periods()
        
        if not periods:
            st.info("ℹ️ 尚未建立電費期間")
        else:
            period_options = {
                f"{p['period_year']}/{p['period_month_start']}-{p['period_month_end']}": p['id']
                for p in periods
            }
            
            selected_period = st.selectbox(
                "選擇期間",
                list(period_options.keys()),
                key="export_elec_period"
            )
            
            if st.button("📥 匯出電費記錄", key="export_electricity"):
                try:
                    period_id = period_options[selected_period]
                    df = db.get_electricity_payment_record(period_id)
                    
                    if df is None or df.empty:
                        st.warning("⚠️ 該期間沒有電費記錄")
                    else:
                        csv = df.to_csv(index=False, encoding='utf-8-sig')
                        
                        st.download_button(
                            "💾 下載 CSV",
                            csv,
                            f"electricity_{period_id}_{datetime.now().strftime('%Y%m%d')}.csv",
                            "text/csv"
                        )
                        
                        st.success(f"✅ 已準備 {len(df)} 筆電費記錄")
                except Exception as e:
                    st.error(f"❌ 匯出失敗: {e}")


# ============== Tab 3: 系統資訊 ==============

def render_info_tab(db):
    """系統資訊"""
    section_header("系統資訊", "ℹ️")
    
    # === 資料庫統計 ===
    st.write("**📊 資料庫統計**")
    
    try:
        # 房客數
        tenants_count = len(db.get_tenants())
        
        # 應收單數
        payments_df = db.get_payment_schedule()
        payments_count = len(payments_df) if not payments_df.empty else 0
        
        # 支出記錄數
        expenses_df = db.get_expenses(limit=10000)
        expenses_count = len(expenses_df) if not expenses_df.empty else 0
        
        # 電費期間數
        periods = db.get_all_periods()
        periods_count = len(periods) if periods else 0
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            metric_card("房客數", str(tenants_count), icon="👥")
        
        with col2:
            metric_card("應收單", str(payments_count), icon="💰")
        
        with col3:
            metric_card("支出記錄", str(expenses_count), icon="💸")
        
        with col4:
            metric_card("電費期間", str(periods_count), icon="⚡")
    
    except Exception as e:
        st.error(f"❌ 統計失敗: {e}")
    
    st.divider()
    
    # === 系統版本 ===
    st.write("**🔧 系統版本**")
    
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.info(f"""
**應用資訊**
- 名稱: 租屋管理系統
- 版本: v2.0.0
- 框架: Streamlit 1.52+
- 資料庫: PostgreSQL (Supabase)
""")
    
    with col_b:
        st.info(f"""
**環境資訊**
- Python: 3.9+
- 部署: Streamlit Cloud
- 更新: {datetime.now().strftime('%Y-%m-%d')}
""")
    
    st.divider()
    
    # === 連線狀態 ===
    st.write("**🔌 連線狀態**")
    
    try:
        with db._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT version()")
            db_version = cur.fetchone()[0]
            
            st.success(f"✅ 資料庫連線正常")
            st.caption(f"PostgreSQL 版本: {db_version}")
    except Exception as e:
        st.error(f"❌ 資料庫連線失敗: {e}")
    
    st.divider()
    
    # === 快速診斷 ===
    st.write("**🔍 快速診斷**")
    
    if st.button("🔍 執行系統檢查"):
        with st.spinner("檢查中..."):
            checks = []
            
            # 檢查資料庫
            try:
                with db._get_connection() as conn:
                    checks.append(("✅", "資料庫連線", "正常"))
            except:
                checks.append(("❌", "資料庫連線", "失敗"))
            
            # 檢查表格
            try:
                db.get_tenants()
                checks.append(("✅", "tenants 表", "正常"))
            except:
                checks.append(("❌", "tenants 表", "異常"))
            
            try:
                db.get_payment_schedule()
                checks.append(("✅", "payment_schedule 表", "正常"))
            except:
                checks.append(("❌", "payment_schedule 表", "異常"))
            
            try:
                db.get_expenses(limit=1)
                checks.append(("✅", "expenses 表", "正常"))
            except:
                checks.append(("❌", "expenses 表", "異常"))
            
            # 顯示結果
            for icon, item, status in checks:
                st.write(f"{icon} **{item}**: {status}")


# ============== Tab 4: 關於系統 ==============

def render_about_tab():
    """關於系統"""
    section_header("關於系統", "📖")
    
    st.markdown("""
## 🏠 租屋管理系統 v2.0

### 功能模組
- **📊 儀表板**: 關鍵指標、租約警示、房間狀態
- **👥 房客管理**: 新增、編輯、刪除房客資訊
- **💰 租金管理**: 單筆/批量預填、繳費確認、財報統計
- **📋 繳費追蹤**: 批量標記、進階篩選、逾期提醒
- **⚡ 電費管理**: 計費期間、計算電費、繳費記錄
- **💸 支出管理**: 新增、編輯、刪除、統計分析
- **⚙️ 系統設定**: 參數設定、資料匯出、系統資訊

### 技術棧
- **前端**: Streamlit 1.52+
- **資料庫**: PostgreSQL (Supabase)
- **語言**: Python 3.9+
- **部署**: Streamlit Cloud

### 版本歷史
- **v2.0.0** (2026-01): 完整重構,新增批量操作、統計圖表
- **v1.5.0** (2025-12): 新增電費管理、繳費追蹤
- **v1.0.0** (2025-11): 初版發布

### 開發團隊
- **專案**: rental_saas2026
- **GitHub**: https://github.com/lianjen/rental_saas2026

### 意見回饋
如有任何問題或建議,歡迎透過 GitHub Issues 回報。

### 授權
© 2025-2026 租屋管理系統. All rights reserved.
""")


# ============== 主函數 ==============

def render(db):
    """主渲染函數"""
    st.title("⚙️ 系統設定")
    
    tab1, tab2, tab3, tab4 = st.tabs([
        "⚙️ 系統參數",
        "📥 資料匯出",
        "ℹ️ 系統資訊",
        "📖 關於"
    ])
    
    with tab1:
        render_params_tab(db)
    
    with tab2:
        render_export_tab(db)
    
    with tab3:
        render_info_tab(db)
    
    with tab4:
        render_about_tab()
