#!/usr/bin/env python3
"""Run an explicit task adapter under a frozen plan and preserve its raw result."""
import argparse,hashlib,json,os,signal,subprocess,time
from pathlib import Path
from workflow_review import review,table,paragraph

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def execute(path,output):
    path=Path(path).resolve();d=json.loads(path.read_text());output=Path(output).resolve()
    if d.get('schema')!='edge-ai-experiment/request-v1':raise ValueError('unsupported experiment schema')
    planpath=(path.parent/Path(d['plan_ref'])).resolve();plan=json.loads(planpath.read_text())
    if plan.get('status')!='frozen':raise ValueError('evaluation plan not frozen')
    suitepath=Path(plan['suite_ref'])
    if sha(suitepath)!=plan['suite_sha256']:raise ValueError('suite changed after freeze')
    adapterpath=(path.parent/Path(d['adapter_request'])).resolve();adapter=json.loads(adapterpath.read_text())
    if 'suite_ref' in adapter and sha(adapter['suite_ref'])!=plan['suite_sha256']:raise ValueError('adapter suite differs from frozen plan')
    if plan['profile']=='native-tool-persona-v1' and 'suite_ref' not in adapter:raise ValueError('native adapter must bind the frozen suite')
    if plan['profile']=='asr-transcription-v1' and adapter.get('suite_sha256')!=plan['suite_sha256']:raise ValueError('ASR adapter must bind frozen sample identity')
    argv=d['adapter_argv']
    if not isinstance(argv,list) or not argv or any(not isinstance(a,str) or not a for a in argv):raise ValueError('explicit argv required')
    timeout=plan['budget']['total_seconds']
    if type(timeout) not in (int,float) or not 0<timeout<=3600:raise ValueError('bounded total timeout required')
    output.mkdir(parents=True,exist_ok=False)
    (output/'request.json').write_bytes(path.read_bytes());(output/'plan.json').write_bytes(planpath.read_bytes());(output/'adapter-request.json').write_bytes(adapterpath.read_bytes())
    command=argv+[str(adapterpath),str(output/'raw')];started=time.monotonic();error=None
    with (output/'stdout.log').open('w') as stdout,(output/'stderr.log').open('w') as stderr:
        try:
            process=subprocess.Popen(command,cwd=d.get('cwd'),stdout=stdout,stderr=stderr,start_new_session=True)
        except OSError as exc:
            process=None;code=None;error='adapter launch failed: '+str(exc)
        if process is not None:
            try:code=process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
                code=process.returncode;error='stage timeout; owned process group terminated'
    rawpath=output/'raw/results.json';raw={}
    if rawpath.exists():
        try:raw=json.loads(rawpath.read_text())
        except (ValueError,OSError) as exc:error='invalid adapter result: '+str(exc)
    elif not error:error='adapter produced no result; inspect retained stderr'
    result={'schema':'edge-ai-experiment/result-v1','run_id':d['run_id'],'profile':plan['profile'],'purpose':plan['purpose'],'status':'failed','command':command,'exit_code':code,'wall_seconds':time.monotonic()-started,'plan_sha256':sha(planpath),'adapter_request_sha256':sha(adapterpath),'source':raw.get('source',{}),'measurement':raw.get('measurement',{}),'summary':raw.get('summary',{}),'raw_result':{'path':str(rawpath),'sha256':sha(rawpath)} if rawpath.exists() else None,'error':error}
    if result['error']:pass
    elif raw.get('run_id')!=adapter.get('run_id'):result['error']='adapter result run identity mismatch'
    elif raw.get('source',{}).get('kind')!='device_measurement':result['error']='real model evidence missing'
    elif raw.get('summary',{}).get('samples')!=plan['samples']:result['error']='case denominator differs from frozen plan'
    elif code==0 and not error:result['status']='completed'
    if code!=0 and not result['error']:result['error']='adapter failed; inspect retained raw evidence'
    (output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    review(output,'本轮测评结果',[( '目的与条件',paragraph(d.get('question',''))+table([('任务',plan['profile']),('用途',plan['purpose']),('执行状态',result['status'])])),('质量结果',table(result['summary'].items())+paragraph('执行完成不等于任务通过；完整逐例失败保存在原始结果。')),('时间与资源',paragraph(result['measurement'])+table([('适配器全阶段墙钟秒',round(result['wall_seconds'],3))])+paragraph('该墙钟包括启动等开销，不能当成逐请求等待。实际推理资源保留在原始结果。')),('证据与下一步',paragraph(result['error'] or '按已有门槛和失败决定下一步，不自动训练或量化。')+'<p><a href="raw/report.html">逐例原始报告（如适配器提供）</a></p>')])
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('request',type=Path);p.add_argument('output',type=Path);p.add_argument('--dry-run',action='store_true');a=p.parse_args()
    if a.dry_run:
        d=json.loads(a.request.read_text());print(json.dumps(d['adapter_argv']+[str(Path(d['adapter_request']).resolve()),str(a.output.resolve()/'raw')],ensure_ascii=False));return
    r=execute(a.request,a.output);print(a.output/'report.html')
    if r['status']!='completed':raise SystemExit(2)
if __name__=='__main__':main()
