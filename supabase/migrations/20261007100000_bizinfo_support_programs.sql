-- Phase 6 (remainder): 기업마당(BizInfo) 지원사업 공고를 K-Startup과 같은 support_programs
-- 테이블에 싣는다. 테이블 모양은 그대로이고, 세 가지만 더한다. 자세한 내용은
-- docs/SUPPORT_PROGRAMS.md.
--
-- 1. source 허용값에 'bizinfo'를 더한다. 기존 제약은 컬럼 인라인 check라 Postgres가
--    support_programs_source_check로 이름을 붙였다. if exists를 일부러 쓰지 않는다 -
--    이름이 다르면 조용히 넘어가 옛 제약이 남는 대신, 여기서 실패해 바로 드러나게 한다.
-- 2. application_period_text: 출처가 적은 신청기간 원문. 기업마당 공고의 65%(2026-10-07
--    공개 목록 1,442건 중 942건)가 "예산 소진시까지"·"상시 접수"처럼 날짜가 아닌 문장이라
--    application_start/end가 비는데, 그때 화면이 "일정 미정"으로 뭉개지 않도록 원문을 둔다.
-- 3. duplicate_of: 같은 공고가 다른 출처에도 올라와 있으면 숨길 쪽 행이 남길 쪽 행을
--    가리킨다. 워커만 채운다(worker/dedupe/support_programs.py). 웹 목록은 null인 행만 보여준다.
--    원본 행을 지우지 않는 이유: 수집은 upsert만 하므로 지워도 다음 회차에 되살아나고,
--    판정이 틀렸을 때 되돌릴 근거(raw_payload)도 함께 사라진다.

alter table support_programs drop constraint support_programs_source_check;
alter table support_programs
  add constraint support_programs_source_check check (source in ('kstartup', 'bizinfo'));

alter table support_programs
  add column application_period_text text,
  add column duplicate_of uuid references support_programs (id) on delete set null,
  add constraint support_programs_not_duplicate_of_self check (duplicate_of is distinct from id);
