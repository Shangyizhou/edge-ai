"""Validate Qwen business outputs without invoking any robot function."""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

EXP = Path(__file__).resolve().parents[1]
ROOT = Path('/home/orangepi/code/ros-robot')
sys.path.insert(0, str(EXP / 'project-source/ros2_ws/src/robot_agent'))
sys.path.insert(0, str(EXP / 'measurement-source'))
# Non-copied package modules are imported read-only from the pinned clean checkout.
sys.path.append(str(ROOT / 'ros2_ws/src/robot_agent'))
from robot_agent.actions.capabilities import create_default_actions
from robot_agent.actions.perception import PerceptionActions
from robot_agent.conversation.local_model import _parse_legacy_reply
from robot_agent.results import _json_value
import benchmark
from evaluation_metrics import resource_window

BINARY = '/home/orangepi/.cache/edge-voice-v2/llama-b6500/bin/llama-server'
MODEL = '/home/orangepi/models/edge-voice-v2/qwen2.5-0.5b-instruct-q4_k_m.gguf'

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def request(origin, path, payload=None, timeout=30):
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    with urlopen(Request(origin + path, data=data, headers={'Content-Type':'application/json'}), timeout=timeout) as r:
        return json.load(r)

def alarm_handler(signum, frame):
    raise TimeoutError('Total diagnostic budget exceeded')

