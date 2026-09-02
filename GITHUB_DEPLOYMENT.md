# GitHub Actions部署说明

## 运行口径

1. 使用GitHub私有仓库。
2. 每天北京时间21:05自动运行一次，对应工作流中的UTC时间13:05。
3. 首次运行建立冷启动基线，不推送列表中的存量公告，但会发送每日运行回执。
4. 第二次及以后只推送新发现且符合规则的公告。
5. SQLite数据库保存在 `state/recruit_monitor.db` 并由工作流自动提交，避免临时运行器结束后丢失去重状态。
6. 当前只启用已经形成离线解析样本的河南省人事考试中心首页栏目。其他P0栏目完成生产网络踩点后再启用。

## 一次性设置

### 1. 建立私有仓库

在GitHub中新建一个私有仓库，建议命名为：

```text
henan-recruit-monitor
```

将本项目全部文件上传到仓库根目录，必须保留 `.github/workflows/daily-monitor.yml`。

### 2. 配置飞书密钥

进入仓库：

```text
Settings → Secrets and variables → Actions → New repository secret
```

新增以下密钥：

| 名称 | 是否必填 | 内容 |
|---|---:|---|
| `FEISHU_WEBHOOK_URL` | 是 | 飞书群自定义机器人Webhook完整地址 |
| `FEISHU_SECRET` | 否 | 机器人开启签名校验时填写 |

不得把Webhook直接写入配置文件、工作流、Issue或运行日志。

### 3. 开启工作流写权限

进入：

```text
Settings → Actions → General → Workflow permissions
```

选择：

```text
Read and write permissions
```

保存设置。该权限只用于自动提交 `state/recruit_monitor.db`。

### 4. 首次手工验收

进入：

```text
Actions → 河南招聘每日监控 → Run workflow
```

验收结果应同时满足：

1. 工作流显示绿色成功。
2. 飞书收到“招聘监控每日运行回执”。
3. 仓库出现 `state/recruit_monitor.db`。
4. 首次运行不推送现有存量公告。

## 日常运行

完成首次验收后无需保持电脑开机。GitHub每天自动运行，飞书每天至少收到一条运行回执；发现新公告时会先发送公告卡片，再发送运行回执。

如需临时测试，可以在Actions页面再次点击 `Run workflow`。重复执行不会重复推送已经成功发送的公告。

## 修改运行时间

工作流使用UTC时间。北京时间减8小时后写入cron表达式。

当前配置：

```yaml
- cron: '5 13 * * *'
```

表示每天北京时间21:05执行。建议分钟数不要设为 `0`，以减少整点调度拥堵。

## 故障判断

1. 工作流红色失败：进入该次运行查看失败步骤。
2. 飞书未收到回执：优先检查 `FEISHU_WEBHOOK_URL` 和机器人是否被移出群聊。
3. 无公告推送但有回执：通常表示没有符合条件的新公告，属于正常状态。
4. 状态提交失败：检查工作流是否具有读写权限，以及默认分支是否设置了禁止机器人提交的保护规则。
5. 官方网站改版：采集步骤会失败，数据库保留历史状态，修复解析器后不会重复推送旧公告。
