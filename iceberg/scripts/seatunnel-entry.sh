#!/bin/sh
set -eu
# The bundled OpenGauss JDBC driver can intercept PostgreSQL URLs.
if [ -f lib/opengauss-jdbc-5.1.0.jar ]; then
  mv lib/opengauss-jdbc-5.1.0.jar lib/opengauss-jdbc-5.1.0.jar.disabled
fi
# 첫 번째 인자로 받은 job 설정을 읽어 같은 컨테이너의 JVM/Zeta에서 실행한다.
# 실제 파일 작성·HMS 커밋은 job에 지정된 Iceberg 커넥터가 수행한다.
exec ./bin/seatunnel.sh --config "$1" -m local
