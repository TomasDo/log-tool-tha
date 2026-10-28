# Oberon 日志噪声复核（2026-10-28）

本轮覆盖日志合集内 14 份去重后的有效 Oberon 日志，以及已导入的 2026-10-27 日志，共 15 份有效日志。OberonV2 源码与原始日志只读。

## 发现与修正

| 之前被折叠的记录 | 售后价值 | 当前显示方式 |
| --- | --- | --- |
| 重力补偿选择、定线/定点、手导、预设位/收纳位移动 | 还原操作顺序和选用的指令参数 | 重点；只标记请求，不断定运动完成 |
| teachStop、specialTeachStop、standby、制动测试 | 排查为何停止、何时发起测试 | 重点；保留原始指令名称；未知控制指令也显示 |
| standbyMarkerOffsetted | 保护待机的请求证据 | 异常提示；不与其他行合并推断故障根因 |
| standbyStepChange 及原因行 | 区分正常切页待机与保护停机 | 普通可见信息，不标成故障 |
| robot no motion joint | 收到 robotStatusStop 后记录停止状态及关节角 | 重点反馈；不等同于急停或异常 |
| pedal-pressed/released UI | 排查界面响应链，尤其旧日志缺少物理脚踏行时 | 重点；明确为界面反馈，与物理信号分开 |
| 标定和髋/股骨配准变换矩阵 | 核对发布、回退后的变换结果 | 重点；不替代 RMSE，不新增“配准完成”判断 |
| 网卡地址、程序运行目录 | 排查设备连接、启动路径或资源目录问题 | 普通可见信息；地址枚举不代表已选中接口 |
| 假体偏移配置读取 | 核对读取值及型号 | 普通可见信息；不推断本次实际采用该型号 |

## 剩余噪声逐类结论

仅保留周期/操作附带的原始力矩、普通关节角快照、原始 hipmarker NDI 位姿及全零 RAS/APP 角度占位。数值仍可通过噪声开关和全文搜索查看；单独数值不自动推断故障或超限。

警告级 W 即使命中转储规则也默认显示为提醒；E/C 始终保留异常。全零快照不参与角度比较，但保留警告/错误本身。

## 样本验证计数

本轮从原噪声中恢复 4,808 条默认可见记录，剩余 44,020 条数值转储/占位记录继续折叠。按日志记录计数，不代表手术、故障或独立操作次数；请求和原因/反馈可能分别记录。

| 恢复的事件ID | 记录数 |
| --- | --- |
| align_direction_request | 60 |
| application_path | 30 |
| brake_current_request | 6 |
| brake_test_request | 15 |
| config_echo | 160 |
| effector_matrix | 20 |
| fix_line_request | 120 |
| fix_point_request | 6 |
| gravity_request | 371 |
| hip_registration_matrix | 40 |
| marker_standby_request | 7 |
| move_patient_request | 34 |
| move_preset_request | 58 |
| move_storage_request | 30 |
| network_address | 190 |
| pedal_ui_pressed | 253 |
| pedal_ui_released | 1099 |
| robot_stopped | 462 |
| special_teach_stop_request | 130 |
| standby_request | 114 |
| step_standby_reason | 680 |
| step_standby_request | 680 |
| teach_stop_request | 35 |
| tool_hand_guiding_request | 208 |

| 剩余噪声规则 | 记录数 |
| --- | --- |
| record torque | 3916 |
| current joint | 2063 |
| ras coordinate realtime anteversion:0 , inclination:0, depth:0 | 430 |
| hipmarker2ndi | 994 |
| current torque | 36617 |

## 验证与边界

- 标准库单元与 HTTP 集成测试共 60 项通过；JavaScript 语法及 Git 空白检查通过。
- 新增覆盖控制请求类型、停止状态反馈、普通切页待机、环境配置、矩阵证据、警告级转储、全零错误行、规则热加载及现有步骤判定不变。
- 15 份日志逐份检查：恢复事件在默认过滤结果中可见；异常计数与时间轴索引一致。
- 基于真实记录及源码输出补规则；未在样本出现的源码分支通过合成日志验证。规则命中不等于现场动作完成。
- 仅修改日志工具，未编译 Oberon，未修改或提交原始日志。
