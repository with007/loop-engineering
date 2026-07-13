# Tasks

> 约定: 任务按日期分组，同天内按优先级从上到下排列

## 2026-06-26

- [x] refactor-core-architecture (→ with) [f610728e] — 15:42 IMP1 VFY1 PASS · 16:45 IMP2 VFY1 PASS — 17:38 IMP3 VFY1 PASS
  ## IMP2 反馈
  1. pages.py 重构后缺少模板上下文变量：/control 缺少 status、/settings 缺少 config、/runs 缺少 pass_rate — 对照原 app.py 补齐
  ## IMP1 反馈
  1. routers/pages.py 和 routers/fragments.py 为空壳，路由未迁移。需从 app.py 搬入页面路由和 HTMX 片段路由，app.py 精简到仅实例+注册+start_server
  2. filter_tasks 的 order 和 filter_name 参数为 stub，需补全排序和 agent 名筛选逻辑，消除 4 个路由中的重复实现
  3. 补齐 test_config.py（deep_merge）、test_control.py（状态机）、test_runlog.py（写入/查询/PASS率）
  4. pip install 需先关闭正在运行的 loop.exe 进程（taskkill /F /IM loop.exe），再重试安装

- [x] 现在页面好像会隔几秒重新加载，导致输入被清空 (→ with) [a35f86a5] — 16:15 IMP2 VFY1 PASS · 17:34 IMP3 VFY1 PASS
- [x] improve-claude-git-robustness — 借鉴 claude-controller: env清理/claude路径解析/git fetch重试/离线模式/pytest (→ with) [2a09877f] — 11:02 IMP1 VFY1 PASS
- [x] 现在生成的diff文件总是空的，解决一下 (→ with) [fd0da496] — 11:24 IMP1 VFY1 PASS
- [x] pid还在并没有被杀掉但是心跳不在的空闲状态下，可以显示聚焦按钮来让用户尝试找回窗口 (→ with) [0d3e52c8] — 17:45 IMP1 VFY1 PASS
- [x] 人物列表需要支持按照agent名筛选，同时默认从新到旧显示 (→ with) [7fe8eb99] — 11:34 IMP1 VFY1 PASS — 12:07 IMP1 VFY2 PASS
  我写错了，其实是任务列表，不过分支列表的筛选也留着吧
- [x] 按照agent筛选应该支持和状态一样的按钮方式筛选，收集tasks中涉及的所有agent作为选项。考虑到agent后面可能很多，做成下拉列表，默认选中自己 (→ with) [7c1db41e] — 15:09 IMP1 VFY1 PASS
- [x] 参考任务f610728e的反馈格式，统一一下添加反馈的相关逻辑和解析逻辑。然后task-merge技能新增加入，如果用户拒绝合入，则和用户讨论，最终使用相同格式添加反馈 (→ with) [a783a210] — 12:13 IMP1 VFY1 PASS · 15:11 IMP2 VFY1 PASS
  ## IMP1 反馈
  1. reopen_task（API）缺少 ## IMP{N} 反馈 标题头 — 当前只写裸文本缩进，需自动统计已有 IMP 条数并追加标题
  2. write_feedback_to_task（task-merge 拒绝时调用）同样缺少标题头 — 需与 reopen 统一格式
- [x] dashboard页面现在还没有图标 (→ with) [fd26b9e7] — 11:30 IMP1 VFY1 PASS
- [x] 任务实际上没有失败的概率，也不需要统计7日失败率 (→ with) [50deb6ff] — 15:54 IMP1 VFY1 PASS · 16:35 IMP1 VFY1 PASS
- [x] 现在托盘应用被关闭，后台服务还在跑，应该跟着一起关闭 (→ with) [a0d94d9f] — 17:50 IMP1 VFY2 PASS

## 2026-07-13

- [ ] streamline-test-verify-docs (→ with) [770ea8b5]
