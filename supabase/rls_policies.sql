-- rental_saas2026 RLS Policies - v1.0.0
-- Purpose:
--   1. Align PostgreSQL row-level security with the current app architecture
--   2. Use BaseDBService's set_config('request.jwt.claim.sub', user_id, false)
--      as the ownership source for psycopg2 direct connections
--   3. Provide a conservative first deployment that protects owner-scoped tables
--      while keeping shared electricity master tables admin-only
--
-- Deployment notes:
--   - Run this manually in Supabase SQL Editor after backing up production
--   - This script is idempotent and safe to rerun
--   - It intentionally does NOT create or mutate business tables
--   - It only enables RLS and creates helper functions / policies when tables exist

BEGIN;

CREATE OR REPLACE FUNCTION public.saas_current_user_id()
RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '');
$$;

CREATE OR REPLACE FUNCTION public.saas_current_role()
RETURNS text
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    current_uid text := public.saas_current_user_id();
    resolved_role text;
BEGIN
    IF current_uid IS NULL THEN
        RETURN NULL;
    END IF;

    IF to_regclass('public.user_profiles') IS NOT NULL THEN
        EXECUTE
            'SELECT role FROM public.user_profiles WHERE id::text = $1 LIMIT 1'
        INTO resolved_role
        USING current_uid;
        IF resolved_role IS NOT NULL THEN
            RETURN resolved_role;
        END IF;
    END IF;

    IF to_regclass('public.app_users') IS NOT NULL THEN
        EXECUTE
            'SELECT role FROM public.app_users WHERE id::text = $1 LIMIT 1'
        INTO resolved_role
        USING current_uid;
        IF resolved_role IS NOT NULL THEN
            RETURN resolved_role;
        END IF;
    END IF;

    IF to_regclass('public.profiles') IS NOT NULL THEN
        EXECUTE
            'SELECT role FROM public.profiles WHERE id::text = $1 LIMIT 1'
        INTO resolved_role
        USING current_uid;
        IF resolved_role IS NOT NULL THEN
            RETURN resolved_role;
        END IF;
    END IF;

    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION public.saas_is_admin()
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(public.saas_current_role() = 'admin', false);
$$;

CREATE OR REPLACE FUNCTION public.saas_owns_room(target_room text)
RETURNS boolean
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    current_uid text := public.saas_current_user_id();
    allowed boolean := false;
BEGIN
    IF current_uid IS NULL OR target_room IS NULL THEN
        RETURN false;
    END IF;

    IF to_regclass('public.tenants') IS NULL THEN
        RETURN false;
    END IF;

    EXECUTE
        $sql$
        SELECT EXISTS (
            SELECT 1
            FROM public.tenants
            WHERE room_number = $1
              AND user_id::text = $2
        )
        $sql$
    INTO allowed
    USING target_room, current_uid;

    RETURN COALESCE(allowed, false);
END;
$$;

CREATE OR REPLACE FUNCTION public.saas_owns_tenant(target_tenant_id uuid)
RETURNS boolean
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    current_uid text := public.saas_current_user_id();
    allowed boolean := false;
BEGIN
    IF current_uid IS NULL OR target_tenant_id IS NULL THEN
        RETURN false;
    END IF;

    IF to_regclass('public.tenants') IS NULL THEN
        RETURN false;
    END IF;

    EXECUTE
        $sql$
        SELECT EXISTS (
            SELECT 1
            FROM public.tenants
            WHERE id = $1
              AND user_id::text = $2
        )
        $sql$
    INTO allowed
    USING target_tenant_id, current_uid;

    RETURN COALESCE(allowed, false);
END;
$$;

