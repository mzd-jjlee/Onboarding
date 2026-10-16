# Superset 웹에서 Iceberg 조회

2026-10-07 Superset 6.0.0과 Trino 483을 연결했다. 주문 Dataset과 주문 목록·상태별 금액 차트, 대시보드를 등록했다.

## 지금 열어보기

[주문 대시보드](http://localhost:8088/superset/dashboard/local-iceberg/)에 접속한다.
로그인 정보는 Mac 터미널의 `Onboarding/iceberg` 폴더에서 확인한다.

```sh
python3 scripts/show-superset-login.py
```

계정은 `admin`이며, 생성된 비밀번호는 `.env.superset`에 보관한다. 이 파일은 Git에서 제외된다. 기존 계정이 있으면 초기화 스크립트가 비밀번호를 바꾸지 않는다.

대시보드에는 주문 5건과 상태별 금액(DONE 113000, NEW 57000)이 표시된다. 총금액은 170000이다.

직접 SQL을 쓰려면 상단 **SQL → SQL Lab**에서 Database `Local Iceberg / Trino`, Catalog `iceberg`, Schema `retail`을 선택하고 실행한다.

```sql
SELECT * FROM iceberg.retail.orders ORDER BY order_id;
SELECT status, COUNT(*) AS order_count, SUM(amount) AS total_amount
FROM iceberg.retail.orders GROUP BY status ORDER BY status;
```

## 다음에 다시 기동하기

Mac 터미널에서 실행한다. 이미지 빌드, 전용 DB 초기화, 웹 서버 기동, 연결·차트 등록을 순서대로 수행한다. 기존 이름의 항목이 있으면 재사용한다.

```sh
cd /Users/mz01-jaejunlee/projects/Onboarding/iceberg
bash scripts/up-superset.sh
```

이미 초기화를 마쳤고 컨테이너만 다시 켜려면:

```sh
docker compose -f compose.yaml -f compose.analytics.yaml up -d --wait superset
```

기존 Iceberg 파일과 HMS DB를 사용하며 SeaTunnel APPEND job을 재실행하지 않는다.

## 어디에 연결되는가

```text
브라우저 localhost:8088
  → Superset (웹 화면 / SQL 요청)
  → trino://superset@trino:8080/iceberg
  → Trino → HMS (현재 metadata JSON 위치 확인)
           → /lake (JSON → Avro → Parquet 읽기)
```

Superset의 Dataset은 `iceberg.retail.orders`를 조회하기 위한 정의다. 주문 데이터를 Superset DB로 복사하지 않는다. 컨테이너 내부에서 Trino 주소는 `trino:8080`, Mac의 DBeaver에서는 `localhost:8081`이다.

| 설정 파일 | 역할 |
|---|---|
| `compose.analytics.yaml` | Trino, Superset, 전용 PostgreSQL 실행 |
| `config/Dockerfile.superset` | Superset 6.0.0에 Trino 0.336.0 SQLAlchemy 드라이버와 PostgreSQL 드라이버 설치 |
| `config/superset/superset_config.py` | Superset 전용 DB 연결, 암호화 키, 동기 조회 설정 |
| `scripts/superset-init.sh` | Superset 내부 DB 테이블·관리자·권한 초기화 |
| `scripts/bootstrap_superset.py` | REST API로 Trino 연결·Dataset·차트·대시보드 등록 |
| `.env.superset` | 로컬 비밀번호 및 암호화 키 (보존 필요) |

`catalog-db`는 HMS의 테이블 등록정보를 보관한다. 별도 `superset-db`는 Superset 사용자, 연결 설정, Dataset, 차트, 대시보드, SQL 조회 이력을 보관한다. 전용 DB는 Compose가 실행하며, `superset db upgrade`가 내부 테이블을 준비한다. 전용 Docker 볼륨과 `.env.superset`을 함께 보존해야 기존 설정을 계속 사용할 수 있다.

이번 구성은 로컬 동기 SQL 조회용이다. 예약 보고서·비동기 작업용 Redis/Celery는 구성하지 않았다. 호스트 공개 포트는 루프백 8088이며 Trino Iceberg catalog는 READ_ONLY다.

## 실행 기록

`evidence/superset/setup.json`에 생성된 항목 ID와 대시보드 주소, `chart-*.json`에 실제 차트 조회 응답, `sql-lab.json`에 SQL Lab 조회 응답을 남겼다. 인증 토큰·비밀번호는 기록하지 않는다.

Chrome에서 실제 로그인 후 주문 5행과 DONE 113k / NEW 57k 막대 차트가 표시되는 것까지 확인했다 (`evidence/superset/browser-check.md`).
