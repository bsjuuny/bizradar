-- Functions are executable by PUBLIC by default in PostgreSQL. The table's grants and
-- RLS already prevent anonymous data reads, but keep the callable surface least-privilege
-- too: browser users are authenticated, while the worker uses service_role.

revoke execute on function support_program_today_utc() from public;
grant execute on function support_program_today_utc() to authenticated, service_role;

revoke execute on function is_open(support_programs) from public;
grant execute on function is_open(support_programs) to authenticated, service_role;

revoke execute on function list_support_programs(
  text, boolean, boolean, text, text[], text, integer, integer, integer
) from public;
grant execute on function list_support_programs(
  text, boolean, boolean, text, text[], text, integer, integer, integer
) to authenticated, service_role;
