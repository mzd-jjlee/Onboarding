# MinIO(S3 호환 저장소)에 Iceberg 테이블 적재하기

> 상태: **2026-11-11 실행 확인 완료.** 아래 "실행 기록"의 결과는 실제 실행으로 확인한 것이다.

## 왜 하는가

지금까지 만든 Iceberg 테이블은 모두 호스트의 `./lake` 폴더(`file:///lake/...`)에 있다.
실무 레이크하우스는 보통 로컬 디스크 대신 **객체 저장소**(Amazon S3, GCS 등)에 파일을 둔다.
여러 서버가 같은 파일을 네트워크로 읽고 쓸 수 있고, 용량을 따로 관리하지 않아도 되기 때문이다.

- **객체 저장소**: 파일을 폴더 트리가 아니라 `bucket` + `key`(경로처럼 생긴 이름)로 저장하고, HTTP API(S3 API)로 읽고 쓰는 저장소.
- **MinIO**: S3와 같은 API로 동작하는 저장소 서버. Docker 컨테이너로 내 PC에 띄우므로 **AWS 계정·비용·외부 통신이 필요 없다.**
  접속 키도 AWS가 발급하는 게 아니라 우리가 만든 로컬 값이다.

## 바뀌는 것과 안 바뀌는 것

```
지금:   SeaTunnel ──쓰기──▶ ./lake            (file:///lake/...)       ◀──읽기── Trino catalog "iceberg"
이번:   SeaTunnel ──쓰기──▶ MinIO bucket      (s3a://lakehouse/...)    ◀──읽기── Trino catalog "iceberg_s3"
              └──커밋──▶ HMS (둘 다 같은 HMS) ◀──metadata 위치 확인──┘
```

- **파일 저장 위치만 바뀐다.** Parquet·manifest(Avro)·metadata.json이 bucket `lakehouse`에 생긴다.
- **HMS는 그대로 카탈로그다.** 테이블의 현재 metadata.json 주소를 기록하는 역할은 같고, 그 주소가 `s3a://...`일 뿐이다.
  S3는 HMS를 대체하지 않는다. **HMS는 카탈로그, S3는 파일 저장소**다.
- **기존 데이터는 이동하지 않는다.** `retail.*`, `public_api.weather_hourly`, `./lake`는 손대지 않는다.
  새 namespace `public_api_s3`에 **새 테이블을 하나 더** 만든다. (Iceberg metadata 안의 절대 경로를 바꿔서 옮기는 방법은 쓰지 않는다.)

## 이 폴더(iceberg/)에 두는 게 맞나

**맞다.** MinIO는 새 프로젝트가 아니라 **이 레이크하우스의 저장소 계층을 하나 더 추가하는 것**이다.

- 같은 HMS(`hms:9083`), 같은 SeaTunnel, 같은 Trino가 MinIO를 써야 하고, 이들은 `iceberg-learning-net` 네트워크의 서비스 이름으로 통신한다.
  별도 폴더(별도 Compose 프로젝트)로 빼면 네트워크가 갈라져서 `minio`라는 이름으로 서로 찾지 못하고, `host.docker.internal`을 경유해야 한다.
- 원본 데이터도 이 폴더의 `public_api.weather_hourly`이고, 검증도 Trino에서 두 테이블을 바로 비교한다.
- 다만 기존 서비스와 섞이지 않게 **저장소 서버는 별도 파일 `compose.minio.yaml`**에 둔다 (Trino·Superset을 `compose.analytics.yaml`로 분리한 것과 같은 방식).

## 구성 요소와 파일

| 파일 | 역할 |
|---|---|
| `compose.minio.yaml` | MinIO 서버(`minio`, API 9000·웹 콘솔 9001)와 bucket 생성 도구(`minio-init`) |
| `scripts/prepare_minio_env.py` | `.env.minio`(로컬 접속 키) 생성. 한 번 만들면 다시 바꾸지 않는다. Git 제외 |
| `scripts/up-minio.sh` | 키 생성 → MinIO 기동 → bucket 생성 → HMS·Trino 재생성(S3 설정 읽기) |
| `config/hadoop/core-site.xml` | HMS가 `s3a://` 경로를 쓸 때 쓰는 접속 설정(endpoint, path-style) |
| `compose.yaml` (수정) | HMS: S3 JAR 클래스패스·core-site·키 / SeaTunnel: 키·CSV 폴더 마운트 |
| `compose.analytics.yaml` (수정) | Trino: 키 |
| `config/trino/catalog/iceberg_s3.properties` | MinIO를 읽는 Trino catalog `iceberg_s3` (READ_ONLY) |
| `scripts/prepare-public-api-s3-catalog.py` | HMS에 namespace `public_api_s3`(location `s3a://lakehouse/warehouse/public_api_s3.db`) 생성 |
| `jobs/05_weather_to_minio_iceberg.conf` | SeaTunnel: CSV → Iceberg sink(S3 warehouse) |
| `scripts/load-weather-to-minio.py` | 원본 snapshot 고정 → CSV → 선행 검사 → 적재 → 전 행 대사. 원시 job 직접 실행 금지 |

