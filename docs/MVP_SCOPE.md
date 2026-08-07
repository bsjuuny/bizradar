# MVP Scope

## Target customer

IT/SI 기업, 웹에이전시, AI 개발사, IT 스타트업 - 직원 5~50명 규모.

## In scope (6 core features)

1. **Project Radar** - 나라장터 공공 IT 프로젝트 발견
2. **Support Radar** - 기업마당/K-Startup 정부지원사업 발견
3. **Market Radar** - 공공 IT 시장 흐름 분석/통계
4. **Company Match** - 회사 프로필 기반 점수 매칭 (rule engine, not AI)
5. **Saved Opportunities**
6. **Watch Conditions**

## Explicitly out of scope for MVP

AI Chat, RAG, Vector DB, Kafka, Redis, Celery, Elasticsearch, Kubernetes, microservice
split, automatic proposal generation, 낙찰확률 예측, freelancer matching, CRM, Slack,
Kakao, SMS, OCR, full legacy-HWP support.

If a task seems to need any of the above, it's a sign the task has grown past MVP scope -
flag it instead of building it.

## Phase plan

| Phase | Scope |
|---|---|
| 0 | Repo + architecture + testing foundation |
| 1 | Supabase migration + auth + company profile |
| 2 | G2B collector + raw data + normalization |
| 3 | Project UI |
| 4 | Ollama + structured analysis |
| 5 | Match engine |
| 6 | BizInfo + K-Startup + Support Radar |
| 7 | Market Radar |
| 8 | Saved + Watch |
| 9 | Error handling + security |
| 10 | Full regression + Railway readiness |

Current status: **Phase 0 in progress.** See `docs/VERIFICATION_REPORT.md` for what has
actually been run and passed vs. what is not yet implemented.