DO $$
BEGIN
    IF to_regclass('public.tenants') IS NOT NULL THEN
        EXECUTE 'ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY';

        EXECUTE 'DROP POLICY IF EXISTS saas_tenants_select ON public.tenants';
        EXECUTE 'DROP POLICY IF EXISTS saas_tenants_insert ON public.tenants';
        EXECUTE 'DROP POLICY IF EXISTS saas_tenants_update ON public.tenants';
        EXECUTE 'DROP POLICY IF EXISTS saas_tenants_delete ON public.tenants';

        EXECUTE '
            CREATE POLICY saas_tenants_select ON public.tenants
            FOR SELECT
            USING (
                public.saas_is_admin()
                OR user_id::text = public.saas_current_user_id()
            )
        ';

        EXECUTE '
            CREATE POLICY saas_tenants_insert ON public.tenants
            FOR INSERT
            WITH CHECK (
                public.saas_is_admin()
                OR user_id::text = public.saas_current_user_id()
            )
        ';

        EXECUTE '
            CREATE POLICY saas_tenants_update ON public.tenants
            FOR UPDATE
            USING (
                public.saas_is_admin()
                OR user_id::text = public.saas_current_user_id()
            )
            WITH CHECK (
                public.saas_is_admin()
                OR user_id::text = public.saas_current_user_id()
            )
        ';

        EXECUTE '
            CREATE POLICY saas_tenants_delete ON public.tenants
            FOR DELETE
            USING (
                public.saas_is_admin()
                OR user_id::text = public.saas_current_user_id()
            )
        ';
    END IF;
END;
$$;

DO $$
BEGIN
    IF to_regclass('public.payment_schedule') IS NOT NULL THEN
        EXECUTE 'ALTER TABLE public.payment_schedule ENABLE ROW LEVEL SECURITY';

        EXECUTE 'DROP POLICY IF EXISTS saas_payment_schedule_select ON public.payment_schedule';
        EXECUTE 'DROP POLICY IF EXISTS saas_payment_schedule_insert ON public.payment_schedule';
        EXECUTE 'DROP POLICY IF EXISTS saas_payment_schedule_update ON public.payment_schedule';
        EXECUTE 'DROP POLICY IF EXISTS saas_payment_schedule_delete ON public.payment_schedule';

        EXECUTE '
            CREATE POLICY saas_payment_schedule_select ON public.payment_schedule
            FOR SELECT
            USING (
                public.saas_is_admin()
                OR user_id::text = public.saas_current_user_id()
            )
        ';

        EXECUTE '
            CREATE POLICY saas_payment_schedule_insert ON public.payment_schedule
            FOR INSERT
            WITH CHECK (
                public.saas_is_admin()
                OR user_id::text = public.saas_current_user_id()
            )
        ';

        EXECUTE '
            CREATE POLICY saas_payment_schedule_update ON public.payment_schedule
            FOR UPDATE
            USING (
                public.saas_is_admin()
                OR user_id::text = public.saas_current_user_id()
            )
            WITH CHECK (
                public.saas_is_admin()
                OR user_id::text = public.saas_current_user_id()
            )
        ';

        EXECUTE '
            CREATE POLICY saas_payment_schedule_delete ON public.payment_schedule
            FOR DELETE
            USING (
                public.saas_is_admin()
                OR user_id::text = public.saas_current_user_id()
            )
        ';
    END IF;
END;
$$;

DO $$
BEGIN
    IF to_regclass('public.expenses') IS NOT NULL THEN
        EXECUTE 'ALTER TABLE public.expenses ENABLE ROW LEVEL SECURITY';

        EXECUTE 'DROP POLICY IF EXISTS saas_expenses_select ON public.expenses';
        EXECUTE 'DROP POLICY IF EXISTS saas_expenses_insert ON public.expenses';
        EXECUTE 'DROP POLICY IF EXISTS saas_expenses_update ON public.expenses';
        EXECUTE 'DROP POLICY IF EXISTS saas_expenses_delete ON public.expenses';

        EXECUTE '
            CREATE POLICY saas_expenses_select ON public.expenses
            FOR SELECT
            USING (
                public.saas_is_admin()
                OR user_id::text = public.saas_current_user_id()
            )
        ';

        EXECUTE '
            CREATE POLICY saas_expenses_insert ON public.expenses
            FOR INSERT
            WITH CHECK (
                public.saas_is_admin()
                OR user_id::text = public.saas_current_user_id()
            )
        ';

        EXECUTE '
            CREATE POLICY saas_expenses_update ON public.expenses
            FOR UPDATE
            USING (
                public.saas_is_admin()
                OR user_id::text = public.saas_current_user_id()
            )
            WITH CHECK (
                public.saas_is_admin()
                OR user_id::text = public.saas_current_user_id()
            )
        ';

        EXECUTE '
            CREATE POLICY saas_expenses_delete ON public.expenses
            FOR DELETE
            USING (
                public.saas_is_admin()
                OR user_id::text = public.saas_current_user_id()
            )
        ';
    END IF;