### 왜 HMS·SeaTunnel·Trino 모두 S3 설정이 필요한가

세 컴포넌트가 **각자 직접** MinIO에 접근하기 때문이다.

| 컴포넌트 | MinIO에서 하는 일 | 사용하는 라이브러리 |
|---|---|---|
| HMS | namespace·테이블을 만들 때 그 위치(폴더)가 있는지 확인하고 만든다 | Hadoop `s3a` (이미지의 `tools/lib`에 있으나 기본 클래스패스 밖 → `HADOOP_CLASSPATH`로 추가) |
| SeaTunnel | Parquet·manifest·metadata.json을 쓴다 | Hadoop `s3a` (이미지 `lib/`에 `seatunnel-hadoop-aws.jar`, `aws-java-sdk-bundle` 포함) |
| Trino | metadata·manifest·Parquet을 읽는다 | Trino 자체 S3 구현(`fs.native-s3.enabled`) |
| Superset | MinIO에 접근하지 않는다. Trino에 SQL만 보낸다 | — |

같은 목적의 설정도 이름이 다르다: Hadoop은 `fs.s3a.endpoint`, Trino는 `s3.endpoint`.
접속 키는 세 곳 모두 환경변수 `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`(값은 `.env.minio`)로 받아서, 설정 파일에는 키를 적지 않는다.

### 설계에서 고른 것과 이유

- **`s3a://` 경로 + Hadoop 파일 IO**: Iceberg 전용 `S3FileIO`를 쓰려면 SeaTunnel에 Iceberg AWS 모듈과 AWS SDK v2 JAR을 추가해야 한다.
  `s3a`는 HMS·SeaTunnel 이미지에 이미 들어 있는 JAR로 동작할 가능성이 있어 먼저 시도한다. Trino는 `s3a://`도 S3 경로로 읽는다.
- **path-style 접속**: AWS는 `http://bucket.host/` 형태를 기본으로 쓰지만, 로컬 MinIO는 `http://minio:9000/bucket/` 형태로 접속해야 한다.
- **Docker 볼륨 `minio-data`**: `./lake`처럼 호스트 폴더로 보지 않고, 파일은 항상 S3 API(웹 콘솔, Trino, `mc`)로 확인한다. 객체 저장소다운 사용법이다.
- **원본 snapshot 고정**: 매일 09:00 Airflow가 원본 테이블에 append한다. 복사 중간에 행이 늘지 않도록 원본을 `FOR VERSION AS OF <snapshot_id>`로 읽는다.
- **MinIO 이미지**: 공식 `minio/minio` 이미지는 Docker Hub에서 받을 수 없다(2026-11-10 확인: "repository does not exist").
  커뮤니티 빌드 `pgsty/minio`(MinIO 소스 그대로 빌드, Docker Hub 약 390만 pull)를 고정 버전으로 쓴다. **서드파티 이미지이므로 사용 전 사용자 승인이 필요하다.**
- **관리자 키를 S3 키로 그대로 사용**: 로컬 실습 단순화. 운영이라면 버킷 권한만 가진 별도 사용자를 만든다.

## 실행 순서

호스트, `iceberg/` 폴더에서 실행한다. 기존 스택(HMS, Trino)이 떠 있어야 한다.

```bash
cd /Users/mz01-jaejunlee/projects/Onboarding/iceberg

# 1. 키 생성 + MinIO 기동 + bucket 생성 + HMS·Trino 재생성
bash scripts/up-minio.sh
```

성공하면: 마지막에 `MinIO console: http://localhost:9001`이 출력된다. `docker ps`에 `iceberg-learning-minio-1`이 보이고,
`hms`, `trino`가 방금 재시작된 상태(Up 1분 이내)가 된다. 웹 콘솔 로그인 정보는 `.env.minio`의 `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`이며,
bucket `lakehouse`가 비어 있는 상태로 보인다.

