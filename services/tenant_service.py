"""
租客管理服務 - v5.6 (rent_due_day 支援)
⚡ FORCE RELOAD: 2026-03-06
✅ 整合 Pydantic 驗證層
✅ 自動注入 user_id
✅ RLS Policy 兼容
✅ 認證權限檢查
✅ 租客 CRUD 操作
✅ 房間佔用檢查
✅ 完整統計功能
✅ SQL 注入防護
✅ DataFrame 安全處理
✅ 與 tenant_contacts 整合
✅ 完全適配 Supabase
✅ 向後兼容
✅ 欄位名稱已統一 (lease_start/end, rent, deposit)
✅ [NEW] base_rent / payment_cycle / annual_discount_months 欄位
✅ [NEW] rent 由 calc_effective_monthly_rent 自動計算
✅ [NEW] rent_due_day 每月繳費日（預設 1 號，支援個別設定）
"""

import pandas as pd
from datetime import date, datetime
from typing import Tuple, Optional, Dict, List, Union
from pydantic import ValidationError

from services.base_db import BaseDBService
from services.cache_utils import cache_data, clear_cached_functions, get_cache_scope
from services.logger import logger, log_db_operation

from schemas.tenant import (
    TenantCreate,
    TenantUpdate,
    TenantResponse,
    TenantListItem,
)

from utils.rent_pricing import calc_effective_monthly_rent

try:
    from config.constants import ROOMS, PAYMENT
    CONSTANTS_LOADED = True
except ImportError:
    logger.warning("⚠️ 無法載入 config.constants，使用備用常量")
    CONSTANTS_LOADED = False

    class BackupConstants:
        class ROOMS:
            ALL_ROOMS = [
                "1A", "1B",
                "2A", "2B",
                "3A", "3B", "3C", "3D",
                "4A", "4B", "4C", "4D",
            ]
        class PAYMENT:
            METHODS = ["月繳", "半年繳", "年繳"]

    ROOMS = BackupConstants.ROOMS
    PAYMENT = BackupConstants.PAYMENT


# ── SELECT 欄位清單（統一來源，改這裡就全部跟著改）─────────────────
_TENANT_SELECT_COLS = """
    id, room_number, name, phone, email, id_number,
    deposit, rent,
    base_rent, payment_cycle, annual_discount_months,
    rent_due_day,
    lease_start, lease_end, status, notes,
    created_at, updated_at
"""

# pricing 相關欄位（用於判斷是否需要重算 rent）
_PRICING_KEYS = {"base_rent", "payment_cycle", "annual_discount_months"}


def _recalculate_rent(
    existing: Dict,
    updates: Dict,
) -> float:
    """
    合併「既有資料 + 本次更新欄位」後重算折扣後月租。
    existing: get_tenant_by_id 回傳的 dict
    updates:  validated_data（已通過 Pydantic）
    """
    base_rent = float(
        updates.get("base_rent")
        or existing.get("base_rent")
        or existing.get("rent")
        or 0
    )
    payment_cycle = (
        updates.get("payment_cycle")
        or existing.get("payment_cycle")
        or "月繳"
    )
    annual_discount_months = int(
        updates.get("annual_discount_months")
        if updates.get("annual_discount_months") is not None
        else (existing.get("annual_discount_months") or 0)
    )
    if payment_cycle != "年繳":
        annual_discount_months = 0

    return calc_effective_monthly_rent(
        base_rent=base_rent,
        payment_cycle=payment_cycle,
        annual_discount_months=annual_discount_months,
        round_to=2,
    )


@cache_data(ttl=300)
def _cached_get_tenants(
    active_only: bool,
    user_id: str,
    dev_mode: bool,
) -> pd.DataFrame:
    return TenantService()._get_tenants_uncached(active_only=active_only)


@cache_data(ttl=300)
def _cached_get_tenant_by_room(
    room_number: str,
    user_id: str,
    dev_mode: bool,
) -> Optional[Dict]:
    return TenantService()._get_tenant_by_room_uncached(room_number=room_number)


def clear_tenant_cache() -> None:
    clear_cached_functions(
        _cached_get_tenants,
        _cached_get_tenant_by_room,
    )
    try:
        from services.electricity_service import clear_electricity_cache

        clear_electricity_cache()
    except Exception:
        pass


