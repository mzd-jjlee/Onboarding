# openmetadata/ — 프로젝트 배경

## 미션

팀장님 지시사항 (온보딩 첫 과제):

> Apache OpenMetadata (https://open-metadata.org/) 에 대해서
> 어떤 도구인지 / 왜 필요한지 / 실제로 어떻게 사용하는지 정도를
> 간단한 시연과 함께 소개해주시면 될 것 같아요!

발표 대상: 팀 내부 온보딩 공유. 발표일: 2026-09-03.

## 세션 시작 시 확인할 것

**작업을 시작하기 전에 `docs/memo.md`가 있으면 먼저 읽고, 직전 세션에서 어디까지 했는지 파악할 것.**
이 파일은 매 세션 종료 시 그 시점 기준으로 덮어써지는 인계 노트이며, "현재 진행 상태"의 유일한 출처다.
이 CLAUDE.md에는 진행 상태를 적지 않는다 (memo.md와 이중관리 방지).

## 핵심 산출물 위치

- `docs/openmetadata-overview.md` — OpenMetadata 개념 설명 문서 (무엇/왜/어떻게)
- `docs/openmetadata-demo-design.md` — 로컬 데모 환경 설계 근거
- `docs/openmetadata-onboarding-slides.pptx` — 발표용 슬라이드 (PowerPoint에서 사용자가 직접 편집 중일 수 있음 — 먼저 열려있는지 확인 없이 덮어쓰지 말 것)
- `docs/openmetadata-presentation-script.md` — 발표 대본(큐카드)
- `docs/memo.md` — 세션 간 작업 인계 노트 (최신 상태만 유지, 로그 아님)

그 외 구성(docker-compose 파일, DAG, 접속 정보 등)은 상위 `../CLAUDE.md`에 정리되어 있다.
