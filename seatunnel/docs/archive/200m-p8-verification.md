# 2억 행 P8 실행 검증 — 2026-09-14

- Job ID: 1151776238910570497
- 사용자 클라이언트 통계: FINISHED, 431초, 읽기/쓰기 200,000,000, 실패 0.
- 설정: parallelism=8, partition_num=8, fetch_size=5000.
- Node 1 실제 Source 시작 index 0,2,4,6 (사용자 표기 1,3,5,7), TaskGroup 3,5,7,9. SplitEnumerator 그룹 1 및 JobMaster/Coordinator 담당.
- Node 2 실제 Source 시작 index 1,3,5,7 (사용자 표기 2,4,6,8), TaskGroup 4,6,8,10. AggregatedCommitter 그룹 2 담당.
- 배치 계획뿐 아니라 각 노드 TaskExecutionService 및 SourceSeaTunnelTask 시작 로그로 대조함. 전체 작업 상태를 모아서 출력하는 Coordinator 로그만으로 실행 위치를 판단하지 않음.
- Node 2: rename file ... finish 200건. 해당 실행 구간 already finished 커밋 skip 0건. 해당 Job ID가 붙은 ERROR 로그 두 노드 모두 0건.
- 최종 output/production_orders_200m: Parquet 200개, 메타데이터 총 200,000,000행, 1,558,402,608바이트. 파일 이름의 Job ID 모두 이번 실행과 일치.
- 이번 확인은 메타데이터/로그 기반. 전체 키의 누락·중복 및 모든 컬럼 원본 대조는 재실행하지 않음.

## 성능 해석

이전 P4 271초 대비 P8 431초: 160초 증가, 소요 시간 약 59% 증가. 서로 다른 시점의 단일 실행 비교로 캐시·다른 부하를 통제하지 않았으므로 원인을 병렬도 하나로 확정하지 않는다.

07:07:35~07:14:47 UTC HealthMonitor 샘플:

- 두 노드 모두 processors=6, physical.memory.total=9.7G, heap.memory.max=3.0G.
- Node 1 힙 최대 사용률(관측 샘플) 75.75%, 시스템 CPU 95% 이상 16/20회.
- Node 2 힙 최대 사용률(관측 샘플) 72.96%, 시스템 CPU 95% 이상 17/21회.
- 두 노드의 load.system은 공유 VM에 대한 관측이므로 합산하지 않는다.
- CPU 여유가 적었던 것은 확인되나 DB/인코딩/디스크 중 정확한 병목과 이전 대비 느려진 원인을 확정할 프로파일링은 없다.

원본 로그 조회본: /private/tmp/seatunnel-p8-node1.log 및 /private/tmp/seatunnel-p8-node2.log. 임시 디렉터리는 재시작/정리 시 사라질 수 있다.
