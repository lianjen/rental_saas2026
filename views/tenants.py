"""
房客管理 - 重構版
特性:
- 完整表單驗證
- 租約衝突檢查
- 刪除功能
- 使用統一常數
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime
from typing import Optional, Tuple
import sys
sys.path.append('..')

from components.cards import section_header, empty_state, data_table, confirm_dialog
from config.constants import ROOMS, PAYMENT


def validate_phone(phone: str) -> Tuple[bool, str]:
    """驗證電話格式"""
    if not phone:
        return True, ""  # 允許空值
    
    # 移除常見分隔符
    clean_phone = phone.replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
    
    # 檢查是否為數字
    if not clean_phone.isdigit():
        return False, "電話號碼只能包含數字"
    
    # 檢查長度 (台灣電話 8-10 碼)
    if len(clean_phone) < 8 or len(clean_phone) > 10:
        return False, "電話號碼長度應為 8-10 碼"
    
    return True, ""


def validate_date_range(start: date, end: date) -> Tuple[bool, str]:
    """驗證日期範圍"""
    if start >= end:
        return False, "租約結束日期必須晚於開始日期"
    
    # 檢查租約長度是否合理 (至少 1 個月)
    delta = (end - start).days
    if delta < 30:
        return False, "租約期間至少需要 30 天"
    
    return True, ""


def check_room_conflict(db, room: str, start: date, end: date, 
                        exclude_tenant_id: Optional[int] = None) -> Tuple[bool, str]:
    """
    檢查房號是否與現有租約衝突
    
    Args:
        db: 資料庫實例
        room: 房號
        start: 租約開始日
        end: 租約結束日
        exclude_tenant_id: 排除的房客 ID (編輯時使用)
    
    Returns:
        (是否衝突, 訊息)
    """
    df = db.get_tenants()
    
    if df.empty:
        return False, ""
    
    # 過濾同房號的房客
    same_room = df[df['room_number'] == room]
    
    if exclude_tenant_id:
        same_room = same_room[same_room['id'] != exclude_tenant_id]
    
    for _, tenant in same_room.iterrows():
        existing_start = pd.to_datetime(tenant['lease_start']).date()
        existing_end = pd.to_datetime(tenant['lease_end']).date()
        
        # 檢查日期是否重疊
        if not (end <= existing_start or start >= existing_end):
            return True, f"與現有房客 {tenant['tenant_name']} 的租約期間衝突"
    
    return False, ""


def render_add_tab(db):
    """新增房客 Tab"""
    section_header("新增房客", "➕")
    
    with st.form("add_tenant_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            room = st.selectbox(
                "房號 *",
                ROOMS.ALL_ROOMS,
                key="add_room"
            )
            
            name = st.text_input(
                "姓名 *",
                placeholder="例如: 王小明",
                key="add_name"
            )
            
            phone = st.text_input(
                "電話",
                placeholder="例如: 0912345678",
                key="add_phone"
            )
            
            deposit = st.number_input(
                "押金 *",
                min_value=0,
                value=10000,
                step=1000,
                key="add_deposit"
            )
        
        with col2:
            base_rent = st.number_input(
                "月租 *",
                min_value=0,
                value=8000,
                step=500,
                key="add_rent"
            )
            
            lease_start = st.date_input(
                "租約開始 *",
                value=date.today(),
                key="add_start"
            )
            
            lease_end = st.date_input(
                "租約到期 *",
                value=date.today().replace(year=date.today().year + 1),
                key="add_end"
            )
            
            payment_method = st.selectbox(
                "繳款方式 *",
                PAYMENT.METHODS,
                key="add_method"
            )
        
        st.divider()
        
        col3, col4 = st.columns(2)
        
        with col3:
            has_water_fee = st.checkbox(
                "包含水費折扣",
                value=False,
                help="勾選後會在租金中扣除 100 元水費",
                key="add_water"
            )
        
        with col4:
            annual_discount_months = st.number_input(
                "年繳折扣月數",
                min_value=0,
                max_value=12,
                value=0,
                help="年繳時可享有的免租月數",
                key="add_discount"
            )
        
        discount_notes = st.text_area(
            "折扣說明",
            placeholder="例如: 年繳送 1 個月",
            key="add_notes"
        )
        
        submitted = st.form_submit_button("✅ 新增房客", type="primary")
        
        if submitted:
            # 驗證必填欄位
            if not name.strip():
                st.error("❌ 請輸入姓名")
                return
            
            # 驗證電話
            phone_valid, phone_msg = validate_phone(phone)
            if not phone_valid:
                st.error(f"❌ {phone_msg}")
                return
            
            # 驗證日期
            date_valid, date_msg = validate_date_range(lease_start, lease_end)
            if not date_valid:
                st.error(f"❌ {date_msg}")
                return
            
            # 檢查房號衝突
            conflict, conflict_msg = check_room_conflict(db, room, lease_start, lease_end)
            if conflict:
                st.error(f"❌ {conflict_msg}")
                return
            
            # 新增房客
            ok, msg = db.add_tenant(
                room, name, phone, deposit, base_rent,
                lease_start, lease_end, payment_method,
                has_water_fee, annual_discount_months, discount_notes
            )
            
            if ok:
                st.success(msg)
                st.balloons()
                st.rerun()
            else:
                st.error(msg)


def render_list_tab(db):
    """房客列表 Tab"""
    section_header("所有房客", "👥")
    
    df = db.get_tenants()
    
    if df.empty:
        empty_state(
            "目前沒有房客資料",
            "👥",
            "點擊「新增房客」開始管理"
        )
        return
    
    # 篩選控制
    col1, col2, col3 = st.columns(3)
    
    with col1:
        filter_room = st.multiselect(
            "篩選房號",
            ROOMS.ALL_ROOMS,
            key="filter_room"
        )
    
    with col2:
        filter_method = st.multiselect(
            "篩選繳款方式",
            PAYMENT.METHODS,
            key="filter_method"
        )
    
    with col3:
        search_name = st.text_input(
            "搜尋姓名",
            placeholder="輸入姓名關鍵字",
            key="search_name"
        )
    
    # 應用篩選
    filtered_df = df.copy()
    
    if filter_room:
        filtered_df = filtered_df[filtered_df['room_number'].isin(filter_room)]
    
    if filter_method:
        filtered_df = filtered_df[filtered_df['payment_method'].isin(filter_method)]
    
    if search_name:
        filtered_df = filtered_df[
            filtered_df['tenant_name'].str.contains(search_name, case=False, na=False)
        ]
    
    st.write(f"共 {len(filtered_df)} 筆資料")
    
    # 顯示資料表
    if not filtered_df.empty:
        display_df = filtered_df[[
            'room_number', 'tenant_name', 'phone', 
            'base_rent', 'lease_start', 'lease_end', 'payment_method'
        ]].copy()
        
        display_df.columns = ['房號', '姓名', '電話', '月租', '租約開始', '租約到期', '繳款方式']
        
        data_table(display_df, key="tenant_list")
    else:
        st.info("📭 沒有符合條件的資料")


def render_edit_tab(db):
    """編輯房客 Tab"""
    section_header("編輯房客", "✏️")
    
    df = db.get_tenants()
    
    if df.empty:
        empty_state("沒有可編輯的房客", "👥")
        return
    
    # 選擇房客
    tenant_options = {
        f"{row['room_number']} - {row['tenant_name']}": row['id']
        for _, row in df.iterrows()
    }
    
    selected = st.selectbox(
        "選擇要編輯的房客",
        list(tenant_options.keys()),
        key="edit_select"
    )
    
    if not selected:
        return
    
    tenant_id = tenant_options[selected]
    tenant_data = df[df['id'] == tenant_id].iloc[0]
    
    st.divider()
    
    # 編輯表單
    with st.form("edit_tenant_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            room = st.selectbox(
                "房號 *",
                ROOMS.ALL_ROOMS,
                index=ROOMS.ALL_ROOMS.index(tenant_data['room_number']),
                key="edit_room"
            )
            
            name = st.text_input(
                "姓名 *",
                value=tenant_data['tenant_name'],
                key="edit_name"
            )
            
            phone = st.text_input(
                "電話",
                value=tenant_data['phone'] or "",
                key="edit_phone"
            )
            
            deposit = st.number_input(
                "押金 *",
                min_value=0,
                value=float(tenant_data['deposit']),
                step=1000,
                key="edit_deposit"
            )
        
        with col2:
            base_rent = st.number_input(
                "月租 *",
                min_value=0,
                value=float(tenant_data['base_rent']),
                step=500,
                key="edit_rent"
            )
            
            lease_start = st.date_input(
                "租約開始 *",
                value=pd.to_datetime(tenant_data['lease_start']).date(),
                key="edit_start"
            )
            
            lease_end = st.date_input(
                "租約到期 *",
                value=pd.to_datetime(tenant_data['lease_end']).date(),
                key="edit_end"
            )
            
            payment_method = st.selectbox(
                "繳款方式 *",
                PAYMENT.METHODS,
                index=PAYMENT.METHODS.index(tenant_data['payment_method']),
                key="edit_method"
            )
        
        st.divider()
        
        col3, col4 = st.columns(2)
        
        with col3:
            has_water_fee = st.checkbox(
                "包含水費折扣",
                value=bool(tenant_data.get('has_water_fee', False)),
                key="edit_water"
            )
        
        with col4:
            annual_discount_months = st.number_input(
                "年繳折扣月數",
                min_value=0,
                max_value=12,
                value=int(tenant_data.get('annual_discount_months', 0)),
                key="edit_discount"
            )
        
        discount_notes = st.text_area(
            "折扣說明",
            value=tenant_data.get('discount_notes', ''),
            key="edit_notes"
        )
        
        col_update, col_delete = st.columns([3, 1])
        
        with col_update:
            update_btn = st.form_submit_button("💾 儲存變更", type="primary")
        
        with col_delete:
            delete_btn = st.form_submit_button("🗑️ 刪除", type="secondary")
        
        if update_btn:
            # 驗證
            if not name.strip():
                st.error("❌ 請輸入姓名")
                return
            
            phone_valid, phone_msg = validate_phone(phone)
            if not phone_valid:
                st.error(f"❌ {phone_msg}")
                return
            
            date_valid, date_msg = validate_date_range(lease_start, lease_end)
            if not date_valid:
                st.error(f"❌ {date_msg}")
                return
            
            conflict, conflict_msg = check_room_conflict(
                db, room, lease_start, lease_end, tenant_id
            )
            if conflict:
                st.error(f"❌ {conflict_msg}")
                return
            
            # 更新
            ok, msg = db.update_tenant(
                room, name, phone, deposit, base_rent,
                lease_start, lease_end, payment_method,
                has_water_fee, annual_discount_months,
                discount_notes, tenant_id
            )
            
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
        
        if delete_btn:
            if confirm_dialog(
                f"確定要刪除 {tenant_data['tenant_name']} 的資料嗎？",
                "delete_tenant_confirm"
            ):
                ok, msg = db.delete_tenant(tenant_id)
                if ok:
                    st.success(msg)
                    del st.session_state.delete_tenant_confirm
                    st.rerun()
                else:
                    st.error(msg)


def render(db):
    """主渲染函數"""
    st.title("👥 房客管理")
    
    tab1, tab2, tab3 = st.tabs(["➕ 新增房客", "📋 房客列表", "✏️ 編輯房客"])
    
    with tab1:
        render_add_tab(db)
    
    with tab2:
        render_list_tab(db)
    
    with tab3:
        render_edit_tab(db)