-- "모집 중"을 다듬는다 (20261007130000의 is_open과 list_support_programs를 바꾼다 - 그 파일은
-- 이미 적용돼서 고치지 않는다).
--
-- 1. is_open_on_its_own(support_programs): 그 행의 값만 보고 정한 모집 여부 - 예전 is_open
--    그대로이되, 모집 여부도 마감일도 없으면 NULL(모름)이다. "마감"이라고 단정하지 않는다:
--    화면은 "—"(또는 신청기간 문장)로 보이고, 모집 중 목록에는 들지 않는다.
-- 2. is_open(support_programs): is_open_on_its_own에 더해, 기업마당 사본(duplicate_of)은
--    원본(K-Startup)이 마감이면 함께 마감이다. 같은 공고라고 짝지었으니 원본의 마감일이 그
--    공고의 마감일이다 - "예산 소진시까지"인 사본이 원본 마감 뒤에도 모집 중으로 남지 않게.
--    원본의 모집 여부를 모르면(NULL) 사본은 제 값대로다. 워커는 마감된 짝도 짝으로 둔다
--    (worker/dedupe/support_programs.py plan_duplicate_marks) - 풀어 버리면 "마감 포함
--    전체"에 같은 공고가 두 번 나온다.
-- 3. list_support_programs: 모집 여부를 모르는 공고(NULL)는 마감된 공고와 함께 뒤로 간다.
--    open/closing에서는 is_open을 계산하기 전에 그 필요조건(마감이라고 하지 않았고 마감일이
--    지나지 않음)으로 먼저 거른다 - 정의는 여전히 is_open 하나이고, 이건 마감된 이력(매달
--    ~1,500건씩 쌓인다)에 is_open을 계산하지 않으려는 것뿐이다.
-- 4. 기업마당 행은 last_seen_at이 반드시 있다(check). is_open의 "3일 넘게 목록에 없으면
--    마감"은 NULL을 "추적하지 않음"(K-Startup)으로 건너뛰는데, 기업마당 행이 NULL이면 그
--    규칙을 빠져나간다. 워커는 2026-10-07 배포부터 upsert마다 값을 쓰고, 2026-10-08 실측
--    1,473건 모두 값이 있다.

alter table support_programs
  add constraint support_programs_bizinfo_last_seen
  check (source <> 'bizinfo' or last_seen_at is not null);

create function is_open_on_its_own(p support_programs)
  returns boolean
  language sql
  stable
  as $$
    select case
      when p.recruiting is null and p.application_end is null then null
      else coalesce(p.recruiting, true)
        and (p.application_end is null or p.application_end >= support_program_today_utc())
        and (p.last_seen_at is null or p.last_seen_at >= now() - interval '3 days')
    end
  $$;

-- Same least-privilege surface as the other support_programs functions (20261007140000,
-- 20261007150000): Supabase's default privileges grant EXECUTE on new public functions to
-- PUBLIC and anon.
revoke execute on function is_open_on_its_own(support_programs) from public;
revoke execute on function is_open_on_its_own(support_programs) from anon;
grant execute on function is_open_on_its_own(support_programs) to authenticated, service_role;

-- create or replace keeps the existing grants/revokes on is_open and list_support_programs.
create or replace function is_open(p support_programs)
  returns boolean
  language sql
  stable
  as $$
    select case
      when p.duplicate_of is null then is_open_on_its_own(p)
      else is_open_on_its_own(p)
        and coalesce(
          (select is_open_on_its_own(o) from support_programs o where o.id = p.duplicate_of),
          true
        )
    end
  $$;

create or replace function list_support_programs(
  p_status text default 'open',
  p_it_only boolean default false,
  p_investment_only boolean default false,
  p_source text default null,
  p_categories text[] default null,
  p_term text default null,
  p_closing_days integer default 7,
  p_limit integer default 20,
  p_offset integer default 0
)
  returns jsonb
  language plpgsql
  stable
  security invoker
  as $$
  begin
    if p_status is null or p_status not in ('open', 'closing', 'all') then
      raise exception 'list_support_programs: unknown status %', p_status
        using errcode = '22023';
    end if;
    if p_limit is null or p_limit < 1 or p_limit > 100
      or p_offset is null or p_offset < 0
      or p_closing_days is null or p_closing_days < 0 or p_closing_days > 366 then
      raise exception 'list_support_programs: invalid paging or window'
        using errcode = '22023';
    end if;

    return (
      with candidates as (
        select
          p.id, p.duplicate_of, p.source, p.title, p.organization, p.supervising_type,
          p.category, p.region, p.recruiting, p.investment_linked, p.it_related,
          p.application_end, p.application_period_text,
          is_open(p) as is_open
        from support_programs p
        where (not p_it_only or p.it_related)
          and (not p_investment_only or p.investment_linked)
          and (p_source is null or p.source = p_source)
          and (p_categories is null or p.category = any (p_categories))
          and (
            p_term is null
            or strpos(lower(p.title), lower(p_term)) > 0
            or strpos(lower(coalesce(p.organization, '')), lower(p_term)) > 0
          )
          -- A necessary condition of is_open (see the header), checked first.
          and (
            p_status = 'all'
            or (
              p.recruiting is distinct from false
              and (p.application_end is null or p.application_end >= support_program_today_utc())
            )
          )
      ),
      filtered as (
        select c.*
        from candidates c
        where (p_status = 'all' or c.is_open)
          and (
            p_status <> 'closing'
            or (
              c.application_end >= support_program_today_utc()
              and c.application_end
                <= support_program_today_utc() + make_interval(days => p_closing_days)
            )
          )
      ),
      visible as (
        select f.*
        from filtered f
        where f.duplicate_of is null
          or not exists (select 1 from filtered o where o.id = f.duplicate_of)
      ),
      ordered as (
        select
          v.*,
          row_number() over (
            order by
              v.is_open desc nulls last,
              case when v.is_open then v.application_end end asc nulls last,
              v.application_end desc nulls last,
              v.id
          ) as position
        from visible v
      ),
      page_rows as (
        select
          o.id, o.source, o.title, o.organization, o.supervising_type, o.category, o.region,
          o.recruiting, o.is_open, o.investment_linked, o.it_related, o.application_end,
          o.application_period_text, o.position
        from ordered o
        where o.position > p_offset
          and o.position <= p_offset::bigint + p_limit
      )
      select jsonb_build_object(
        'total', (select count(*) from visible),
        'items', coalesce(
          (select jsonb_agg(to_jsonb(r) - 'position' order by r.position) from page_rows r),
          '[]'::jsonb
        )
      )
    );
  end;
  $$;