END;
$$;

DO $$
BEGIN
    IF to_regclass('public.tenant_contacts') IS NOT NULL THEN
        EXECUTE 'ALTER TABLE public.tenant_contacts ENABLE ROW LEVEL SECURITY';

        EXECUTE 'DROP POLICY IF EXISTS saas_tenant_contacts_select ON public.tenant_contacts';
        EXECUTE 'DROP POLICY IF EXISTS saas_tenant_contacts_insert ON public.tenant_contacts';
        EXECUTE 'DROP POLICY IF EXISTS saas_tenant_contacts_update ON public.tenant_contacts';
        EXECUTE 'DROP POLICY IF EXISTS saas_tenant_contacts_delete ON public.tenant_contacts';

        EXECUTE '
            CREATE POLICY saas_tenant_contacts_select ON public.tenant_contacts
            FOR SELECT
            USING (
                public.saas_is_admin()
                OR public.saas_owns_tenant(tenant_id)
            )
        ';

        EXECUTE '
            CREATE POLICY saas_tenant_contacts_insert ON public.tenant_contacts
            FOR INSERT
            WITH CHECK (
                public.saas_is_admin()
                OR public.saas_owns_tenant(tenant_id)
            )
        ';

        EXECUTE '
            CREATE POLICY saas_tenant_contacts_update ON public.tenant_contacts
            FOR UPDATE
            USING (
                public.saas_is_admin()
                OR public.saas_owns_tenant(tenant_id)
            )
            WITH CHECK (
                public.saas_is_admin()
                OR public.saas_owns_tenant(tenant_id)
            )
        ';

        EXECUTE '
            CREATE POLICY saas_tenant_contacts_delete ON public.tenant_contacts
            FOR DELETE
            USING (
                public.saas_is_admin()
                OR public.saas_owns_tenant(tenant_id)
            )
        ';
    END IF;
END;
$$;

DO $$
BEGIN
    IF to_regclass('public.memos') IS NOT NULL THEN
        EXECUTE 'ALTER TABLE public.memos ENABLE ROW LEVEL SECURITY';

        EXECUTE 'DROP POLICY IF EXISTS saas_memos_admin_all ON public.memos';

        EXECUTE '
            CREATE POLICY saas_memos_admin_all ON public.memos
            FOR ALL
            USING (public.saas_is_admin())
            WITH CHECK (public.saas_is_admin())
        ';
    END IF;
END;
$$;

DO $$
BEGIN
    IF to_regclass('public.electricity_readings') IS NOT NULL THEN
        EXECUTE 'ALTER TABLE public.electricity_readings ENABLE ROW LEVEL SECURITY';

        EXECUTE 'DROP POLICY IF EXISTS saas_electricity_readings_select ON public.electricity_readings';
        EXECUTE 'DROP POLICY IF EXISTS saas_electricity_readings_insert ON public.electricity_readings';
        EXECUTE 'DROP POLICY IF EXISTS saas_electricity_readings_update ON public.electricity_readings';
        EXECUTE 'DROP POLICY IF EXISTS saas_electricity_readings_delete ON public.electricity_readings';

        EXECUTE '
            CREATE POLICY saas_electricity_readings_select ON public.electricity_readings
            FOR SELECT
            USING (
                public.saas_is_admin()
                OR public.saas_owns_room(room_number)
            )
        ';

        EXECUTE '
            CREATE POLICY saas_electricity_readings_insert ON public.electricity_readings
            FOR INSERT
            WITH CHECK (
                public.saas_is_admin()
                OR public.saas_owns_room(room_number)
            )
        ';

        EXECUTE '
            CREATE POLICY saas_electricity_readings_update ON public.electricity_readings
            FOR UPDATE
            USING (
                public.saas_is_admin()
                OR public.saas_owns_room(room_number)
            )
            WITH CHECK (
                public.saas_is_admin()
                OR public.saas_owns_room(room_number)
            )
        ';

        EXECUTE '
            CREATE POLICY saas_electricity_readings_delete ON public.electricity_readings
            FOR DELETE
            USING (
                public.saas_is_admin()
                OR public.saas_owns_room(room_number)
            )
        ';
    END IF;
END;
$$;