class TenantService(BaseDBService):
    """租客管理服務 (繼承 BaseDBService，整合認證)"""

    def __init__(self):
        super().__init__()
        self.all_rooms = ROOMS.ALL_ROOMS
        self.payment_methods = PAYMENT.METHODS

    # ==================== 查詢操作 ====================

    def _get_tenants_uncached(self, active_only: bool = True) -> pd.DataFrame:
        """獲取租客列表（自動過濾當前用戶）"""

        def query():
            with self.get_connection() as conn:
                cursor = conn.cursor()

                conditions = []
                if active_only:
                    conditions.append("status = 'active'")

                if not self.is_dev_mode():
                    user_id = self._get_current_user_id()
                    if user_id:
                        conditions.append(f"user_id = '{user_id}'")
                    else:
                        logger.warning("⚠️ 未登入，返回空結果")
                        return pd.DataFrame()

                where_clause = (
                    f"WHERE {' AND '.join(conditions)}" if conditions else ""
                )

                cursor.execute(
                    f"""
                    SELECT {_TENANT_SELECT_COLS}
                    FROM tenants
                    {where_clause}
                    ORDER BY room_number
                    """
                )

                columns = [desc[0] for desc in cursor.description]
                data = cursor.fetchall()

                if not data:
                    logger.info("📭 無租客記錄")
                    return pd.DataFrame(columns=columns)

                log_db_operation("SELECT", "tenants", True, len(data))
                logger.info(f"✅ 查詢到 {len(data)} 位租客")
                return pd.DataFrame(data, columns=columns)

        return self.retry_on_failure(query)

    def get_tenants(self, active_only: bool = True) -> pd.DataFrame:
        user_id, dev_mode = get_cache_scope(self)
        return _cached_get_tenants(active_only, user_id, dev_mode)

    def get_all_tenants(self, include_inactive: bool = True) -> List[Dict]:
        """取得所有房客"""
        try:
            df = self.get_tenants(active_only=not include_inactive)
            if not isinstance(df, pd.DataFrame):
                return []
            if df.empty:
                return []
            result = df.to_dict("records")
            logger.info(f"✅ 取得 {len(result)} 筆房客資料")
            return result
        except Exception as e:
            logger.error(f"❌ 取得所有房客失敗: {str(e)}", exc_info=True)
            return []

    def get_active_tenants(self) -> List[Dict]:
        """取得所有有效房客"""
        try:
            df = self.get_tenants(active_only=True)
            if not isinstance(df, pd.DataFrame) or df.empty:
                return []
            result = df.to_dict("records")
            logger.info(f"✅ 取得 {len(result)} 筆有效房客")
            return result
        except Exception as e:
            logger.error(f"❌ 取得有效房客失敗: {str(e)}", exc_info=True)
            return []

    def get_tenant_by_id(self, tenant_id: str) -> Optional[Dict]:
        """根據 ID 查詢租客（自動驗證權限）"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                user_id_check = ""
                if not self.is_dev_mode():
                    user_id = self._get_current_user_id()
                    if user_id:
                        user_id_check = f"AND user_id = '{user_id}'"
                    else:
                        return None

                cursor.execute(
                    f"""
                    SELECT {_TENANT_SELECT_COLS}
                    FROM tenants
                    WHERE id = %s {user_id_check}
                    """,
                    (tenant_id,),
                )

                row = cursor.fetchone()
                if not row:
                    return None

                columns = [desc[0] for desc in cursor.description]
                log_db_operation("SELECT", "tenants", True, 1)
                return dict(zip(columns, row))

        except Exception as e:
            log_db_operation("SELECT", "tenants", False, error=str(e))
            logger.error(f"❌ 查詢失敗: {str(e)}", exc_info=True)
            return None

    def _get_tenant_by_room_uncached(self, room_number: str) -> Optional[Dict]:
        """根據房號查詢租客"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                user_id_check = ""
                if not self.is_dev_mode():
                    user_id = self._get_current_user_id()
                    if user_id:
                        user_id_check = f"AND user_id = '{user_id}'"

                cursor.execute(
                    f"""
                    SELECT {_TENANT_SELECT_COLS}
                    FROM tenants
                    WHERE room_number = %s AND status = 'active' {user_id_check}
                    """,
                    (room_number,),
                )

                row = cursor.fetchone()
                if not row:
                    return None

                columns = [desc[0] for desc in cursor.description]
                log_db_operation("SELECT", "tenants", True, 1)
                return dict(zip(columns, row))

        except Exception as e:
            log_db_operation("SELECT", "tenants", False, error=str(e))
            logger.error(f"❌ 查詢失敗: {str(e)}", exc_info=True)
            return None

    # ==================== 新增操作 ====================

    def get_tenant_by_room(self, room_number: str) -> Optional[Dict]:
        user_id, dev_mode = get_cache_scope(self)
        return _cached_get_tenant_by_room(room_number, user_id, dev_mode)

    def add_tenant(
        self,
        tenant_data: Union[TenantCreate, Dict, None] = None,
        # ── 向後兼容舊參數 ──
        room: str = None,
        name: str = None,
        phone: str = None,
        deposit: float = None,
        base_rent: float = None,
        start: date = None,
        end: date = None,
        payment_method: str = None,
        has_water_fee: bool = False,
        annual_discount_months: int = 0,
        discount_notes: str = "",
        email: str = None,
        id_number: str = None,
        notes: str = None,
    ) -> Tuple[bool, str]:
        """
        新增租客（自動注入 user_id）

        方式 1（推薦）：傳入 TenantCreate 物件
        方式 2：傳入 dict
        方式 3（向後兼容）：傳入舊版關鍵字參數
        """
        try:
            user_id = self._get_current_user_id()
            if not user_id and not self.is_dev_mode():
                return False, "請先登入"

            # ── 取得 validated_data ──────────────────────────────────
            if isinstance(tenant_data, TenantCreate):
                validated_data = tenant_data.model_dump()

            elif isinstance(tenant_data, dict):
                try:
                    validated_data = TenantCreate(**tenant_data).model_dump()
                except ValidationError as e:
                    msg = self._format_validation_error(e)
                    return False, f"資料驗證失敗: {msg}"

            else:
                # 舊版關鍵字參數：組裝 dict → TenantCreate（不含 rent_due_day，使用預設 1）
                data_dict = {
                    "name": name,
                    "room_number": room,
                    "phone": phone or None,
                    "email": email or None,
                    "id_number": id_number or None,
                    "base_rent": base_rent or 0,
                    "payment_cycle": payment_method or "月繳",
                    "annual_discount_months": annual_discount_months or 0,
                    "deposit": deposit or 0,
                    "lease_start": start,
                    "lease_end": end,
                    "notes": notes or discount_notes or None,
                }
                try:
                    validated_data = TenantCreate(**data_dict).model_dump()
                except ValidationError as e:
                    msg = self._format_validation_error(e)
                    return False, f"資料驗證失敗: {msg}"

            # ── 業務驗證 ─────────────────────────────────────────────
            if validated_data["room_number"] not in self.all_rooms:
                return False, f"無效房號: {validated_data['room_number']}"

            if not self.check_room_availability(validated_data["room_number"]):
                return False, f"房間 {validated_data['room_number']} 已有租客"

            # ── 確保 rent 是最新計算值（防禦性再算一次）───────────────
            rent = calc_effective_monthly_rent(
                base_rent=validated_data["base_rent"],
                payment_cycle=validated_data["payment_cycle"],
                annual_discount_months=validated_data["annual_discount_months"],
                round_to=2,
            )

            # rent_due_day：從 validated_data 取，Pydantic 已確保預設 1
            rent_due_day = validated_data.get("rent_due_day", 1)

            # ── INSERT ───────────────────────────────────────────────
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO tenants
                    (user_id, room_number, name, phone, email, id_number,
                     base_rent, payment_cycle, annual_discount_months,
                     rent, deposit,
                     rent_due_day,
                     lease_start, lease_end, status, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        user_id,
                        validated_data["room_number"],
                        validated_data["name"],
                        validated_data.get("phone") or "",
                        validated_data.get("email"),
                        validated_data.get("id_number"),
                        validated_data["base_rent"],
                        validated_data["payment_cycle"],
                        validated_data["annual_discount_months"],
                        rent,
                        validated_data["deposit"],
                        rent_due_day,
                        validated_data["lease_start"],
                        validated_data.get("lease_end"),
                        validated_data.get("status", "active"),
                        validated_data.get("notes") or "",
                    ),
                )
                tenant_id = cursor.fetchone()[0]
                conn.commit()

            clear_tenant_cache()
            log_db_operation("INSERT", "tenants", True, 1)
            logger.info(
                f"✅ 新增租客: {validated_data['name']} "
                f"({validated_data['room_number']}) - ID: {tenant_id} "
                f"| base_rent={validated_data['base_rent']} "
                f"| payment_cycle={validated_data['payment_cycle']} "
                f"| rent(effective)={rent} "
                f"| rent_due_day={rent_due_day}"
            )
            return True, f"成功新增租客 {validated_data['name']}"

        except ValidationError as e:
            msg = self._format_validation_error(e)
            log_db_operation("INSERT", "tenants", False, error=msg)
            return False, f"資料驗證失敗: {msg}"

        except Exception as e:
            log_db_operation("INSERT", "tenants", False, error=str(e))
            logger.error(f"❌ 新增失敗: {str(e)}", exc_info=True)
            return False, f"新增失敗: {str(e)[:100]}"

    def create_tenant(self, tenant_data: Union[TenantCreate, Dict]) -> Optional[str]:
        """新增房客（別名，返回 ID）"""
        try:
            success, _ = self.add_tenant(tenant_data=tenant_data)
            if not success:
                return None

            room_number = (
                tenant_data.room_number
                if isinstance(tenant_data, TenantCreate)
                else tenant_data.get("room_number")
            )
            tenant = self.get_tenant_by_room(room_number)
            return tenant["id"] if tenant else None

        except Exception as e:
            logger.error(f"❌ 新增房客失敗: {str(e)}", exc_info=True)
            return None

    # ==================== 更新操作 ====================

    def update_tenant(
        self,
        tenant_id: str,
        tenant_data: Union[TenantUpdate, Dict, None] = None,
        # ── 向後兼容舊參數 ──
        room: str = None,
        name: str = None,
        phone: str = None,
        deposit: float = None,
        base_rent: float = None,
        start: date = None,
        end: date = None,
        payment_method: str = None,
        has_water_fee: bool = None,
        annual_discount_months: int = None,
        discount_notes: str = None,
        email: str = None,
        id_number: str = None,
        notes: str = None,
        status: str = None,
    ) -> Tuple[bool, str]:
        """
        更新租客資訊（自動驗證權限）
        任何 pricing 欄位（base_rent/payment_cycle/annual_discount_months）
        有變動時，自動重算 rent 寫入 DB。
        rent_due_day 可單獨更新，不影響其他欄位。
        """
        try:
            existing_tenant = self.get_tenant_by_id(tenant_id)
            if not existing_tenant:
                return False, f"租客 ID {tenant_id} 不存在或無權限"

            # ── 取得 validated_data ──────────────────────────────────
            if isinstance(tenant_data, TenantUpdate):
                validated_data = tenant_data.model_dump(exclude_unset=True)

            elif isinstance(tenant_data, dict):
                try:
                    validated_data = TenantUpdate(**tenant_data).model_dump(
                        exclude_unset=True
                    )
                except ValidationError as e:
                    return False, f"資料驗證失敗: {self._format_validation_error(e)}"

            else:
                data_dict = {}
                if name is not None:             data_dict["name"]                    = name
                if room is not None:             data_dict["room_number"]             = room
                if phone is not None:            data_dict["phone"]                   = phone
                if email is not None:            data_dict["email"]                   = email
                if id_number is not None:        data_dict["id_number"]               = id_number
                if base_rent is not None:        data_dict["base_rent"]               = base_rent
                if payment_method is not None:   data_dict["payment_cycle"]           = payment_method
                if annual_discount_months is not None:
                    data_dict["annual_discount_months"] = annual_discount_months
                if deposit is not None:          data_dict["deposit"]                 = deposit
                if start is not None:            data_dict["lease_start"]             = start
                if end is not None:              data_dict["lease_end"]               = end
                if status is not None:           data_dict["status"]                  = status
                if notes is not None or discount_notes is not None:
                    data_dict["notes"] = notes or discount_notes

                if not data_dict:
                    return False, "沒有要更新的欄位"

                try:
                    validated_data = TenantUpdate(**data_dict).model_dump(
                        exclude_unset=True
                    )
                except ValidationError as e:
                    return False, f"資料驗證失敗: {self._format_validation_error(e)}"

            # ── 業務驗證（房號衝突）──────────────────────────────────
            if "room_number" in validated_data:
                if validated_data["room_number"] not in self.all_rooms:
                    return False, f"無效房號: {validated_data['room_number']}"
                other = self.get_tenant_by_room(validated_data["room_number"])
                if other and other["id"] != tenant_id:
                    return False, f"房間 {validated_data['room_number']} 已有租客"

            # ── 若 pricing 欄位有變動，重算 rent ────────────────────
            if _PRICING_KEYS.intersection(validated_data.keys()):
                new_rent = _recalculate_rent(existing_tenant, validated_data)

                # 同步修正 annual_discount_months（非年繳歸零）
                merged_payment_cycle = (
                    validated_data.get("payment_cycle")
                    or existing_tenant.get("payment_cycle")
                    or "月繳"
                )
                if merged_payment_cycle != "年繳":
                    validated_data["annual_discount_months"] = 0

                validated_data["rent"] = new_rent
                logger.info(
                    f"💰 重算 rent: base_rent={validated_data.get('base_rent') or existing_tenant.get('base_rent')} "
                    f"| cycle={merged_payment_cycle} "
                    f"| discount={validated_data.get('annual_discount_months', 0)} "
                    f"| rent(effective)={new_rent}"
                )

            # ── UPDATE ───────────────────────────────────────────────
            with self.get_connection() as conn:
                cursor = conn.cursor()

                set_clauses = [f"{field} = %s" for field in validated_data]
                set_clauses.append("updated_at = NOW()")
                values = list(validated_data.values())
                values.append(tenant_id)

                user_id_check = ""
                if not self.is_dev_mode():
                    uid = self._get_current_user_id()
                    if uid:
                        user_id_check = f"AND user_id = '{uid}'"

                sql = f"""
                    UPDATE tenants
                    SET {', '.join(set_clauses)}
                    WHERE id = %s {user_id_check}
                """
                cursor.execute(sql, values)

                if cursor.rowcount == 0:
                    return False, f"租客 ID {tenant_id} 不存在或無權限"

                conn.commit()

            clear_tenant_cache()
            log_db_operation("UPDATE", "tenants", True, 1)
            logger.info(f"✅ 更新租客 ID: {tenant_id}")

            # ── 同步更新 tenant_contacts.room_number ─────────────────
            if "room_number" in validated_data:
                old_room = existing_tenant["room_number"]
                new_room = validated_data["room_number"]
                if old_room != new_room:
                    try:
                        with self.get_connection() as conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                """
                                UPDATE tenant_contacts
                                SET room_number = %s, updated_at = NOW()
                                WHERE tenant_id = %s
                                """,
                                (new_room, tenant_id),
                            )
                            conn.commit()
                            if cursor.rowcount > 0:
                                logger.info(
                                    f"🔄 tenant_contacts.room_number: {old_room} → {new_room}"
                                )
                    except Exception:
                        pass  # tenant_contacts 不存在時忽略

            return True, "成功更新租客資料"

        except ValidationError as e:
            msg = self._format_validation_error(e)
            log_db_operation("UPDATE", "tenants", False, error=msg)
            return False, f"資料驗證失敗: {msg}"

        except Exception as e:
            log_db_operation("UPDATE", "tenants", False, error=str(e))
            logger.error(f"❌ 更新失敗: {str(e)}", exc_info=True)
            return False, f"更新失敗: {str(e)[:100]}"

    # ==================== 刪除操作 ====================

    def delete_tenant(self, tenant_id: str) -> Tuple[bool, str]:
        """刪除租客（軟刪除，自動驗證權限）"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                user_id_check = ""
                if not self.is_dev_mode():
                    uid = self._get_current_user_id()
                    if uid:
                        user_id_check = f"AND user_id = '{uid}'"

                cursor.execute(
                    f"SELECT name FROM tenants WHERE id = %s {user_id_check}",
                    (tenant_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return False, f"租客 ID {tenant_id} 不存在或無權限"

                tenant_name = row[0]

                cursor.execute(
                    f"""
                    UPDATE tenants
                    SET status = 'inactive',
                        lease_end = CURRENT_DATE,
                        updated_at = NOW()
                    WHERE id = %s {user_id_check}
                    """,
                    (tenant_id,),
                )
                conn.commit()

            clear_tenant_cache()
            log_db_operation("UPDATE", "tenants (soft delete)", True, 1)
            logger.info(f"✅ 刪除租客: {tenant_name} (ID: {tenant_id})")

            # 清理 tenant_contacts 綁定狀態
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        UPDATE tenant_contacts
                        SET
                            line_user_id = NULL,
                            is_verified = false,
                            room_number = NULL,
                            pending_room = NULL,
                            verification_code = NULL,
                            verification_expires_at = NULL,
                            updated_at = NOW()
                        WHERE tenant_id = %s
                        """,
                        (tenant_id,),
                    )
                    conn.commit()
            except Exception:
                pass

            return True, f"成功刪除租客 {tenant_name}"

        except Exception as e:
            log_db_operation("UPDATE", "tenants", False, error=str(e))
            logger.error(f"❌ 刪除失敗: {str(e)}", exc_info=True)
            return False, f"刪除失敗: {str(e)[:100]}"

    # ==================== 輔助方法 ====================

    def _format_validation_error(self, error: ValidationError) -> str:
        errors = []
        for err in error.errors():
            field = " -> ".join(str(loc) for loc in err["loc"])
            errors.append(f"{field}: {err['msg']}")
        return "; ".join(errors)

    def check_room_availability(self, room_number: str) -> bool:
        """檢查房間是否可用"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                user_id_check = ""
                if not self.is_dev_mode():
                    uid = self._get_current_user_id()
                    if uid:
                        user_id_check = f"AND user_id = '{uid}'"

                cursor.execute(
                    f"""
                    SELECT COUNT(*) FROM tenants
                    WHERE room_number = %s AND status = 'active' {user_id_check}
                    """,
                    (room_number,),
                )
                is_available = cursor.fetchone()[0] == 0
                logger.info(f"🔍 房間 {room_number}: {'可用' if is_available else '已佔用'}")
                return is_available

        except Exception as e:
            logger.error(f"❌ 檢查失敗: {str(e)}", exc_info=True)
            return False

    def get_available_rooms(self) -> List[str]:
        """取得所有可用房間"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                user_id_check = ""
                if not self.is_dev_mode():
                    uid = self._get_current_user_id()
                    if uid:
                        user_id_check = f"AND user_id = '{uid}'"

                cursor.execute(
                    f"""
                    SELECT room_number FROM tenants
                    WHERE status = 'active' {user_id_check}
                    """
                )
                occupied = {row[0] for row in cursor.fetchall()}
                available = [r for r in self.all_rooms if r not in occupied]

            log_db_operation("SELECT", "tenants (available rooms)", True, len(available))
            logger.info(f"✅ 可用房間: {len(available)} 間")
            return available

        except Exception as e:
            log_db_operation("SELECT", "tenants (available rooms)", False, error=str(e))
            logger.error(f"❌ 查詢失敗: {str(e)}", exc_info=True)
            return []

    def get_vacant_rooms(self, all_rooms: Optional[List[str]] = None) -> List[str]:
        """空房列表（別名）"""
        return self.get_available_rooms()

    def get_tenant_statistics(self) -> Dict:
        """取得租客統計數據"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                user_id_check = ""
                if not self.is_dev_mode():
                    uid = self._get_current_user_id()
                    if uid:
                        user_id_check = f"AND user_id = '{uid}'"

                cursor.execute(
                    f"""
                    SELECT
                        COUNT(*)         AS total_tenants,
                        SUM(rent)        AS total_rent,
                        AVG(rent)        AS avg_rent,
                        SUM(deposit)     AS total_deposit
                    FROM tenants
                    WHERE status = 'active' {user_id_check}
                    """
                )
                row = cursor.fetchone()

            total_tenants = int(row[0] or 0)
            total_rooms = len(self.all_rooms)
            occupancy_rate = (
                total_tenants / total_rooms * 100 if total_rooms > 0 else 0
            )

            stats = {
                "total_tenants":   total_tenants,
                "total_rent":      float(row[1] or 0),
                "avg_rent":        float(row[2] or 0),
                "total_deposit":   float(row[3] or 0),
                "occupied_rooms":  total_tenants,
                "available_rooms": total_rooms - total_tenants,
                "total_rooms":     total_rooms,
                "occupancy_rate":  round(occupancy_rate, 2),
            }

            log_db_operation("SELECT", "tenants (statistics)", True, 1)
            logger.info(f"✅ 統計完成: 出租率 {occupancy_rate:.1f}%")
            return stats

        except Exception as e:
            log_db_operation("SELECT", "tenants (statistics)", False, error=str(e))
            logger.error(f"❌ 統計失敗: {str(e)}", exc_info=True)
            return {
                "total_tenants":   0,
                "total_rent":      0.0,
                "avg_rent":        0.0,
                "total_deposit":   0.0,
                "occupied_rooms":  0,
                "available_rooms": len(self.all_rooms),
                "total_rooms":     len(self.all_rooms),
                "occupancy_rate":  0.0,
            }

    def get_occupancy_rate(self, total_rooms: Optional[int] = None) -> float:
        """計算出租率（別名）"""
        return self.get_tenant_statistics()["occupancy_rate"]

    def get_expiring_leases(self, days: int = 30) -> List[Dict]:
        """取得即將到期的租約"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                user_id_check = ""
                if not self.is_dev_mode():
                    uid = self._get_current_user_id()
                    if uid:
                        user_id_check = f"AND user_id = '{uid}'"

                cursor.execute(
                    f"""
                    SELECT
                        id, room_number, name, phone, lease_end,
                        (lease_end - CURRENT_DATE) AS days_remaining
                    FROM tenants
                    WHERE status = 'active'
                      AND lease_end <= CURRENT_DATE + make_interval(days => %s)
                      AND lease_end >= CURRENT_DATE
                      {user_id_check}
                    ORDER BY lease_end
                    """,
                    (days,),
                )
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()

            log_db_operation("SELECT", "tenants (expiring leases)", True, len(rows))
            logger.info(f"⏰ 找到 {len(rows)} 筆即將到期的租約")
            return [dict(zip(columns, r)) for r in rows]

        except Exception as e:
            log_db_operation("SELECT", "tenants (expiring leases)", False, error=str(e))
            logger.error(f"❌ 查詢失敗: {str(e)}", exc_info=True)
            return []

    def check_lease_expiry(self, days_ahead: int = 45) -> List[Dict]:
        """即將到期租約（別名）"""
        return self.get_expiring_leases(days=days_ahead)


