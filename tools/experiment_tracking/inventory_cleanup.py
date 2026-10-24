"""Describe optional cleanup candidates; never delete files."""
import json
from pathlib import Path
from import_history import ROOT, DEFAULT_HOME
from catalog import CATALOG, REPORTS


def inventory():
    home=DEFAULT_HOME; rows=[]
    def add(path,status,reason,recovery=''):
        p=Path(path)
        if not p.exists():return
        rows.append({'path':str(p),'status':status,'bytes':p.stat().st_size if p.is_file() else None,'reason':reason,'recovery_or_condition':recovery,'deleted':False})
    for name in ['index.html','cases.html','comparison.html','lineage.html']:
        add(home/'view'/name,'REBUILDABLE','派生页面，当前服务使用；不再是权威记录。','保留 catalog、bindings、模板和冻结逐例源后，运行 python3 tools/experiment_tracking/build_dashboard.py 重建；重建前页面暂不可用。')
    for path in sorted(home.glob('*proof.png')):
        add(path,'OPTIONAL_ATTACHMENT','验收截图；应用运行不依赖。','可删除，但旧聊天中的图片链接会失效；若要保留交接证据则保留。')
    for path in sorted(home.glob('*.log')):
        if path.name.startswith('server-'):
            add(path,'KEEP_ACTIVE','当前本机服务日志；运行中进程仍可能写入。','需另做日志轮转，当前不建议删除。')
        else:add(path,'OPTIONAL_DIAGNOSTIC','安装/导入/重复导入过程日志；catalog 与页面运行不读取。','保留故障排查或审核所需日志后可选清理；不包含模型原始训练日志。')
    for name in ['lineage-import.json','import-verification.json','view/data.json']:
        add(home/name,'OPTIONAL_MIGRATION_CACHE','新展示与原生配置已改读 catalog；历史一次性迁移仍读取此文件。','先备份 catalog+bindings，并决定不再直接运行旧迁移命令；删除后旧导入/迁移回退流程需从保留记录恢复。')
    for path in sorted((ROOT/'tools/experiment_tracking/__pycache__').glob('*.pyc')):
        add(path,'REBUILDABLE','Python字节码缓存；对应源代码保留。','Python会重新生成，无需运行训练。')
    for name in ['mlflow.db','bindings/catalog-mlflow.json']:
        add(home/name,'KEEP_ACTIVE','当前MLflow元数据或项目ID到MLflowID的绑定；不可作为临时文件删除。')
    for name in ['catalog.py','build_dashboard.py','dashboard.html','cases.html','lineage.html','view.html','configure_native.py','patch_native_frontend.py','import_history.py']:
        add(ROOT/'tools/experiment_tracking'/name,'KEEP_ACTIVE','当前读模型、页面、配置、恢复或共享常量仍引用；不是可立即删除项。')
    for path in sorted((home/'backups').glob('*')):
        add(path,'KEEP_RECOVERY','历史备份或原生前端回滚资产。','旧备份可作为后续保留策略候选；本次未验证替代备份恢复，暂不标为可直接删。')
    out=REPORTS/'maintenance-2026-10-24';out.mkdir(exist_ok=True)
    (out/'cleanup-inventory.json').write_text(json.dumps({'scope':'explicit MLflow local runtime and tracking files only; no raw experiment scan','no_deletions':True,'entries':rows},ensure_ascii=False,indent=2)+'\n')
    groups={'REBUILDABLE':'可重建（删除会暂时失去页面/缓存）','OPTIONAL_ATTACHMENT':'可选附件','OPTIONAL_DIAGNOSTIC':'可选诊断日志','OPTIONAL_MIGRATION_CACHE':'有条件可选：旧迁移缓存','KEEP_ACTIVE':'仍在使用，保留','KEEP_RECOVERY':'回滚/备份，保留'}
    text='# 重构与可选清理清单\n\n2026-10-24。**本次没有删除文件。** 范围只包括本次跟踪/展示系统，不含权重、音频、数据集、封存题或冻结实验目录。\n\n'
    text+='目录职责已拆分：catalog 为稳定索引，experiments 保留冻结证据，reports 为阶段报告源与维护记录，research 保留分析；MLflow数据库、绑定、生成页面与缓存继续位于Git外。\n\n'
    for status,title in groups.items():
        entries=[r for r in rows if r['status']==status];text+='## '+title+'（'+str(len(entries))+'项）\n\n'
        for r in entries:
            p=r['path'];size=(' · '+str(r['bytes'])+' bytes') if r['bytes'] is not None else ''
            text+='- ['+Path(p).name+']('+p+')'+size+'：'+r['reason']+' '+r['recovery_or_condition']+'\n'
        text+='\n'
    text+='## 不列为清理项\n\n- experiments 下原始JSON、逐例结果、配置、训练日志、源快照、manifest、HTML及其相对资源：仍是冻结证据或历史链接，不能因MLflow已有索引就删除。\n- 已发布的 reports/2026-10-22-voice-screening：现有网站仍引用。\n- research 下旧计划、诊断和导入验收：是历史说明，不因当前入口变化就自动作废。\n- weights、HF版本、数据集与录音：不是本次重构的清理范围。\n- .vscode、app.log及其他已有个人/无关改动：本次不分类、不改动。\n\n[机器可读清单](cleanup-inventory.json)列出完整路径、大小、理由与条件。当前仅标注，没有执行清理或关闭本机服务。\n'
    (out/'README.md').write_text(text)
    print(json.dumps({k:sum(r['status']==k for r in rows) for k in groups}))

if __name__=='__main__':inventory()
