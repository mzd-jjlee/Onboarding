# ETL 현황 문서 (as-is)

## 목적
`data/sales_raw.csv`에 있는 원본 판매 기록을 정제해 `data/sales.db`(SQLite)의 `sales` 테이블로 적재한다. 외부 라이브러리 없이 표준 라이브러리(`csv`, `sqlite3`, `pathlib`)만 사용한다.

## 데이터 흐름

```
data/sales_raw.csv --extract--> raw_rows (list[dict])
                    --transform--> clean_rows (list[dict])
                    --load--> data/sales.db :: sales 테이블
```

## 단계별 동작 (`etl.py`)

### extract(path)
- CSV를 `csv.DictReader`로 읽어 dict의 리스트로 반환한다.
- 별도 검증 없음 — 원본 그대로 반환.

### transform(rows)
입력 컬럼: `order_id, customer, product, quantity, unit_price, order_date`

필터링 규칙 (에러 없이 조용히 skip):
- `order_id`가 이미 나온 값이면 skip (중복 주문 제거, 첫 번째 값만 유지)
- `customer` 또는 `quantity`가 빈 문자열이면 skip

변환 규칙:
- `order_id` → `int`
- `quantity` → `int`
- `unit_price` → `float`
- `total = round(quantity * unit_price, 2)` 파생 컬럼 추가

주의: `quantity`/`unit_price`가 숫자가 아닌 문자열이면 `int()`/`float()`에서 예외 발생 (빈 값 케이스만 방어됨).

### load(rows, db_path)
- 매 실행마다 `sales` 테이블을 `DROP TABLE IF EXISTS` 후 `CREATE TABLE`로 재생성 → 멱등적 재실행 가능.
- `executemany`로 일괄 INSERT, `order_id`를 PRIMARY KEY로 사용.

## 현재 샘플 데이터 (`data/sales_raw.csv`)
9개 행 중:
- `1002` 주문이 중복 → 마지막 행은 transform에서 제거됨
- `1003` 행은 `quantity`가 빈 값 → 제거됨
- `1006` 행은 `customer`가 빈 값 → 제거됨
- 결과적으로 6개 행이 적재됨

## 알려진 한계
- 단일 소스(sales_raw.csv)만 다룸 — 조인/보강 로직 없음
- 필터링된 행에 대한 로그/사유 기록이 없음 (단순 skip)
- 스키마 변경 시 마이그레이션 개념 없이 DROP/CREATE로만 처리
