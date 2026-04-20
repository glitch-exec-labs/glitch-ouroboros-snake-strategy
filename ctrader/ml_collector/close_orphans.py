"""
One-shot orphan closer.

Finds every broker-open cTrader position across all bot accounts that has
NO matching row in ml_trades (closed_at IS NULL, ticket=X). These are
trades the collector never recorded — pre-v2 trades, failed-DB-insert
residue, or manual positions.

Closes each at the broker so the portfolio state matches ml_trades, and
the Oracle risk gate stops undercounting real exposure.

Data loss is intentional: PnL on these closures is not preserved in the
DB. For the historical 11 orphans on viper's account this is acceptable;
going forward, the collector's monitor loop backfills any orphan it sees
so this situation cannot recur.

Usage:
    cd /opt/glitch-ouroboros/ctrader
    sudo -u glitchml ml_collector/venv/bin/python -m ml_collector.close_orphans
    # --dry-run to only list orphans, not close them.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from collections import defaultdict
from typing import Dict, List, Set

import asyncpg

from . import _ctrader_compat  # noqa: F401
from executor.ctrader_client import CTraderClient

from .config import get_config, configure_logging

logger = logging.getLogger("ml_collector.close_orphans")


async def run(dry_run: bool = False) -> None:
    cfg = get_config()
    configure_logging(cfg)
    logger.info("Starting orphan closer (dry_run=%s)", dry_run)

    pool = await asyncpg.create_pool(cfg.db_dsn, min_size=1, max_size=2)

    # DB-known open tickets per account
    rows = await pool.fetch(
        "SELECT account_id, ticket FROM ml_trades "
        "WHERE closed_at IS NULL AND ticket IS NOT NULL"
    )
    known: Dict[int, Set[str]] = defaultdict(set)
    for r in rows:
        known[int(r["account_id"])].add(str(r["ticket"]))

    await pool.close()

    totals = {"orphans_found": 0, "closed": 0, "close_failed": 0}

    for bot in cfg.bots:
        client = CTraderClient(
            client_id=cfg.ctrader_client_id,
            client_secret=cfg.ctrader_client_secret,
            access_token=cfg.ctrader_access_token,
            account_id=bot.account_id,
            live=False,
        )
        try:
            positions = await client.get_open_positions()
        except Exception:
            logger.exception("ReconcileRes failed for %s (acct %d)", bot.name, bot.account_id)
            continue

        broker_tickets = {str(p["ticket"]) for p in positions}
        db_tickets = known.get(bot.account_id, set())
        orphans = [p for p in positions if str(p["ticket"]) not in db_tickets]

        logger.info(
            "%s (acct %d): %d broker-open, %d DB-open, %d ORPHAN",
            bot.name, bot.account_id, len(broker_tickets), len(db_tickets), len(orphans),
        )
        totals["orphans_found"] += len(orphans)

        for pos in orphans:
            tkt = str(pos["ticket"])
            logger.info(
                "  ORPHAN tkt=%s sym_id=%s side=%s lots=%.2f  %s",
                tkt, pos.get("symbol"), pos.get("side"), pos.get("amount", 0),
                "(would close)" if dry_run else "(closing…)",
            )
            if dry_run:
                continue
            try:
                res = await client.close_position(str(pos.get("symbol")), tkt)
                if res.get("success"):
                    totals["closed"] += 1
                    logger.info("  closed tkt=%s", tkt)
                else:
                    totals["close_failed"] += 1
                    logger.warning("  close failed tkt=%s: %s", tkt, res.get("error"))
            except Exception:
                logger.exception("  close exception tkt=%s", tkt)
                totals["close_failed"] += 1

    logger.info("Orphan closer done: %s", totals)


def main() -> None:
    ap = argparse.ArgumentParser(description="Close broker positions not tracked in ml_trades.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report orphans; do not close.")
    args = ap.parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
