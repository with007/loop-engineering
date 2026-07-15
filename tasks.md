# Tasks

> 约定: 状态和详情见 Web 面板。本文由 state.json 自动生成，勿手动编辑。

## 2026-06-26

- [x] refactor-core-architecture (→ with) [f610728e]
  ## IMP1 反馈
  1. routers/pages.py 和 routers/fragments.py 为空壳，路由未迁移。需从 app.py 搬入页面路由和 HTMX 片段路由，app.py 精简到仅实例+注册+start_server
  2. filter_tasks 的 order 和 filter_name 参数为 stub，需补全排序和 agent 名筛选逻辑，消除 4 个路由中的重复实现
  3. 补齐 test_config.py（deep_merge）、test_control.py（状态机）、test_runlog.py（写入/查询/PASS率）
  4. pip install 需先关闭正在运行的 loop.exe 进程（taskkill /F /IM loop.exe），再重试安装
  ## IMP2 反馈
  1. pages.py 重构后缺少模板上下文变量：/control 缺少 status、/settings 缺少 config、/runs 缺少 pass_rate — 对照原 app.py 补齐
- [x] 现在页面好像会隔几秒重新加载，导致输入被清空 (→ with) [a35f86a5]
- [x] improve-claude-git-robustness — 借鉴 claude-controller: env清理/claude路径解析/git fetch重试/离线模式/pytest (→ with) [2a09877f]
- [x] 现在生成的diff文件总是空的，解决一下 (→ with) [fd0da496]
- [x] pid还在并没有被杀掉但是心跳不在的空闲状态下，可以显示聚焦按钮来让用户尝试找回窗口 (→ with) [0d3e52c8]
- [x] 人物列表需要支持按照agent名筛选，同时默认从新到旧显示 (→ with) [7fe8eb99]
- [x] 按照agent筛选应该支持和状态一样的按钮方式筛选，收集tasks中涉及的所有agent作为选项。考虑到agent后面可能很多，做成下拉列表，默认选中自己 (→ with) [7c1db41e]
- [x] 参考任务f610728e的反馈格式，统一一下添加反馈的相关逻辑和解析逻辑。然后task-merge技能新增加入，如果用户拒绝合入，则和用户讨论，最终使用相同格式添加反馈 (→ with) [a783a210]
  ## IMP1 反馈
  1. reopen_task（API）缺少 ## IMP{N} 反馈 标题头 — 当前只写裸文本缩进，需自动统计已有 IMP 条数并追加标题
  2. write_feedback_to_task（task-merge 拒绝时调用）同样缺少标题头 — 需与 reopen 统一格式
- [x] dashboard页面现在还没有图标 (→ with) [fd26b9e7]
- [x] 任务实际上没有失败的概率，也不需要统计7日失败率 (→ with) [50deb6ff]
- [x] 现在托盘应用被关闭，后台服务还在跑，应该跟着一起关闭 (→ with) [a0d94d9f]

## 2026-07-13

- [x] streamline-test-verify-docs (→ with) [770ea8b5]
  ## IMP1 反馈
  1. commit message 描述删除了 6 个文件（VERIFY.md.j2 ×3、loop-test-init 模板/部署副本、项目根 VERIFY.md），但实际分支只包含 10 个文件修改，无任何删除。分支改动不完整。
  2. 部署页(/setup)的 TEST.md 是单独一个预览区域，与设置页(/settings)「verifier skills 和 TEST.md」合并为一个编辑入口的风格不一致。建议统一。
  ## IMP2 反馈
  agent 用 rm 物理删除文件但未 git add，删除未进入 commit。两次了：
  1. IMP1: commit 8a285be 声称删除 6 个文件，实际只有 10 个 M
  2. IMP2: commit 0ce2dc4 声称删除 6 个文件+2 HTML，实际只有 2 个 M
  根因：删除文件需用 git rm 而非 rm，或 commit 时确保 git add -A。
  ## IMP3 反馈
  1. setup 预览为空：切换项目类型后预览区域不刷新，始终显示空白，但文档 tab 按钮正常刷新 — 检查 setup.html 中项目类型切换事件是否正确触发预览更新
  2. 模板渲染缺失章节：python-server TEST.md.j2 渲染后缺少「Web 页面/模板」章节 — 精简模板时可能误删了关键 section
  3. 初始化页面不应该可以编辑验证 skill 内容：loop-verify-init 区域当前是可编辑的输入框，应该是只读预览 — 与 setup 预览问题可能同源

- [ ] task-detail-panel (→ with) [79fb9ca7]