"""Build the guide's offline SVG diagrams and HTML using only the standard library."""
from pathlib import Path
import html
import re

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / 'assets' / 'lakehouse'
ASSETS.mkdir(parents=True, exist_ok=True)
COLORS = {'blue': ('#eaf2ff', '#2963ba'), 'green': ('#e8f6ee', '#26784c'),
          'purple': ('#f1edff', '#7354ac'), 'orange': ('#fff2df', '#986014'),
          'gray': ('#f0f3f6', '#566779')}


class Diagram:
    def __init__(self, title, subtitle, height=520):
        self.height = height
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}" role="img" aria-label="{html.escape(title)}">',
                      f'<title>{html.escape(title)}</title><desc>{html.escape(subtitle)}</desc>',
                      '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#68798a"/></marker></defs>',
                      '<rect width="1200" height="100%" rx="18" fill="#ffffff"/>',
                      '<style>text{font-family:"Apple SD Gothic Neo","Malgun Gothic",sans-serif;fill:#203349} .title{font-size:27px;font-weight:700} .sub{font-size:18px;fill:#53677b} .node{font-size:21px;font-weight:700} .body{font-size:17px} .label{font-size:16px;fill:#53677b}</style>']
        self.text(35, 44, title, 'title')
        self.text(35, 76, subtitle, 'sub')

    def text(self, x, y, text, cls='body', anchor='start'):
        self.parts.append(f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}">{html.escape(text)}</text>')

    def box(self, x, y, w, title, lines=(), color='blue', h=106):
        bg, stroke = COLORS[color]
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{bg}" stroke="{stroke}" stroke-width="1.5"/>')
        self.text(x+18, y+31, title, 'node')
        for i, line in enumerate(lines):
            self.text(x+18, y+60+i*24, line)

    def arrow(self, points, label=None, lx=None, ly=None, dashed=False):
        dash = ' stroke-dasharray="7 5"' if dashed else ''
        self.parts.append(f'<polyline points="{points}" fill="none" stroke="#68798a" stroke-width="2.2" marker-end="url(#arrow)"{dash}/>')
        if label:
            self.text(lx, ly, label, 'label', 'middle')

    def save(self, name):
        svg = '\n'.join(self.parts) + '\n</svg>\n'
        marker_id = 'arrow-' + Path(name).stem
        svg = svg.replace('id="arrow"', f'id="{marker_id}"').replace('url(#arrow)', f'url(#{marker_id})')
        (ASSETS / name).write_text(svg)


d = Diagram('01  ·  역할을 먼저 나누기', 'SQL은 DuckDB가 실행하고, Iceberg는 테이블을 구성하는 규칙을 제공한다.', 540)
d.box(35, 125, 235, '원본 DB', ['업무 데이터', 'PostgreSQL / MySQL'])
d.box(330, 125, 235, 'SeaTunnel Zeta', ['읽고 적재하는 엔진', 'LocalFile / Iceberg sink'])
d.box(635, 125, 235, '로컬 디스크', ['실제 데이터: Parquet', '테이블 정보: JSON / Avro'], 'green')
d.box(930, 125, 235, 'DuckDB', ['SQL · 집계 · 조인', '파일을 읽어 결과 생성'])
d.arrow('270,178 330,178'); d.arrow('565,178 635,178'); d.arrow('870,178 930,178', '읽기', 900, 164)
d.box(635, 310, 235, 'Hive Metastore', ['이름 → 현재 메타 위치', '카탈로그 서비스'], 'purple')
d.box(35, 310, 530, 'Iceberg = 테이블 포맷 + 구현', ['별도 SQL 서버가 아니라, 파일 집합과 버전을 관리하는 규약', 'writer와 reader 안의 라이브러리 / 확장이 처리한다'], 'orange')
d.arrow('1048,231 1048,365 870,365', '테이블 찾기', 1000, 345, True)
d.text(35, 493, '※ 조회 경로에 따라 PyIceberg가 파일을 읽어 DuckDB에 넘길 수도 있다. 그림 06에서 구분한다.', 'sub')
d.save('01-roles.svg')

