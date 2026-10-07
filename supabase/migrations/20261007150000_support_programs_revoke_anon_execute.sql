-- Supabase projects may grant function EXECUTE directly to anon through default
-- privileges. Revoking PUBLIC alone therefore does not guarantee that unauthenticated
-- PostgREST callers cannot invoke these helpers.

revoke execute on function support_program_today_utc() from anon;

revoke execute on function is_open(support_programs) from anon;

revoke execute on function list_support_programs(
  text, boolean, boolean, text, text[], text, integer, integer, integer
) from anon;
