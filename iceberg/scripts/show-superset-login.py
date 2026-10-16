"""로컬 웹 로그인 정보만 출력한다 (DB 비밀번호·암호화 키 제외)."""
from pathlib import Path
for line in (Path(__file__).resolve().parent.parent / '.env.superset').read_text().splitlines():
    if line.startswith(('SUPERSET_ADMIN_USERNAME=', 'SUPERSET_ADMIN_PASSWORD=')):
        print(line)
print('http://localhost:8088/superset/dashboard/local-iceberg/')