d = Diagram('02  ·  파일 적재에 테이블 관리를 더하기', '같은 Parquet 파일이어도, 등록과 커밋 여부에 따라 Iceberg 테이블 포함 여부가 달라진다.', 480)
d.box(35, 125, 230, '지금까지', ['DB → SeaTunnel', '파일을 완성한다'], 'gray')
d.box(330, 125, 350, 'Parquet 파일들', ['a.parquet / b.parquet', '폴더의 파일을 직접 조회'], 'green')
d.box(765, 125, 395, 'DuckDB read_parquet()', ['파일 경로로 SQL 실행', 'Iceberg가 없어도 가능'])
d.arrow('265,178 330,178'); d.arrow('680,178 765,178')
d.box(35, 310, 230, '이번에 추가', ['PyIceberg 등록', '새 상태를 커밋'], 'orange')
d.box(330, 310, 350, 'Iceberg 스냅샷', ['이 버전의 파일은 a + b', '파일 목록 · 스키마 · 이력'], 'green')
d.box(765, 310, 395, '카탈로그를 통한 테이블 탐색', ['retail.orders → 현재 metadata', '선택된 스냅샷의 파일만 조회'], 'purple')
d.arrow('265,363 330,363'); d.arrow('765,363 680,363')
d.save('02-before-after.svg')

d = Diagram('03  ·  메타데이터는 어디에 저장될까?', '카탈로그 DB와 Iceberg 메타데이터 파일, 실제 행 데이터는 서로 다른 층이다.', 550)
d.box(35, 120, 1130, 'HMS 백엔드 DB: 이름과 현재 위치', ['retail.orders → metadata_location = file:///lake/.../00002-uuid.metadata.json'], 'purple', 87)
d.arrow('200,207 200,254', '위치를 따라 파일 읽기', 375, 239)
d.box(35, 254, 330, 'metadata JSON', ['테이블 스키마 · 파티션 정의', '현재 스냅샷 → S2'], 'orange')
d.box(435, 254, 330, 'manifest list', ['S2에 포함되는', 'manifest들의 목록'], 'orange')
d.box(835, 254, 330, 'manifest', ['데이터 파일 경로', '파티션 값 · 통계'], 'orange')
d.arrow('365,307 435,307'); d.arrow('765,307 835,307')
d.box(835, 415, 330, 'Parquet', ['실제 행: 1001, DONE, ...'], 'green', 88)
d.arrow('1000,360 1000,415')
d.text(35, 440, 'JSON과 Avro는 warehouse 등의 파일 저장소에 있다.', 'sub')
d.text(35, 474, 'HMS의 PostgreSQL에 Parquet 행을 적재하는 것이 아니다.', 'sub')
d.save('03-metadata.svg')

d = Diagram('04  ·  노트북 한 대의 배치 구조', '설계안 · 같은 Docker 네트워크에서 서비스 이름을 사용하고, 파일 경로는 /lake로 통일한다.', 665)
d.box(35, 125, 325, 'SeaTunnel 컨테이너', ['기존 Zeta 환경 활용', '파일 생성 / 테이블 쓰기'])
d.box(435, 125, 325, 'lab 컨테이너', ['Python + PyIceberg + DuckDB', '등록 스크립트 / SQL 조회'])
d.box(835, 125, 330, 'hms 컨테이너', ['Thrift: hms:9083', '테이블 등록 / 현재 위치'], 'purple')
d.arrow('760,178 835,178', 'RPC', 798, 162, True)
d.box(835, 310, 330, 'catalog-db', ['HMS용 PostgreSQL', '별도 DB 데이터 볼륨'], 'purple')
d.arrow('1000,231 1000,310', 'JDBC', 1040, 278, True)
d.box(35, 480, 1130, '호스트의 ./lake → 각 컨테이너의 /lake', ['landing: SeaTunnel 산출물     |     warehouse: Iceberg 메타데이터와 데이터 파일', '동일한 파일을 동일한 경로로 공유 · 컨테이너 삭제 후에도 호스트 파일은 보존'], 'green')
d.arrow('198,231 198,480', '파일 접근', 255, 370)
d.arrow('598,231 598,480', '파일 접근', 655, 370)
d.arrow('1135,231 1190,231 1190,451 1090,451 1090,480', dashed=True)
d.text(35, 632, '점선: 서비스 통신 / HMS의 필요 시 파일 접근. 실선: SeaTunnel·lab의 파일 접근.', 'sub')
d.save('04-deployment.svg')

d = Diagram('05  ·  쓰기: 파일 완성 → 테이블 등록 → 커밋', 'SeaTunnel LocalFile sink와 PyIceberg add_files()를 나눈 첫 학습 경로', 510)
d.box(35, 125, 330, '① SeaTunnel', ['원본 DB 읽기', 'Parquet 파일 완성'])
d.box(435, 125, 330, '② PyIceberg', ['HMS에서 테이블 로드', '완성된 파일을 add_files'], 'orange')
d.box(835, 125, 330, '③ 새 메타데이터', ['새 파일 목록 / 스냅샷', 'metadata JSON 작성'], 'green')
d.arrow('365,178 435,178'); d.arrow('765,178 835,178')
d.box(835, 325, 330, '④ HMS 카탈로그 커밋', ['현재 메타데이터 위치 변경', '충돌 시 검증 / 재시도·실패'], 'purple')
d.box(35, 325, 730, '⑤ 새 reader가 새 스냅샷을 읽음', ['디스크에 파일만 생겼을 때는 테이블 결과가 바뀌지 않는다.', '커밋에 성공해야 테이블의 새 상태로 공개된다.'], 'blue')
d.arrow('1000,231 1000,325'); d.arrow('835,378 765,378')
d.save('05-write.svg')

