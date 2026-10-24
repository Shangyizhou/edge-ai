# 小沫 Qwen3-0.6B · 首个固定交付记录

<!-- Generated from release.json, catalog and decision Markdown; edit those sources. -->

固定版本：`xiaomo-qwen3-0.6b-r1` · 记录日期：2026-10-24

## 采用状态

- **selection_status**：`user_selected_with_limits`。用户明确选择Q4，并接受已知语义质量损失。
- **validation_status**：`development_gates_not_passed`。开发集多次参与选配；未通过原门槛，未作本版独立泛化验收。
- **deployment_status**：`historical_model_api_deployed`。记录2026-10-24既有三条模型API与Registry校验；不是本次实时探测或完整ROS验收。

## 来源与训练

- 基座：Qwen/Qwen3-0.6B，revision `c1899de289a04d12100db370d81485cdf75e47ca`。
- 数据：235条训练 / 50条已观察开发；数据版本见下方HF固定引用。
- 方法：LoRA，rank 8，MLX直接scale 16.0，学习率 5e-05。
- 模块：`self_attn.q_proj, self_attn.v_proj, mlp.gate_proj, mlp.up_proj, mlp.down_proj`；监督目标：continuation8。
- 实际训练：1408微步 / 176更新，选定1408微步检查点。
- 项目训练ID：`training-f60b3aa7f905765a493f16bc`；所选制品ID：`model-75ebc7a6aaa0180750a9cafe`。
- 执行代码：依据catalog中的冻结执行记录及measurement_sources，当前工作区HEAD不冒充训练版本。

## 同源量化对照

同一检查点、同50条已观察开发题、Mac llama.cpp；RSS为请求窗口采样。

| 候选 | 工具正确 | 不调用误触发 | 文件MB | Mac峰RSS MiB |
|---|---:|---:|---:|---:|
| F16 | 24/27 | 4/23 | 1198.2 | 1525.4 |
| Q8 | 24/27 | 5/23 | 639.4 | 990.5 |
| Q4 | 20/27 | 11/23 | 396.7 | 782.8 |

三者开发集单指令均9/10；这不能覆盖取消、不调用和多动作的退步。原质量门槛未过，开发集多次用于选配。

## 能力与限制

已测试：选定10工具目录下的原生tool_calls；相机采集、雷达融合、Follow启停及状态查询。

- 取消、否定、不调用与工具不可用时仍可能误调用。
- 复杂多动作及解释问答仍有错误。
- Schema/Registry通过不代表业务意图正确。

## 板端历史快照

RK3566既有3条API请求：协议/Registry 3/3，意图 2/3；峰值PSS 563.0 MiB。不是本次实时验收、完整ROS交互或动作执行。

## 固定制品与数据引用

- adapter：[Shangyizhou/xiaomo-qwen3-0.6b](https://huggingface.co/Shangyizhou/xiaomo-qwen3-0.6b/commit/10109cc14697a2dd2968676855350f5dc2ea0862)，路径 `releases/xiaomo235-cont8-e6-v1`，private=true。
- dataset：[Shangyizhou/xiaomo-robotics-data](https://huggingface.co/datasets/Shangyizhou/xiaomo-robotics-data/commit/837cc1c501a3948c8512ff2befa3731a22948ef6)，路径 `releases/xiaomo235-v1`，private=true。
- 所选Q4：SHA256 `e5e283a9285ffb8f3fd2539fec3e4734474c8a5b0ba42ae4a586c1188df325c6`；尚未上传HF，不将adapter链接当作GGUF下载地址。旧根文件不自动成为本版制品。

## 采用依据与实验结论

### 继续边界加权：观察到开发集改善

#### 假设

调用继续边界学习不足可能导致多动作提前结束。

#### 对照与改动

仅中间调用继续边界权重1→8；对齐1408微步检查点。

#### 结论

单种子开发工具与误调用联合改善，但仍未达门槛，纠正类有退步。

#### 下一步

保留结果，完善独立验证；不以此宣称排除过拟合。


结论强度：`observed_development_improvement`。

### Q4：用户接受资源与质量取舍后选用

#### 假设

量化是否能在设备资源约束下保留任务效果。

#### 对照与改动

同一检查点生成F16、Q8_0、Q4_K_M；同Mac运行时和同开发50题比较。

#### 结论

Q4更省资源但语义损失明显；用户明确选用，保留F16/Q8作参照。

#### 下一步

重点防护取消、不调用、缺工具边界；不把选择状态标为质量通过。


结论强度：`user_selected_with_limits`。

## 后续与恢复

保留当前选定Q4；后续优先完善边界数据和验证证据；不自动恢复训练。

部署恢复步骤引用已有板端部署记录；本次不改变服务或回滚指向。
