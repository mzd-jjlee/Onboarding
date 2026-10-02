"""Continue the 2026-09-15 isolated Local heap experiment; retain containers/logs."""
from pathlib import Path
import json
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
STUDY = ROOT / 'output/oom-study/20260915'

def docker(*args, check=True):
    return subprocess.run(['docker', *args], text=True, capture_output=True, check=check).stdout

def observe(label, name):
    dest = STUDY / label
    started = time.monotonic()
    oom_at = None
    sampled = False
    while True:
        state = json.loads(docker('inspect', name))[0]['State']
        (dest / 'container-state.json').write_text(json.dumps(state, indent=2))
        log = (dest / 'console.log').read_text(errors='replace') if (dest / 'console.log').exists() else ''
        if not state['Running']:
            print(f'{label}: stopped; exit={state["ExitCode"]}; OOMKilled={state["OOMKilled"]}', flush=True)
            break
        if not sampled:
            info = docker('exec', name, 'sh', '-c', 'jcmd -l; jcmd $(pgrep -f "^java " | head -1) VM.flags', check=False)
            (dest / 'jvm-monitor.txt').write_text(info)
            sampled = True
        if 'java.lang.OutOfMemoryError' in log and oom_at is None:
            oom_at = time.monotonic()
            print(f'{label}: Java OOM observed', flush=True)
        if (oom_at and time.monotonic() - oom_at > 90) or time.monotonic() - started > 1200:
            reason = 'JVM remained running for 90 seconds after OOM' if oom_at else '20-minute observation limit'
            (dest / 'manual-stop-reason.txt').write_text(reason)
            docker('exec', name, 'sh', '-c', f'cp -R /opt/seatunnel/logs /study/{label}/engine-logs', check=False)
            docker('stop', '-t', '15', name)
            print(f'{label}: stopped by experiment runner: {reason}', flush=True)
            continue
        progress = [s.strip() for s in log.splitlines() if 'Read Count So Far' in s or 'Write Attempt Count So Far' in s]
        print(f'{label}: running; ' + '; '.join(progress[-2:]), flush=True)
        time.sleep(30)
    docker('cp', f'{name}:/opt/seatunnel/logs', str(dest / 'preserved-engine-logs'), check=False)

observe('local-512m', 'st-oom-local-512m-20260915')
label = 'local-3g'
name = 'st-oom-local-3g-20260915'
shell = ('mv /opt/seatunnel/lib/opengauss-jdbc-5.1.0.jar /opt/seatunnel/lib/opengauss-jdbc-5.1.0.jar.bak; '
         './bin/seatunnel.sh --config /study/local-3g/job.conf -m local > /study/local-3g/console.log 2>&1; '
         'result=$?; cp -R /opt/seatunnel/logs /study/local-3g/engine-logs; '
         'echo "$result" > /study/local-3g/exit-code; exit "$result"')
print(docker('run', '-d', '--name', name, '--network', 'seatunnel_default',
             '-v', f'{STUDY}:/study',
             '-v', f'{STUDY / label / "jvm_client_options"}:/opt/seatunnel/config/jvm_client_options:ro',
             '--entrypoint', 'sh', 'apache/seatunnel:2.3.13', '-c', shell), flush=True)
observe(label, name)
