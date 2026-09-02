# 河南招聘公告监控与飞书推送

当前版本：0.2.0，对应需求规格v1.2及“每天运行一次、优先使用GitHub Actions”的后续业务决定。当前默认仅启用河南省人事考试中心首页栏目，其余P0栏目必须完成生产网络踩点后再启用。

## 首选运行方式

当前首选GitHub私有仓库和GitHub Actions，每天北京时间21:05运行一次。工作流文件为：

```text
.github/workflows/daily-monitor.yml
```

首次运行只建立冷启动基线，但会发送运行回执；后续发现新公告时发送公告卡片。SQLite状态自动保存到 `state/recruit_monitor.db` 并提交回仓库。详细步骤见 `GITHUB_DEPLOYMENT.md`。

## 已实现能力

1. JSON配置和官方域名白名单校验。
2. 15秒超时、失败重试2次、重定向域名校验和5MiB页面上限。
3. UTF-8、GBK及GB18030兼容解码。
4. 招聘白名单、选调生与教师专项硬过滤、一般流程降噪。
5. “考试录用、考录、选聘”等关键词覆盖。
6. 重大变更关联失败时按招聘语境fail-open，并标记“未关联原事项”。
7. 按feed冷启动、URL幂等去重、公告主体去重和简化deliveries投递状态。
8. 飞书卡片每批最多10条，隐藏“应届生相关性未知”标签。
9. 每日健康回执、GitHub状态持久化、按天滚动日志和systemd备选配置。
10. 离线HTML回放、规则、解析、卡片、冷启动和GitHub工作流测试。

## 本地验收

要求Python 3.10及以上，不依赖第三方Python包。

```bash
python3 -m unittest discover -s tests -v
python3 -m app.cli --config-dir config --db data/recruit_monitor.db phase0 --output reports/phase0_report.json
python3 -m app.cli --config-dir config --db data/recruit_monitor.db run --feed hnrsks_home --fixture tests/fixtures/hnrsks_home.html
python3 -m app.cli --config-dir config --db data/recruit_monitor.db daily --dry-run
```

第一次运行样本只建立冷启动基线，不创建推送。随后使用包含新URL的样本运行，才会创建pending投递。

查看待发送卡片但不调用飞书：

```bash
python3 -m app.cli --config-dir config --db data/recruit_monitor.db deliver --dry-run
python3 -m app.cli --config-dir config --db data/recruit_monitor.db heartbeat --dry-run
```

## GitHub部署

按照 `GITHUB_DEPLOYMENT.md` 建立私有仓库，配置 `FEISHU_WEBHOOK_URL` 和可选的 `FEISHU_SECRET`，然后手工执行一次“河南招聘每日监控”工作流完成冷启动验收。

## 独立服务器备选方案

1. 将目录部署到`/opt/henan-recruit-monitor`，建立专用低权限用户并授予data、logs、backups目录写权限。
2. 复制`.env.example`为`/etc/henan-recruit-monitor.env`，填入飞书Webhook和可选签名密钥，文件权限设为600。
3. 在生产主机执行低频网络踩点：

```bash
python3 -m app.cli --config-dir config --db data/recruit_monitor.db phase0 --network --output reports/phase0_production.json
```

4. 先在测试群完成一次冷启动和模拟新公告推送，再安装`deploy`目录中的systemd单元。
5. 如改用独立服务器，也按每天一次设置定时任务，并保持`aggregation_window=0`。

## 安全边界

Webhook、签名密钥和PushPlus Token只允许通过环境变量提供，不得写入配置、数据库、日志或测试样本。`sources.json`中只有`enabled=true`的栏目会参与运行；`verification_status`为pending的栏目不得在未踩点时启用。

## 当前阻塞项

GitHub工作流和持久化状态机制已经就绪。真实飞书Webhook尚未写入仓库密钥，河南省人事考试中心仍需通过GitHub运行器完成一次真实网络验收；其他P0栏目继续保持禁用。具体状态见`PHASE0_STATUS.md`。
