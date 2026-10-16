# 3GiB 힙 포화로 중단한 첫 시도

실제 Java 명령줄: `-Xms512m -Xmx3g -XX:+UseG1GC`. 기본 힙 512MB가 원인은 아니다.
GC.class_histogram 주요 항목: char[] 약 1.84GB, StructLikeWrapper 6,528,512개,
BaseTaskWriter$PathOffset 6,528,508개, StructCopy 6,528,508개.
HMS 테이블 metadata JSON: identifier-field-ids=[1], current-snapshot-id=-1.
SeaTunnel 2.3.13 IcebergWriterFactory는 identifierFieldIds가 있으면 upsert=false여도 Delta writer를 선택한다.
https://github.com/apache/seatunnel/blob/2.3.13/seatunnel-connectors-v2/connector-iceberg/src/main/java/org/apache/seatunnel/connectors/seatunnel/iceberg/sink/writer/IcebergWriterFactory.java

첫 시도는 성공 커밋 없이 수동 중지했다. exit 137은 stop timeout 후 종료된 결과이며 자동 OOM kill이라고 단정하지 않는다.
기존 512MB LocalFile OOM과는 다르다. 당시 증거는 seatunnel/output/oom-study/20260915 및 발표자료 16~17쪽.
복구: 첫 빈 테이블을 HMS API로 별도 이름에 보존하고 새 경로에 identifier 없는 append 테이블을 만든다.
