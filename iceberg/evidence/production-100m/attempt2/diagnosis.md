# 대상 테이블의 identifier 제거만으로 충분하지 않음

SeaTunnel IcebergSink 생성자는 원본 CatalogTable의 PK를 sink config의 primaryKeys로 자동 복사한다.
대상 테이블을 identifier 없이 생성해도 source PK가 남으면 Delta writer를 선택한다.
두 번째 힙 histogram도 StructLikeWrapper 약 637만 개로 동일한 누적 패턴이었다.
성공 스냅샷과 data 파일 없이 수동 중지했다.
최종 수정은 SQL projection 2개로 order_id 이름을 임시 변경·복원해 원본 PK 메타데이터를 제거한다.
값과 최종 컬럼명은 유지하며 SQLTransform의 출력 컬럼 기준 PK 보존 조건을 이용한다.
https://github.com/apache/seatunnel/blob/2.3.13/seatunnel-transforms-v2/src/main/java/org/apache/seatunnel/transform/sql/SQLTransform.java
