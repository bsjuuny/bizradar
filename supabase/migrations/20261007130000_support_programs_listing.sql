-- Support Radar 목록용 뷰와, "모집 중"의 단 하나의 정의.
--
-- support_program_is_open(recruiting, application_end): 출처가 모집 중이라고 하거나(recruiting),
-- 모집 여부를 알 수 없을 때(null)는 마감일이 있으면, 그리고 마감일이 없거나 오늘(서울)
-- 이후일 때. 출처가 마감이라고 한 공고(false)는 날짜와 상관없이 마감이다. 웹의 "모집 중"·
-- "7일 안에 마감" 보기(apps/web/src/lib/supportPrograms.ts)와 워커의 중복 짝짓기
-- (worker/repositories/support_programs.py)가 모두 이 정의만 쓴다 - 따로 쓰면 어긋나는 순간
-- 원본은 목록에서 빠지고 사본은 숨겨져 공고가 사라진다.
-- application_end는 날짜의 자정(UTC, 수집기가 +00:00을 붙여 저장)이므로, 오늘(서울) 날짜도
-- 같은 방식으로 바꿔 비교한다.
--
-- support_programs_listing: 모든 행 + 그 행의 is_open + 기업마당 사본(duplicate_of가 있는 행)이면
-- 원본의 지금 상태와 필터에 쓰이는 값(original_*). duplicate_of는 워커가 매시간 맞추는 짝일
-- 뿐이고, 사본을 숨길지는 웹이 보기마다 정한다: 원본도 그 보기의 조건을 모두 통과해 목록에
-- 함께 나올 때만 숨긴다(docs/SUPPORT_PROGRAMS.md#web). 조회 시점 값이라 원본이 마감되는 순간
-- 사본이 다시 보인다.
--
-- security_invoker: 조회하는 사용자의 RLS를 그대로 적용한다(opportunities_current와 같은 방식).
-- 주의: p.* 는 이 뷰를 만들 때의 컬럼 목록으로 고정된다. support_programs에 컬럼을 더하는
-- 마이그레이션은 이 뷰도 다시 만들어야(drop + create) 웹에서 그 컬럼을 읽을 수 있다.

create function support_program_is_open(recruiting boolean, application_end timestamptz)
  returns boolean
  language sql
  stable
  as $$
    select coalesce(recruiting, application_end is not null)
      and (
        application_end is null
        or application_end >= ((now() at time zone 'Asia/Seoul')::date)::timestamp at time zone 'UTC'
      )
  $$;

create view support_programs_listing
  with (security_invoker = true)
  as
  select
    p.*,
    support_program_is_open(p.recruiting, p.application_end) as is_open,
    support_program_is_open(o.recruiting, o.application_end) as original_open,
    o.application_end as original_end,
    o.title as original_title,
    o.organization as original_organization,
    o.category as original_category,
    o.it_related as original_it_related,
    o.investment_linked as original_investment_linked
  from support_programs p
  left join support_programs o on o.id = p.duplicate_of;

grant select on support_programs_listing to authenticated;
