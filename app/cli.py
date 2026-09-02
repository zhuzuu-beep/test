from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .database import Database
from .delivery import DeliveryError, FeishuWebhookSender, build_health_card, deliver_pending
from .logsetup import configure_logging
from .phase0 import run_phase0, write_report
from .pipeline import Pipeline


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="河南招聘公告监控")
    parser.add_argument("--config-dir", default=os.getenv("APP_CONFIG_DIR", "config"))
    parser.add_argument("--db", default=os.getenv("APP_DB_PATH", "data/recruit_monitor.db"))
    parser.add_argument("--log-dir", default=os.getenv("APP_LOG_DIR", "logs"))
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="初始化SQLite数据库")
    phase0 = sub.add_parser("phase0", help="执行环境与渠道核验")
    phase0.add_argument("--network", action="store_true", help="对已启用栏目执行低频网络检查")
    phase0.add_argument("--output", default="reports/phase0_report.json")

    run = sub.add_parser("run", help="运行一个栏目")
    run.add_argument("--feed", required=True)
    run.add_argument("--fixture", help="使用本地HTML样本，不访问网络")
    run.add_argument("--aggregation-window", type=int, default=0)

    daily = sub.add_parser("daily", help="运行所有已启用栏目并发送每日回执")
    daily.add_argument("--dry-run", action="store_true")
    daily.add_argument("--aggregation-window", type=int, default=0)

    delivery = sub.add_parser("deliver", help="发送到期的即时公告")
    delivery.add_argument("--dry-run", action="store_true")

    heartbeat = sub.add_parser("heartbeat", help="发送或预览每日运行回执")
    heartbeat.add_argument("--dry-run", action="store_true")
    sub.add_parser("checkpoint-db", help="将SQLite WAL安全合并到主数据库")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    configure_logging(args.log_dir)
    if args.command == "init-db":
        db = Database(args.db)
        db.migrate()
        print(json.dumps({"status": "ok", "db": str(Path(args.db))}, ensure_ascii=False))
        return
    if args.command == "phase0":
        report = run_phase0(args.config_dir, args.db, args.log_dir, network=args.network)
        write_report(report, args.output)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    if args.command == "run":
        pipeline = Pipeline(args.config_dir, args.db, args.aggregation_window)
        summary = pipeline.run_feed(args.feed, args.fixture)
        print(json.dumps(summary.as_dict(), ensure_ascii=False, indent=2))
        raise SystemExit(0 if summary.status == "success" else 2)
    if args.command == "daily":
        pipeline = Pipeline(args.config_dir, args.db, args.aggregation_window)
        summaries = pipeline.run_enabled_feeds()
        webhook = os.getenv("FEISHU_WEBHOOK_URL")
        secret = os.getenv("FEISHU_SECRET")
        errors: list[dict[str, str]] = []
        delivery_payloads: list[dict[str, object]] = []
        try:
            delivery_payloads = deliver_pending(
                pipeline.db,
                webhook,
                secret,
                dry_run=args.dry_run,
            )
        except DeliveryError as exc:
            errors.append({"stage": "delivery", "error": str(exc)})

        health_payload = build_health_card(pipeline.db.health_snapshot())
        if not args.dry_run:
            if not webhook:
                errors.append({"stage": "heartbeat", "error": "未配置FEISHU_WEBHOOK_URL"})
            else:
                try:
                    FeishuWebhookSender(webhook, secret).send(health_payload)
                except DeliveryError as exc:
                    errors.append({"stage": "heartbeat", "error": str(exc)})

        pipeline.db.checkpoint()
        report = {
            "status": "failed" if errors or any(item.status != "success" for item in summaries) else "success",
            "feeds": [item.as_dict() for item in summaries],
            "delivery_batches": len(delivery_payloads),
            "health_card": health_payload,
            "errors": errors,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(0 if report["status"] == "success" else 2)
    if args.command == "deliver":
        db = Database(args.db)
        db.migrate()
        payloads = deliver_pending(
            db,
            os.getenv("FEISHU_WEBHOOK_URL"),
            os.getenv("FEISHU_SECRET"),
            dry_run=args.dry_run,
        )
        print(json.dumps(payloads, ensure_ascii=False, indent=2))
        return
    if args.command == "heartbeat":
        db = Database(args.db)
        db.migrate()
        payload = build_health_card(db.health_snapshot())
        if not args.dry_run:
            webhook = os.getenv("FEISHU_WEBHOOK_URL")
            if not webhook:
                raise SystemExit("未配置FEISHU_WEBHOOK_URL")
            FeishuWebhookSender(webhook, os.getenv("FEISHU_SECRET")).send(payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if args.command == "checkpoint-db":
        db = Database(args.db)
        db.migrate()
        checkpoint = db.checkpoint()
        print(json.dumps({"status": "ok", "checkpoint": checkpoint}, ensure_ascii=False))


if __name__ == "__main__":
    main()
