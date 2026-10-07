-- Support Radar 목록용 뷰와, "모집 중"의 단 하나의 정의.
--
-- support_program_is_open(recruiting, application_end): recruiting이고 마감일이 없거나
-- 오늘(서울) 이후. 웹의 기본 "모집 중"·"7일 안에 마감" 보기(apps/web/src/lib/supportPrograms.ts)와
-- 워커의 중복 짝짓기(worker/repositories/support_programs.py)가 모두 이 정의를 쓴다 - 셋이
-- 따로 쓰면 어긋나는 순간 원본은 목록에서 빠지고 사본은 숨겨져 공고가 사라진다.
-- application_end는 날짜의 자정(UTC)으로 저장되므로, 오늘(서울) 날짜도 같은 방식으로 바꿔 비교한다.
--
-- support_programs_listing: 모든 행 + 그 행의 is_open + 기업마당 사본(duplicate_of가 있는 행)이면
-- 원본의 지금 상태(original_open, original_end). duplicate_of는 워커가 매시간 맞추는 짝일
-- 뿐이고, 사본을 숨길지는 웹이 보기마다 이 값으로 정한다(docs/SUPPORT_PROGRAMS.md#web) -
-- 원본이 마감되거나 마감일이 지나는 순간 사본이 다시 보인다.
--
-- security_invoker: 조회하는 사용자의 RLS를 그대로 적용한다(opportunities_current와 같은 방식).
-- 주의: p.* 는 이 뷰를 만들 때의 컬럼 목록으로 고정된다. support_programs에 컬럼을 더하는
-- 마이그레이션은 이 뷰도 다시 만들어야(drop + create) 웹에서 그 컬럼을 읽을 수 있다.

create function support_program_is_open(recruiting boolean, application_end timestamptz)
  returns boolean
  language sql
  stable
  as $$
    select recruiting is true
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
    o.application_end as original_end
  from support_programs p
  left join support_programs o on o.id = p.duplicate_of;

grant select on support_programs_listing to authenticated;
