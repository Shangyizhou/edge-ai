# Stable experiment catalog with external runtime bindings

实验原始证据继续保留在既有 experiments 路径，新增 catalog 按数据、训练、模型制品、评测登记稳定身份与来源引用。MLflow 与报告使用这些记录，MLflow Run/Model ID 和 Registry 序号只存仓库外绑定表；目录和项目身份不依赖某个数据库。选择增量索引迁移而不搬动历史文件，代价是短期保留旧导入缓存和迁移适配器，收益是冻结证据、旧链接和校验哈希不被重写。阶段报告源集中到 reports，生成物可重建；公开发布仍独立审核。

现有 datasets 版本清单继续作为数据库存入口，实验catalog只保留内容身份与运行关联，不建立第二份样本存储。私有catalog及数据库绑定不随公开代码提交；本地路径可以通过环境变量配置。公开版本摘要可引用固定HF提交，不携带原始样本或本机访问路径。现有逐文件SHA256发布白名单保持不变。
