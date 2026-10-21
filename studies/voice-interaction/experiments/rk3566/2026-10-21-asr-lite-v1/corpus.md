# ASR v1 固定小输入集

实际清单和文件hash见[fixtures.json](fixtures.json)。共6条、原始总长37.769125秒；每条追加3.2秒零输入不计入原始时长。初筛固定3条：command、fleurs-1805-1、silence1；复测使用全部6条。CPU/NPU及两场景使用同一文件，三轮不增加独立语料数量。

| 用例 | 原始时长 | 来源及用途 | 质量证据 |
| --- | --- | --- | --- |
| official0 | 10.053125s | 现有模型官方测试文件 | 无独立转写，功能/性能回归 |
| command | 5.888s | 现有机器人指令录音的既有16kHz派生文件；只识别，不执行动作 | 旧模型一致输出仅作参考，不计CER |
| command-pause080 | 6.368s | 同一command插入停顿的既有派生文件 | 同一原语料，不当新增独立质量样本 |
| fleurs-1805-1 | 7.62s | FLEURS普通话测试集，Scotturb 403 / 辛特拉句 | 数据集既有转写 |
| fleurs-1965-2 | 6.84s | FLEURS普通话测试集，沙滩 / 新西兰圣诞树句 | 数据集既有转写 |
| silence1 | 1s | 新生成的全零PCM，验证空输出行为 | expected_behavior=silence；不参加CER |

FLEURS来自Google发布的[FLEURS: Few-shot Learning Evaluation of Universal Representations of Speech](https://huggingface.co/datasets/google/fleurs)（Conneau等，2022），数据许可CC-BY-4.0。仅流式读取中文test归档中最先遇到的两条3–8秒文件，然后停止下载，没有读取模型输出后挑选。转写来自对应test.tsv，版本固定为该文件SHA-256；原始音频成员名、原文件hash、派生文件hash及标签来源都记录在清单中。它们是公开朗读小子集，不能代表机器人远场或全部普通话准确率。

原始FLEURS WAV为float32，统一用ffmpeg转换为单声道16kHz PCM16；没有改写转写。变换命令为`ffmpeg -i SOURCE -ac 1 -ar 16000 -c:a pcm_s16le TARGET`。原始和派生音频都留在Git外部缓存，仓库只保存来源、元数据和测量输出。原测试集转写中的专名、英文、数字保留，CER规则不将“403”强行等价于中文数字。

所有非静音条目的能量末端使用最后一个20ms RMS>-35dBFS窗口末端；静音记-1（无锚点）。这不是人工末音标注。重复轮次及派生停顿用例的相关性明确保留，不按独立说话人统计。
