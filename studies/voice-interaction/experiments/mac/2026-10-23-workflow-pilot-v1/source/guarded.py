"""Bound one owned model command; preserve timeout/resource-stop evidence."""
import argparse,json,os,signal,subprocess,time
from pathlib import Path

def main():
    import psutil
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=float,required=True);p.add_argument('--record',type=Path,required=True);p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args()
    cmd=a.command[1:] if a.command and a.command[0]=='--' else a.command
    started=time.monotonic();stop=None;samples=[]
    child=subprocess.Popen(cmd,start_new_session=True)
    while child.poll() is None:
        try:
            proc=psutil.Process(child.pid);rss=sum(x.memory_info().rss for x in [proc]+proc.children(recursive=True) if x.is_running());available=psutil.virtual_memory().available
        except psutil.Error:rss=0;available=psutil.virtual_memory().available
        samples.append({'seconds':time.monotonic()-started,'rss_bytes':rss,'host_available_bytes':available})
        if time.monotonic()-started>a.seconds:stop='wall budget exceeded'
        if rss>8*2**30:stop='process tree RSS exceeds 8GiB'
        if available<512*2**20:stop='host available below 512MiB'
        if stop:
            os.killpg(child.pid,signal.SIGTERM)
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
            break
        time.sleep(.5)
    a.record.write_text(json.dumps({'command':cmd,'exit_code':child.wait(),'wall_seconds':time.monotonic()-started,'stop_reason':stop,'samples':samples},indent=2))
    if child.returncode or stop:raise SystemExit(2)
if __name__=='__main__':main()
