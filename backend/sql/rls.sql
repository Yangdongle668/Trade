-- 多租户 RLS 双保险（架构 §9）：应用层过滤之外的数据库层兜底。
-- 应用/worker 使用非 owner 角色连接时启用；每个请求经
-- set_config('app.tenant_id', ...) 注入租户上下文（见 core/tenancy.py）。
-- 对所有带 tenant_id 的业务表执行（示例给出三张，其余同构）：

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'brand_assets','campaigns','companies','leads','source_runs','contacts',
    'email_candidates','sequence_states','send_jobs','mailboxes','threads',
    'messages','suppression_entries','usage_counters','events'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);  -- 幂等：部署可重复执行
    EXECUTE format($f$
      CREATE POLICY tenant_isolation ON %I
      USING (tenant_id = current_setting('app.tenant_id', true)::uuid)
      WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)
    $f$, t);
  END LOOP;
END $$;

-- 注意：research_facts 无 tenant_id（跨租户共享的公开事实缓存），不启用 RLS；
-- tenants/users/memberships 由应用层控制（登录流程发生在租户上下文建立之前）。