def main():
    assert not (EXP / 'results.json').exists(), 'Never overwrite a previous run'
    cases = json.loads((EXP / 'cases.json').read_text())
    tools = json.loads((EXP / 'tools-subset.json').read_text())
    registry = create_default_actions().registry
    registry.register_perception(PerceptionActions(None))
    grammar_file = EXP / 'project-source/ros2_ws/src/robot_inference/include/robot_inference/reply_grammar.hpp'
    grammar = re.search(r'R"GBNF\((.*?)\)GBNF"', grammar_file.read_text(), re.S).group(1)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    command = [BINARY,'-m',MODEL,'--host','127.0.0.1','--port',str(port),'-t','2','-tb','2','-c','2048','-b','128','-ub','64','-ctk','f16','-ctv','f16','-fa','off','-ngl','0','--no-warmup']
    save(EXP / 'execution-plan.json', dict(model=MODEL,model_sha256=hashlib.sha256(Path(MODEL).read_bytes()).hexdigest(),binary=BINARY,binary_sha256=hashlib.sha256(Path(BINARY).read_bytes()).hexdigest(),command=command,catalog='6 of 60 original project tool declarations; diagnostic subset only',template='Official Qwen2.5 ChatML; project local system content preserved, original trained-model text envelope replaced explicitly',grammar='Exact project fc-first-v1; JSON syntax does not enforce business correctness',generation=dict(n_predict=128,temperature=0,seed=42,cache_prompt=False),budgets=dict(per_request_s=210,total_s=750),scope='No ROS, no registry.invoke, no executor, no hardware or simulation action dispatch'))
    signal.signal(signal.SIGALRM, alarm_handler); signal.alarm(750)
    origin = 'http://127.0.0.1:' + str(port)
    stop = threading.Event(); resource_errors=[]; guard=[]
    output=[]; token_counts=[]
    log = (EXP / 'native.log').open('w')
    server = subprocess.Popen(command,stdout=log,stderr=log,start_new_session=True)
    def sample():
        with (EXP / 'resources.jsonl').open('w') as stream:
            while not stop.is_set():
                try:
                    row = benchmark.observe(server.pid)
                    stream.write(json.dumps(row)+'\n');stream.flush()
                    if row['host']['MemAvailable'] < 600*1024:
                        guard.append('host MemAvailable below 600MiB')
                        benchmark.stop_group(server)
                        return
                except Exception as error:
                    resource_errors.append(repr(error));return
                stop.wait(.2)
    thread = threading.Thread(target=sample); thread.start()
    try:
        started=time.monotonic()
        while True:
            if server.poll() is not None:raise RuntimeError('server exited before ready')
            try:
                if request(origin,'/health',timeout=2).get('status')=='ok':break
            except (HTTPError,URLError,TimeoutError):pass
            if time.monotonic()-started>60:raise TimeoutError('load timeout')
            time.sleep(.1)
        for scope in ['full','subset']:
            for c in cases:
                raw=(EXP/(scope+'-'+c['id']+'.txt')).read_text()
                # Tokenize both actual project envelope and explicit official-template adaptation.
                split=raw.index('<|im_end|>')
                system=raw[len('System: '):split]
                chatml='<|im_start|>system\n'+system+'<|im_end|>\n<|im_start|>user\n'+c['text']+'<|im_end|>\n<|im_start|>assistant\n'
                (EXP/(scope+'-'+c['id']+'-chatml.txt')).write_text(chatml)
                for name,prompt in [('project-envelope',raw),('official-chatml',chatml)]:
                    tokens=request(origin,'/tokenize',dict(content=prompt,add_special=True,parse_special=True))['tokens']
                    token_counts.append(dict(scope=scope,case=c['id'],template=name,prompt_tokens=len(tokens),output_reserve=128,fits_selected_2048=len(tokens)+128<=2048,fits_project_example_4096=len(tokens)+512<=4096))
        save(EXP/'token-counts.json',token_counts)
        print('Token counts:',token_counts,flush=True)
        request(origin,'/completion',dict(prompt='<|im_start|>user\n你好<|im_end|>\n<|im_start|>assistant\n',n_predict=8,temperature=0,cache_prompt=False),timeout=60)
        time.sleep(3)
        for c in cases:
            prompt=(EXP/('subset-'+c['id']+'-chatml.txt')).read_text()
            payload=dict(prompt=prompt,n_predict=128,temperature=0,seed=42,cache_prompt=False,stream=True,grammar=grammar)
            folder=EXP/c['id'];folder.mkdir()
            save(folder/'request.json',payload)
            row=dict(id=c['id'],input=c['text'],expected=c['expected'],catalog_count=6,scope='diagnostic subset, not full project acceptance')
            chunks=[];reply='';first=None;final=None
            start=time.monotonic();before=benchmark.observe(server.pid)
            print('Starting business case',c['id'],flush=True)
            try:
                with urlopen(Request(origin+'/completion',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'}),timeout=210) as response:
                    for line in response:
                        if not line.startswith(b'data: '):continue
                        raw=line[6:].strip()
                        if raw==b'[DONE]':break
                        event=json.loads(raw);elapsed=time.monotonic()-start
                        chunks.append(dict(elapsed_s=elapsed,event=event))
                        content=event.get('content','')
                        if content and first is None:first=elapsed
                        reply+=content
                        if event.get('stop'):final=event
                row.update(status='complete' if final and final.get('stopped_eos') else 'output_limit_or_missing_stop',raw=reply,ttft_s=first,total_s=time.monotonic()-start,native_final=final)
                parsed=_parse_legacy_reply(reply,c['id'],tools)
                calls=[dict(name=x.name,arguments=_json_value(x.arguments)) for x in parsed.tool_calls]
                if parsed.tool_calls:registry.validate_calls(parsed.tool_calls)
                row.update(protocol_valid=True,registry_valid=True,calls=calls,response=parsed.response,intent_pass=calls==c['expected'])
            except Exception as error:
                row.update(status='error',error=repr(error),raw=reply,ttft_s=first,total_s=time.monotonic()-start,protocol_valid=False,intent_pass=False)
            end=time.monotonic();after=benchmark.observe(server.pid)
            save(folder/'stream.json',chunks)
            save(folder/'result.json',row)
            row.update(start_monotonic=start,end_monotonic=end)
            save(folder/'boundary-resources.json',dict(before=before,after=after))
            output.append(row);save(EXP/'progress.json',output)
            print('Completed',c['id'],row['status'],'intent:',row['intent_pass'],'raw:',reply,flush=True)
            if guard or server.poll() is not None:break
    finally:
        signal.alarm(0);stop.set();thread.join();benchmark.stop_group(server);log.close()
        resources=[json.loads(l) for l in (EXP/'resources.jsonl').read_text().splitlines()]
        for row in output:
            row['resources']=resource_window(resources,row['start_monotonic'],row['end_monotonic'],os.cpu_count(),benchmark.memory_info()['MemTotal'])
        save(EXP/'results.json',dict(source_kind='device_measurement',source_model='official Qwen2.5-0.5B-Instruct Q4_K_M; not the project trained qwen3-robot',cases=output,token_counts=token_counts,guard=guard,resource_errors=resource_errors,product_fit='NOT_ACCEPTED_FULL_PROJECT',execution_scope='No function was invoked; validation only'))

if __name__=='__main__':main()
