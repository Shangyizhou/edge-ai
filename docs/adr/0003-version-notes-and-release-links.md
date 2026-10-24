# Version notes and release links share stable project identities

固定交付记录通过release_id关联catalog制品、来源训练、数据与评测，并分别记录选用、验证、部署状态。人工结论保存在短Markdown笔记，模型卡由这些笔记与catalog事实生成，MLflow/HF/GitHub引用同一来源；HTML仅为可选导出。选择不把所有实验说明合并进一个可变“最终报告”，以保留历史失败、版本取舍与可追溯性；旧HTML保留为证据，新阶段不再另行手写重复数字。远端版本发布独立于本地选择，未上传的Q4不能借用adapter地址冒充可下载制品。
