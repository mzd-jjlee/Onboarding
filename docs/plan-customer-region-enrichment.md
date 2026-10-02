# 계획: 고객 지역(region) 보강 + 고객별 매출 요약

상태: **계획 단계** (구현 전). 진행 순서: 문서 작성 → **계획(현재 위치)** → 구현 → 테스트 → 리뷰.

## 배경 / 목적
현재 ETL은 `sales_raw.csv` 단일 소스만 다룬다. 두 번째 소스를 extract해 조인하는 연습으로, 고객의 지역(region) 정보를 추가하고 고객별 매출 요약 테이블을 만든다.

## 스코프
- 새 extract 소스: `data/customers_raw.csv`
- `sales` 테이블에 `region` 컬럼 추가 (조인 결과)
- 신규 `customer_summary` 테이블 추가 (고객별 집계)
- 기존 `sales_raw.csv` extract/transform 로직은 그대로 재사용, 확장만 함

## 1. Extract — 어디서 가져오나
- `data/customers_raw.csv` 신규 생성 (컬럼: `customer,region,signup_date`)
- 기존 `extract()` 함수를 경로 인자 그대로 재사용해서 두 번 호출 (`sales_raw.csv`, `customers_raw.csv`) — 함수 자체는 CSV 포맷에 무관하므로 수정 불필요
- 샘플 데이터는 일부러 지저분하게 구성해 정제 로직을 테스트할 수 있게 함:
  - 동일 `customer`가 두 번 등장 (중복 고객 → 첫 값 유지)
  - `region`이 빈 값인 행 (제외 대상)
  - `sales_raw.csv`에는 있지만 `customers_raw.csv`에는 없는 고객 (조인 시 `region = "Unknown"` 처리)

## 2. Transform — 정제/조인 규칙
`transform_customers(rows)` 신규 함수:
- `customer` 중복 시 첫 값 유지 (skip)
- `region`이 빈 문자열이면 skip
- 결과: `{customer, region, signup_date}` dict 리스트

`transform(rows)` (기존 sales 정제)는 그대로 유지.

`enrich_with_region(sales_rows, customers_rows)` 신규 함수:
- `customers_rows`를 `customer` 기준 dict로 인덱싱
- 각 sales row에 `region` 추가, 매칭 안 되면 `"Unknown"`

`summarize_by_customer(enriched_rows)` 신규 함수:
- `customer, region` 기준 집계: `order_count`, `total_amount`(sum of `total`)
- 반환: `{customer, region, order_count, total_amount}` dict 리스트

## 3. Load — 스키마 변경
- `sales` 테이블: 기존 스키마에 `region TEXT` 컬럼 추가
- 신규 `customer_summary` 테이블:
  ```sql
  CREATE TABLE customer_summary (
      customer TEXT PRIMARY KEY,
      region TEXT,
      order_count INTEGER,
      total_amount REAL
  )
  ```
- 기존과 동일하게 매 실행마다 `DROP TABLE IF EXISTS` 후 재생성 (멱등성 유지)

## 4. main() 파이프라인 변경
```
raw_sales = extract(RAW_CSV)
raw_customers = extract(CUSTOMERS_CSV)

clean_sales = transform(raw_sales)
clean_customers = transform_customers(raw_customers)

enriched_sales = enrich_with_region(clean_sales, clean_customers)
summary = summarize_by_customer(enriched_sales)

load_sales(enriched_sales, DB_PATH)
load_customer_summary(summary, DB_PATH)
```

## 5. 테스트 계획 (구현 후 진행)
- `transform_customers`: 중복 고객 제거, 빈 region 제외 확인
- `enrich_with_region`: 매칭되는 케이스 / `customers_raw.csv`에 없는 고객이 `"Unknown"`으로 처리되는 케이스
- `summarize_by_customer`: 동일 고객 여러 주문의 `order_count`/`total_amount` 합산 정확성
- 전체 파이프라인 실행 후 `sales.db`를 열어 `sales.region`, `customer_summary` 로우 수/값 스팟체크
- 재실행 시 멱등성 확인 (두 번 실행해도 동일 결과)

## 6. 리뷰 체크리스트 (구현 후 진행)
- CLAUDE.md 규칙 위반 없는지 (표준 라이브러리만 사용, 조용한 필터링 동작 일관성)
- 신규 함수들이 기존 `extract/transform/load` 네이밍·구조 패턴과 일관되는지
- `Unknown` region 처리가 명시적으로 문서화·테스트되는지 (silent bug 방지)
- 컬럼/테이블 스키마 변경이 `docs/etl-current.md`에도 반영되는지

## 산출물 (구현 단계에서 만들 것)
- `data/customers_raw.csv` (신규)
- `etl.py` 수정 (함수 추가: `transform_customers`, `enrich_with_region`, `summarize_by_customer`, `load` 분리 또는 확장)
- 테스트 코드 (예: `test_etl.py`, stdlib `unittest` 사용 — 외부 의존성 없음 원칙 유지)