DO $$
BEGIN
    IF to_regclass('public.electricity_deposit_ledger') IS NOT NULL THEN
        EXECUTE 'ALTER TABLE public.electricity_deposit_ledger ENABLE ROW LEVEL SECURITY';

        EXECUTE 'DROP POLICY IF EXISTS saas_electricity_deposit_ledger_select ON public.electricity_deposit_ledger';
        EXECUTE 'DROP POLICY IF EXISTS saas_electricity_deposit_ledger_insert ON public.electricity_deposit_ledger';
        EXECUTE 'DROP POLICY IF EXISTS saas_electricity_deposit_ledger_update ON public.electricity_deposit_ledger';
        EXECUTE 'DROP POLICY IF EXISTS saas_electricity_deposit_ledger_delete ON public.electricity_deposit_ledger';

        EXECUTE '
            CREATE POLICY saas_electricity_deposit_ledger_select ON public.electricity_deposit_ledger
            FOR SELECT
            USING (
                public.saas_is_admin()
                OR public.saas_owns_room(room_number)
            )
        ';

        EXECUTE '
            CREATE POLICY saas_electricity_deposit_ledger_insert ON public.electricity_deposit_ledger
            FOR INSERT
            WITH CHECK (
                public.saas_is_admin()
                OR public.saas_owns_room(room_number)
            )
        ';

        EXECUTE '
            CREATE POLICY saas_electricity_deposit_ledger_update ON public.electricity_deposit_ledger
            FOR UPDATE
            USING (
                public.saas_is_admin()
                OR public.saas_owns_room(room_number)
            )
            WITH CHECK (
                public.saas_is_admin()
                OR public.saas_owns_room(room_number)
            )
        ';

        EXECUTE '
            CREATE POLICY saas_electricity_deposit_ledger_delete ON public.electricity_deposit_ledger
            FOR DELETE
            USING (
                public.saas_is_admin()
                OR public.saas_owns_room(room_number)
            )
        ';
    END IF;
END;
$$;

DO $$
BEGIN
    IF to_regclass('public.electricity_periods') IS NOT NULL THEN
        EXECUTE 'ALTER TABLE public.electricity_periods ENABLE ROW LEVEL SECURITY';

        EXECUTE 'DROP POLICY IF EXISTS saas_electricity_periods_admin_all ON public.electricity_periods';

        EXECUTE '
            CREATE POLICY saas_electricity_periods_admin_all ON public.electricity_periods
            FOR ALL
            USING (public.saas_is_admin())
            WITH CHECK (public.saas_is_admin())
        ';
    END IF;
END;
$$;

DO $$
BEGIN
    IF to_regclass('public.electricity_taipower_bills') IS NOT NULL THEN
        EXECUTE 'ALTER TABLE public.electricity_taipower_bills ENABLE ROW LEVEL SECURITY';

        EXECUTE 'DROP POLICY IF EXISTS saas_electricity_taipower_bills_admin_all ON public.electricity_taipower_bills';

        EXECUTE '
            CREATE POLICY saas_electricity_taipower_bills_admin_all ON public.electricity_taipower_bills
            FOR ALL
            USING (public.saas_is_admin())
            WITH CHECK (public.saas_is_admin())
        ';
    END IF;
END;
$$;

DO $$
BEGIN
    IF to_regclass('public.taipower_bills') IS NOT NULL THEN
        EXECUTE 'ALTER TABLE public.taipower_bills ENABLE ROW LEVEL SECURITY';

        EXECUTE 'DROP POLICY IF EXISTS saas_taipower_bills_admin_all ON public.taipower_bills';

        EXECUTE '
            CREATE POLICY saas_taipower_bills_admin_all ON public.taipower_bills
            FOR ALL
            USING (public.saas_is_admin())
            WITH CHECK (public.saas_is_admin())
        ';
    END IF;
END;
$$;

DO $$
BEGIN
    IF to_regclass('public.electricity_deposit') IS NOT NULL THEN
        EXECUTE 'ALTER TABLE public.electricity_deposit ENABLE ROW LEVEL SECURITY';

        EXECUTE 'DROP POLICY IF EXISTS saas_electricity_deposit_admin_all ON public.electricity_deposit';

        EXECUTE '
            CREATE POLICY saas_electricity_deposit_admin_all ON public.electricity_deposit
            FOR ALL
            USING (public.saas_is_admin())
            WITH CHECK (public.saas_is_admin())
        ';
    END IF;
END;
$$;

COMMIT;
