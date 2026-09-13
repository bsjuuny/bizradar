-- Telegram Watch 다이제스트: 이메일/슬랙 발송 인프라가 없어(MVP_SCOPE.md도 Slack/Kakao/
-- SMS를 명시적으로 범위 밖으로 뺌) 텔레그램 봇 하나만 붙인다. 회사가 Settings에서 자신의
-- chat_id를 등록해 두면, worker/jobs/digest_job.py가 활성 watch_conditions에 새로 걸리는
-- 공고를 찾아 그 chat_id로 보낸다.

alter table companies add column telegram_chat_id text;

-- companies의 UPDATE 권한은 20260809031000_fix_approval_status_grant.sql에서 컬럼
-- 화이트리스트로 바뀌었다(테이블 전체 grant가 아님) - 새 컬럼도 명시적으로 추가해야
-- Settings 저장이 동작한다.
grant update (telegram_chat_id) on companies to authenticated;

-- 이미 보낸 (company, opportunity) 쌍을 기록해 다이제스트 중복 발송을 막는다. worker
-- (service_role, RLS 우회)만 쓰고 읽는 내부 상태라 authenticated 정책은 두지 않는다
-- (RLS는 켜 두되 정책 없음 = 기본 거부, docs/DATABASE.md의 "RLS는 테스트 통과를 위해
-- 끄지 않는다" 원칙과 일치).
create table watch_notifications_sent (
  company_id uuid not null references companies (id) on delete cascade,
  opportunity_id uuid not null references opportunities (id) on delete cascade,
  sent_at timestamptz not null default now(),
  primary key (company_id, opportunity_id)
);

alter table watch_notifications_sent enable row level security;