# ============================================
# 本機測試
# ============================================
if __name__ == "__main__":
    from datetime import timedelta

    service = TenantService()
    print("=== 測試 TenantService v5.5 ===\n")

    print("0. 認證狀態:")
    print(f"   已登入: {service.is_authenticated()}")
    print(f"   開發模式: {service.is_dev_mode()}")
    print(f"   User ID: {service._get_current_user_id() or '無'}\n")

    print("1. Pydantic 驗證（年繳折 1 個月 + 繳費日 5 號）:")
    try:
        t = TenantCreate(
            name="測試房客",
            room_number="4D",
            phone="0912-345-678",
            base_rent=5000.0,
            payment_cycle="年繳",
            annual_discount_months=1,
            deposit=12000.0,
            rent_due_day=5,
            lease_start=date.today(),
            lease_end=date.today() + timedelta(days=365),
        )
        print(f"   ✅ base_rent={t.base_rent} | payment_cycle={t.payment_cycle} | rent={t.rent} | rent_due_day={t.rent_due_day}\n")
    except ValidationError as e:
        print(f"   ❌ 驗證失敗: {e}\n")

    print("2. Pydantic 驗證（預設繳費日 = 1 號）:")
    try:
        t2 = TenantCreate(
            name="預設房客",
            room_number="3A",
            base_rent=6000.0,
            lease_start=date.today(),
        )
        print(f"   ✅ rent_due_day={t2.rent_due_day}（預設 1 號）\n")
    except ValidationError as e:
        print(f"   ❌ 驗證失敗: {e}\n")

    print("3. Pydantic 驗證（錯誤資料 - 應攔截）:")
    try:
        TenantCreate(
            name="王",         # ❌ 太短
            room_number="4D",
            base_rent=-100,    # ❌ 負數
            rent_due_day=31,   # ❌ 超過 28
            lease_start=date.today(),
        )
        print("   ❌ 未攔截錯誤\n")
    except ValidationError as e:
        print(f"   ✅ 成功攔截 {e.error_count()} 個錯誤\n")

    print("4. 所有房客 (DataFrame):")
    df = service.get_tenants()
    print(f"   共 {len(df)} 筆, 欄位: {list(df.columns)}\n")

    print("5. 統計:")
    for k, v in service.get_tenant_statistics().items():
        print(f"   {k}: {v}")

    print("\n6. 可用房間:")
    vacant = service.get_vacant_rooms()
    print(f"   {', '.join(vacant[:6])}... 共 {len(vacant)} 間")

    print("\n✅ 測試完成")