```bash
# 2. 원본 날씨 테이블을 MinIO 위 Iceberg 테이블로 복사 (한 번만 적재, 재실행 시 동일하면 skip)
python3 scripts/load-weather-to-minio.py
```

성공하면: `"status": "PASS"`, `"action": "LOAD"`, `"rows"`가 원본 행 수(2026-11-10 기준 576)와 같다.
다시 실행하면 `"action": "SKIP_IDENTICAL"`이 나오고 행이 늘지 않는다.

```bash
# 3. 조회와 확인
bash scripts/trino.sh --execute "SELECT count(*), min(weather_time), max(weather_time) FROM iceberg_s3.public_api_s3.weather_hourly"
bash scripts/trino.sh --execute 'SELECT file_path FROM iceberg_s3.public_api_s3."weather_hourly$files"'
```

성공하면: 행 수가 2단계와 같고, `file_path`가 `s3a://lakehouse/warehouse/public_api_s3.db/weather_hourly-.../data/...parquet`로 시작한다.
웹 콘솔 bucket `lakehouse`에서 `metadata/`(json, avro)와 `data/`(parquet) 폴더가 보인다.

## 처음 하는 사람이 밟을 함정

- **컨테이너 안의 `localhost`**: SeaTunnel·HMS·Trino는 `http://minio:9000`(서비스 이름)으로 접속한다. `localhost:9000`은 각 컨테이너 자기 자신이다.
  호스트 브라우저에서만 `localhost:9001`(콘솔)을 쓴다.
- **포트 9000(API) / 9001(콘솔)**: 이 프로젝트 포트 표에는 겹치는 곳이 없다(2026-11-10 `lsof`로 미사용 확인). `127.0.0.1`에만 공개한다.
- **HMS·Trino 재생성**: `.env.minio`와 S3 설정을 읽으려면 컨테이너를 다시 만들어야 한다. HMS 등록 정보는 `catalog-db` 볼륨에 있어 유지되지만,
  재생성하는 1분 남짓 동안 Trino 조회와 Airflow 적재가 실패할 수 있다. **매일 09:00(Airflow 실행) 근처에는 하지 않는다.**
- **`.env.minio`가 없을 때**: HMS·SeaTunnel·Trino는 키 없이도 뜬다(`required: false`). 기존 `file:` 테이블은 그대로 동작하고 S3 접근만 실패한다.
- **`iceberg_s3` catalog로 기존 테이블 조회**: 같은 HMS를 보므로 `iceberg_s3.retail.orders`도 목록에는 보이지만, 파일이 `file:` 경로라 읽을 수 없다.
  기존 테이블은 계속 `iceberg` catalog로 조회한다.
- **원시 job 직접 실행 금지**: `05_weather_to_minio_iceberg.conf`도 `APPEND_DATA`라 두 번 실행하면 행이 중복된다. 항상 `load-weather-to-minio.py`로 실행한다.

## 실행 기록

### 2026-11-11 첫 실행 (Rancher Desktop, 사용자 승인 후 `pgsty/minio` 이미지 사용)

| 확인 항목 | 결과 |
|---|---|
| `up-trino.sh` (`.env.minio` 없는 상태) | HMS·Trino healthy. `iceberg_s3` catalog가 있어도 기존 조회 정상: orders 5건/170000, weather 576행 |
| `up-minio.sh` | `.env.minio` 생성, bucket `lakehouse` 생성, HMS·Trino 재생성 후 healthy |
| `load-weather-to-minio.py` 1회차 | `PASS` / `LOAD` / 576행, 원본 snapshot `6575098936787609950` |
| 원본 snapshot과 양방향 `EXCEPT` | 0행 / 0행 (값까지 일치) |
| 데이터 파일 위치 | Parquet 1개(576행), `s3a://lakehouse/warehouse/public_api_s3.db/weather_hourly/data/...` |
| bucket 내용(`mc ls -r`) | `data/` Parquet 1개, `metadata/` metadata.json 2개(빈 테이블 + 1커밋), manifest list 1개, manifest 1개 |
| 재실행 | `PASS` / `SKIP_IDENTICAL` / 576행 (중복 없음) |
| 기존 `./lake` | 파일 72개 SHA-256이 실행 전후 동일 |

- 실행 기록: `evidence/minio/20261111T051028Z-82245d3c/` (report.json, CSV, catalog·SeaTunnel 로그). 새 evidence는 `.gitignore` 대상이다.
- 실행 시 Airflow는 기동되어 있지 않았다 (원본 append와 겹치지 않음).