d = Diagram('06  ·  읽기: 실제 파일을 여는 주체가 다르다', '공통: HMS는 테이블 위치를 알려준다. 데이터 행이 HMS를 통과할 필요는 없다.', 645)
d.text(35, 120, 'A  ·  PyIceberg가 읽고 DuckDB에 결과 전달', 'node')
d.box(35, 145, 250, 'HMS', ['테이블 위치 응답'], 'purple', 88)
d.box(365, 145, 400, 'PyIceberg + Arrow', ['메타데이터·Parquet 읽기', '필터 / 컬럼 선택 후 메모리 결과'], 'orange')
d.box(845, 145, 320, 'DuckDB', ['Arrow 결과로 SQL 실행', '집계 / 조인'])
d.arrow('285,190 365,190'); d.arrow('765,190 845,190', 'Arrow', 805, 176)
d.box(365, 295, 400, '공유 파일 저장소 /lake', ['Iceberg metadata + Parquet'], 'green', 88)
d.arrow('565,295 565,251')
d.text(35, 436, 'B  ·  PyIceberg는 위치만 찾고 DuckDB가 직접 읽음', 'node')
d.box(35, 460, 250, 'HMS', ['현재 metadata 위치'], 'purple', 88)
d.box(345, 460, 310, 'PyIceberg', ['metadata_location 전달'], 'orange', 88)
d.box(715, 460, 450, 'DuckDB + iceberg 확장', ['iceberg_scan(정확한 metadata 경로)', '공유 저장소의 메타데이터·Parquet 읽기'], 'blue')
d.arrow('285,504 345,504'); d.arrow('655,504 715,504')
d.arrow('765,340 940,340 940,460', '공유 파일 읽기', 1040, 396)
d.text(35, 611, 'A는 메모리 결과를 조회 · B는 지정한 테이블 버전을 직접 조회 · 둘 다 새 상태 확인 시 재로드 필요', 'sub')
d.save('06-read.svg')

d = Diagram('07  ·  커밋이 바꾸는 것은 “현재 상태”', 'append 예시 · 스냅샷은 데이터 전체를 복제한 백업이 아니라 파일 집합을 가리키는 상태다.', 520)
d.box(35, 130, 330, '커밋 전', ['카탈로그 → S1의 metadata', 'reader 결과 = a.parquet'], 'purple')
d.box(435, 130, 330, 'writer 준비 중', ['b.parquet + 새 metadata', '아직 새 상태로 공개되지 않음'], 'orange')
d.box(835, 130, 330, '커밋 후', ['카탈로그 → S2의 metadata', '새 reader 결과 = a + b'], 'purple')
d.arrow('365,183 435,183'); d.arrow('765,183 835,183')
d.box(35, 330, 530, 'S1 · 이전 상태', ['a.parquet', '보존된 스냅샷으로 과거 조회 가능'], 'green')
d.box(635, 330, 530, 'S2 · 새 상태', ['a.parquet + b.parquet', 'a는 공유한다. 모든 데이터를 복사하지 않는다.'], 'green')
d.arrow('200,236 200,330'); d.arrow('1000,236 1000,330')
d.text(35, 482, '스냅샷을 만료하고 관련 파일을 삭제하면 그 시점의 과거 조회는 더 이상 보장되지 않는다.', 'sub')
d.save('07-snapshot.svg')

d = Diagram('08  ·  OpenMetadata는 사람이 이해하는 계층', 'HMS는 실행을 위한 카탈로그이고, OpenMetadata는 검색·설명·소유자·계보를 위한 서비스다.', 500)
d.box(35, 130, 340, '사람 / 데이터 사용자', ['어떤 테이블인가?', '누가 관리하고 어디서 왔나?'])
d.box(465, 130, 700, 'OpenMetadata', ['메타데이터 수집 → 검색 / 설명 / 계보', '커넥터 설정과 수집 작업이 별도로 필요'], 'orange')
d.arrow('375,183 465,183')
d.box(35, 325, 340, 'writer / reader', ['테이블 로드와 커밋', '파일 읽기·쓰기'])
d.box(465, 325, 310, 'Hive Metastore', ['현재 테이블 위치', '커밋 상태 관리'], 'purple')
d.box(855, 325, 310, '파일 저장소', ['metadata / manifest', 'Parquet 데이터'], 'green')
d.arrow('375,378 465,378', dashed=True)
d.arrow('205,431 205,463 1010,463 1010,431')
d.arrow('620,325 620,236', '별도 수집 구성', 730, 285, True)
d.save('08-openmetadata.svg')


