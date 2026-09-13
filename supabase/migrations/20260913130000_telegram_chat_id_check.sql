-- telegram_chat_id는 지금 애플리케이션 레이어(apps/web/src/app/(app)/settings/actions.ts)
-- 에서만 숫자 형식을 검증한다. docs/DATABASE.md의 "애플리케이션 레이어를 유일한 방어선으로
-- 신뢰하지 않는다" 원칙에 따라, 직접 REST PATCH로 임의 문자열이 들어가는 것도 DB에서 막는다.
-- 텔레그램 chat id는 그룹/채널이면 음수일 수 있어 부호는 허용한다.
alter table companies
  add constraint companies_telegram_chat_id_format
    check (telegram_chat_id is null or telegram_chat_id ~ '^-?[0-9]+$');
