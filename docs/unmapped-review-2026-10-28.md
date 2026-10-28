# 未映射日志复核（2026-10-28）

## 真实样本结果

对日志合集中的有效 Oberon 样本及已有导入日志去重后，共 15 份、58,580 个事件进行复核。当前未映射事件为 0，未识别的非标准日志块为 0；本轮新规则在这些现场样本中尚无命中，因此不声称恢复了新的现场记录。

Titan 日志与损坏文件按既定规则拒绝分析；合成验证文件不计入现场样本统计。

## 对照当前 OberonV2 源码补齐的内容

| 输出类型 | 原处理 | 新处理 | 售后价值 |
| --- | --- | --- | --- |
| custom module version query attempt | I 级未映射、默认隐藏 | 普通可见的模块查询事件 | 保留版本查询序号，不把重试次数直接当故障 |
| custom module version | I 级未映射、默认隐藏 | 重点模块版本事件 | 核对模块能力与软件搭配；不当作 Oberon 启动/软件版本 |
| robot is not teaching state and manual close mask | I 级未映射、默认隐藏 | 重点遮罩操作事件 | 还原操作状态，不单凭此认定机器人已停止或已重连 |
| prepar step ..., send robot cmd: ... | I 级未映射、默认隐藏 | 重点设备准备上下文 | 保留步骤和原始参数；不虚构注册/标定结果或修正源码的格式化参数 |
| teach module reported that teach mode is closed; teach stop command sent | 通用 W 警告 | 设备异常：示教意外关闭触发停止保护 | 区分保护原因与动作结果 |
| teach module connection lost; teach stop command sent | 通用 W 警告 | 设备异常：模块断连触发停止保护 | 连接故障与停止请求关联，但不当作运动完成 |
| custom module teach mode is open after heartbeat recovery; sending close command | 通用 W 警告 | 设备异常：恢复后示教开启触发关闭保护 | 发现恢复阶段的状态异常，不断定关闭成功 |
| femurmarker2ndi NDIDATA | 原始位姿未映射 | 明确归为原始 NDI 位姿噪声 | 与髋骨位姿一致；采集操作另记录，W/E/C 仍默认可见 |

以上均在 `docs/oberon-log-spec.md` 中注明源码来源，并通过合成消息验证。未修改 Oberon 或其日志输出。

## 源码核对范围

- 检查实际 `g_sysLogger` 输出，排除注释；直接字符串输出及已知股骨/髋骨 marker 变体共 165 项均能命中规则。
- 另外检查了 `FITKukaCmd` 条件分支的两条保护警告、动态配准矩阵输出，以及崩溃堆栈的现有处理。
- `qDebug`/stdout 中的连接恢复、监听失败等语句没有擅自写成已存在的运行日志规则。
- 静态核对不是运行覆盖；外部库生成的新日志或未来版本仍可能出现未映射项。

## 验证

- 标准库单元及 HTTP 集成测试共 68 项通过；JavaScript 语法与 Git 空白检查通过。
- 新增覆盖模块版本与软件会话隔离、三类保护警告、设备准备上下文不当作完成证据、遮罩操作不当作停止反馈、股骨 NDI 位姿及警告等级、规则热更新。
- 未知 I 级事件仍保留“未映射”身份，可用“显示全部”和全文搜索查看；未知 W 默认可见。没有添加包揽任意文本的规则来人为清零计数。
- 已有样本的异常计数与时间轴索引保持一致；本轮新增源码规则不改变这些样本的分析结果。