def inline(s):
    s = html.escape(s)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', s)
    return s


def render_md(text):
    out, para, table, code = [], [], [], None
    def flush():
        if para:
            out.append('<p>' + inline(' '.join(para)) + '</p>'); para.clear()
        if table:
            rows = [[c.strip() for c in row.strip('|').split('|')] for row in table]
            out.append('<div class="table-wrap"><table><thead><tr>' + ''.join('<th>'+inline(c)+'</th>' for c in rows[0]) + '</tr></thead><tbody>')
            for row in rows[2:]:
                out.append('<tr>'+''.join('<td>'+inline(c)+'</td>' for c in row)+'</tr>')
            out.append('</tbody></table></div>'); table.clear()
    for line in text.splitlines():
        if line.startswith('```'):
            if code is None:
                flush(); code = []
            else:
                out.append('<pre><code>'+html.escape('\n'.join(code))+'</code></pre>'); code = None
            continue
        if code is not None:
            code.append(line); continue
        if not line.strip(): flush(); continue
        if line.startswith('|'): table.append(line); continue
        flush_needed = line.startswith(('#', '>', '![')) or re.match(r'^\d+\. ', line)
        if flush_needed: flush()
        if line.startswith('#'):
            hashes, title = line.split(' ', 1)
            out.append(f'<h{len(hashes)}>{inline(title)}</h{len(hashes)}>')
        elif line.startswith('>'):
            if line[1:].strip(): out.append('<aside>'+inline(line[1:].strip())+'</aside>')
        elif line.startswith('!['):
            m = re.fullmatch(r'!\[([^]]+)\]\(([^)]+)\)', line)
            svg = (ROOT / m[2]).read_text()
            out.append('<figure>'+svg+'<figcaption>'+html.escape(m[1])+'</figcaption></figure>')
        elif re.match(r'^\d+\. ', line):
            out.append('<p class="step">'+inline(line)+'</p>')
        else: para.append(line)
    flush()
    assert code is None
    return '\n'.join(out)


body = render_md((ROOT / 'local-lakehouse-visual-guide.md').read_text())
page = '''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>그림으로 이해하는 로컬 레이크하우스</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f3f6fa;color:#23354a;font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;line-height:1.8}main{max-width:1280px;margin:auto;background:white;padding:48px 40px 90px}h1{font-size:38px;line-height:1.3;letter-spacing:-1px}h2{font-size:28px;margin-top:64px;padding-top:22px;border-top:2px solid #dce5ef;line-height:1.45}h3{font-size:22px;margin-top:36px}p{font-size:17px;margin:18px 0}a{color:#205fab;text-underline-offset:3px}aside{color:#53677b;padding:6px 16px;border-left:4px solid #8aa9d1;background:#f5f8fc}figure{margin:28px 0;padding:8px;border:1px solid #dce5ef;border-radius:16px;overflow:auto}figure svg{display:block;width:100%;min-width:760px;height:auto}figcaption{color:#596b7d;font-size:14px;padding:8px 16px}pre{background:#17283d;color:#e2edf9;border-radius:10px;padding:22px;overflow:auto;line-height:1.6;font-size:14px}code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}p code,td code{font-size:.88em;background:#eef3f9;padding:2px 4px;border-radius:4px}table{border-collapse:collapse;width:100%;font-size:15px;min-width:700px}th,td{text-align:left;vertical-align:top;border-bottom:1px solid #dce5ef;padding:12px 14px}th{background:#edf3fb}.table-wrap{overflow:auto;margin:24px 0}.step{padding-left:16px;border-left:3px solid #c4d8f2}strong{color:#173f6a}@media(max-width:700px){main{padding:24px 18px}h1{font-size:29px}h2{font-size:24px}p{font-size:16px}}@media print{body{background:white}main{padding:0;max-width:none}figure{break-inside:avoid}figure svg{min-width:0}h2,h3{break-after:avoid}pre{white-space:pre-wrap}table{min-width:0;font-size:11px}a{color:inherit}}
</style></head><body><main>'''+body+'</main></body></html>\n'
(ROOT / 'local-lakehouse-visual-guide.html').write_text(page)
print(f'Built {len(list(ASSETS.glob("*.svg")))} SVG diagrams and offline HTML guide.')
