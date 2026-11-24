"""Deterministic data generator seeding 150 days of SaaS/E-Commerce data + 4 planted mysteries."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

import duckdb

from backend.config import DB_PATH, REF_NOW


def _sql_lit(val: object) -> str:
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, datetime):
        return f"TIMESTAMP '{val.strftime('%Y-%m-%d %H:%M:%S')}'"
    if hasattr(val, "isoformat"):
        return f"DATE '{val.isoformat()}'"
    s = str(val).replace("'", "''")
    return f"'{s}'"


def _bulk_insert(con: duckdb.DuckDBPyConnection, table: str, rows: list[tuple], chunk_size: int = 2000) -> None:
    if not rows:
        return
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        values_sql = ", ".join("(" + ", ".join(_sql_lit(v) for v in row) + ")" for row in chunk)
        con.execute(f"INSERT INTO {table} VALUES {values_sql}")


def seed_database(db_path: Path = DB_PATH) -> dict[str, int]:
    """Seed raw schema tables in DuckDB with deterministic data and 4 planted mysteries."""
    rng = random.Random(42)
    if db_path.exists():
        db_path.unlink()

    con = duckdb.connect(str(db_path))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw;")

    # ------------------------------------------------------------------
    # 1. raw.users (500 accounts, 1500 users)
    # ------------------------------------------------------------------
    con.execute("""
        CREATE TABLE raw.users (
            user_id VARCHAR PRIMARY KEY,
            account_id VARCHAR,
            region VARCHAR,
            plan_tier VARCHAR,
            created_at TIMESTAMP,
            ingested_at TIMESTAMP
        );
    """)

    regions = ["EMEA", "NA", "APAC"]
    region_weights = [0.35, 0.45, 0.20]
    tiers = ["Enterprise", "Growth", "Self-Serve"]
    tier_weights = [0.20, 0.30, 0.50]

    users_rows = []
    account_meta: dict[str, tuple[str, str]] = {}
    for acc_idx in range(1, 501):
        acc_id = f"acc_{acc_idx:04d}"
        reg = rng.choices(regions, weights=region_weights, k=1)[0]
        tier = rng.choices(tiers, weights=tier_weights, k=1)[0]
        account_meta[acc_id] = (reg, tier)

    for u_idx in range(1, 1501):
        acc_id = f"acc_{((u_idx - 1) % 500) + 1:04d}"
        reg, tier = account_meta[acc_id]
        created = REF_NOW - timedelta(days=rng.randint(30, 180))
        users_rows.append((f"usr_{u_idx:05d}", acc_id, reg, tier, created, REF_NOW - timedelta(minutes=20)))

    _bulk_insert(con, "raw.users", users_rows)

    # ------------------------------------------------------------------
    # 2. raw.orders, raw.order_items, raw.payments & raw.support_tickets
    #    Includes Mystery 3: Q3 Net Revenue for accounts with support tickets
    #    Target: ~140 ticketed accounts in Q3 with exact $418,000 net revenue,
    #    and ~3.4 tickets per ticketed account -> naive join ~ $1,421,200.
    # ------------------------------------------------------------------
    con.execute("""
        CREATE TABLE raw.orders (
            order_id VARCHAR PRIMARY KEY,
            account_id VARCHAR,
            user_id VARCHAR,
            order_date DATE,
            net_revenue_usd DOUBLE,
            region VARCHAR,
            plan_tier VARCHAR,
            status VARCHAR,
            ingested_at TIMESTAMP
        );
    """)
    con.execute("""
        CREATE TABLE raw.order_items (
            order_item_id VARCHAR PRIMARY KEY,
            order_id VARCHAR,
            sku VARCHAR,
            quantity INTEGER,
            unit_price_usd DOUBLE,
            ingested_at TIMESTAMP
        );
    """)
    con.execute("""
        CREATE TABLE raw.payments (
            payment_id VARCHAR PRIMARY KEY,
            order_id VARCHAR,
            payment_gateway VARCHAR,
            payment_status VARCHAR,
            ingested_at TIMESTAMP
        );
    """)
    con.execute("""
        CREATE TABLE raw.support_tickets (
            ticket_id VARCHAR PRIMARY KEY,
            account_id VARCHAR,
            created_date DATE,
            priority VARCHAR,
            category VARCHAR,
            ingested_at TIMESTAMP
        );
    """)

    orders_rows = []
    order_items_rows = []
    payments_rows = []
    tickets_rows = []

    ticketed_q3_accounts = [f"acc_{i:04d}" for i in range(1, 141)]  # 140 accounts
    non_ticketed_accounts = [f"acc_{i:04d}" for i in range(141, 501)]

    order_seq = 1
    item_seq = 1
    pay_seq = 1
    ticket_seq = 1

    # Seed Q3 orders for ticketed accounts: 140 accounts, 2 orders each = 280 orders,
    # each $1,492.857142857... -> total = $418,000.00
    q3_start = datetime(2026, 7, 1).date()
    for idx, acc_id in enumerate(ticketed_q3_accounts):
        reg, tier = account_meta[acc_id]
        for j in range(2):
            o_id = f"ord_{order_seq:06d}"
            order_seq += 1
            o_date = q3_start + timedelta(days=(idx * 3 + j * 17) % 90)
            # Exact sum across 280 orders = 418,000.00
            rev = 1492.86 if (idx * 2 + j) < 200 else 1492.85
            orders_rows.append((
                o_id, acc_id, f"usr_{((idx % 500) + 1):05d}", o_date,
                rev, reg, tier, "completed", REF_NOW - timedelta(minutes=25),
            ))
            order_items_rows.append((
                f"oi_{item_seq:07d}", o_id, "SKU-PRO-ANNUAL", 1, rev, REF_NOW - timedelta(minutes=25)
            ))
            item_seq += 1
            payments_rows.append((
                f"pay_{pay_seq:06d}", o_id, "Stripe", "captured", REF_NOW - timedelta(minutes=25)
            ))
            pay_seq += 1

        # 3 or 4 tickets per ticketed account in Q3 -> avg 3.40 tickets/account
        # 140 * 3.4 = 476 tickets total (84 accounts with 3, 56 accounts with 4 -> 252 + 224 = 476)
        num_tickets = 4 if idx < 56 else 3
        for t in range(num_tickets):
            t_date = q3_start + timedelta(days=(idx * 5 + t * 11) % 90)
            tickets_rows.append((
                f"tkt_{ticket_seq:06d}", acc_id, t_date,
                rng.choice(["high", "medium", "low"]),
                rng.choice(["billing", "sso_config", "api_limit"]),
                REF_NOW - timedelta(minutes=30),
            ))
            ticket_seq += 1

    # Seed background orders across 150 days for non-ticketed accounts
    start_date = (REF_NOW - timedelta(days=149)).date()
    for day_offset in range(150):
        cur_date = start_date + timedelta(days=day_offset)
        for _ in range(14):
            acc_id = rng.choice(non_ticketed_accounts)
            reg, tier = account_meta[acc_id]
            o_id = f"ord_{order_seq:06d}"
            order_seq += 1
            rev = round(rng.uniform(450.0, 2400.0), 2)
            orders_rows.append((
                o_id, acc_id, f"usr_{rng.randint(1, 1500):05d}", cur_date,
                rev, reg, tier, "completed", REF_NOW - timedelta(minutes=25),
            ))
            order_items_rows.append((
                f"oi_{item_seq:07d}", o_id, rng.choice(["SKU-CORE", "SKU-ENT"]), 1, rev,
                REF_NOW - timedelta(minutes=25),
            ))
            item_seq += 1
            payments_rows.append((
                f"pay_{pay_seq:06d}", o_id, rng.choice(["Stripe", "Adyen_3DS", "PayPal"]),
                "captured", REF_NOW - timedelta(minutes=25),
            ))
            pay_seq += 1

    _bulk_insert(con, "raw.orders", orders_rows)
    _bulk_insert(con, "raw.order_items", order_items_rows)
    _bulk_insert(con, "raw.payments", payments_rows)
    _bulk_insert(con, "raw.support_tickets", tickets_rows)

    # ------------------------------------------------------------------
    # 3. raw.checkout_events (Mystery 1: EU Checkout Conversion -19% WoW)
    #    Baseline week: 2026-11-10 .. 2026-11-16
    #    Current week:  2026-11-17 .. 2026-11-23
    #    EMEA + iOS Safari + Adyen_3DS + v2.14 drops from 64% -> 8%
    # ------------------------------------------------------------------
    con.execute("""
        CREATE TABLE raw.checkout_events (
            checkout_session_id VARCHAR PRIMARY KEY,
            user_id VARCHAR,
            event_date DATE,
            region VARCHAR,
            device_os VARCHAR,
            payment_gateway VARCHAR,
            app_version VARCHAR,
            converted INTEGER,
            timeout_ms INTEGER,
            ingested_at TIMESTAMP
        );
    """)

    checkout_rows = []
    cs_seq = 1
    devices = ["iOS Safari", "Android Chrome", "Desktop Chrome", "Desktop Safari"]
    gateways = ["Stripe", "Adyen_3DS", "PayPal"]

    for day_offset in range(90):
        cur_date = (REF_NOW - timedelta(days=89 - day_offset)).date()
        is_current_week = cur_date >= datetime(2026, 11, 17).date()
        app_ver_pool = ["v2.14", "v2.13"] if is_current_week else ["v2.12", "v2.13"]

        for ev_i in range(420):
            reg = rng.choices(regions, weights=[0.45, 0.35, 0.20], k=1)[0]
            dev = rng.choices(devices, weights=[0.42, 0.20, 0.23, 0.15], k=1)[0]
            gw = rng.choices(gateways, weights=[0.30, 0.55, 0.15], k=1)[0]
            ver = rng.choices(app_ver_pool, weights=[0.85, 0.15], k=1)[0] if is_current_week else rng.choice(app_ver_pool)

            # Mystery 1 trigger: EMEA + iOS Safari + Adyen_3DS + v2.14
            if is_current_week and reg == "EMEA" and dev == "iOS Safari" and gw == "Adyen_3DS" and ver == "v2.14":
                converted = 1 if (ev_i % 20 == 0) else 0  # 5% conversion
                timeout_ms = rng.randint(14500, 30000)
            else:
                converted = 1 if (ev_i % 20 < 13) else 0  # deterministic 65% baseline conversion
                timeout_ms = rng.randint(250, 1200)
            checkout_rows.append((
                f"chk_{cs_seq:07d}",
                f"usr_{rng.randint(1, 1500):05d}",
                cur_date,
                reg,
                dev,
                gw,
                ver,
                converted,
                timeout_ms,
                REF_NOW - timedelta(minutes=15),
            ))
            cs_seq += 1

    _bulk_insert(con, "raw.checkout_events", checkout_rows)

    # ------------------------------------------------------------------
    # 4. raw.telemetry_eu (Mystery 2: Upstream Pipeline Outage)
    #    Stopped ingesting 16 hours before REF_NOW (2026-11-24 02:00:00)
    #    AND has a 68% NULL spike in session_id on the latest day!
    # ------------------------------------------------------------------
    con.execute("""
        CREATE TABLE raw.telemetry_eu (
            event_id VARCHAR PRIMARY KEY,
            user_id VARCHAR,
            account_id VARCHAR,
            session_id VARCHAR,
            event_ts TIMESTAMP,
            event_date DATE,
            region VARCHAR,
            plan_tier VARCHAR,
            ingested_at TIMESTAMP
        );
    """)

    telemetry_rows = []
    tel_seq = 1
    outage_cutoff = REF_NOW - timedelta(hours=16)  # 2026-11-24 02:00:00

    for day_offset in range(60):
        cur_date = (REF_NOW - timedelta(days=59 - day_offset)).date()
        is_latest_day = cur_date == REF_NOW.date()

        # EMEA telemetry: healthy for days 0..58, broken on day 59 (latest day)
        if not is_latest_day:
            daily_n = 160 + rng.randint(-8, 8)
            for u_idx in range(221, 221 + daily_n):
                ev_ts = datetime.combine(cur_date, datetime.min.time()) + timedelta(hours=rng.randint(0, 23))
                telemetry_rows.append((
                    f"tel_{tel_seq:08d}",
                    f"usr_{u_idx:05d}",
                    f"acc_{((u_idx - 1) % 100) + 1:04d}",
                    f"sess_{tel_seq:08d}",
                    ev_ts,
                    cur_date,
                    "EMEA",
                    "Enterprise",
                    ev_ts + timedelta(minutes=15),
                ))
                tel_seq += 1
        else:
            # On latest day: only 25 events before outage_cutoff, and 68% NULL session_id
            for u_idx in range(221, 246):
                ev_ts = outage_cutoff - timedelta(minutes=rng.randint(5, 110))
                is_null_sess = (u_idx - 221) < 17  # 17 / 25 = 68% NULL
                telemetry_rows.append((
                    f"tel_{tel_seq:08d}",
                    f"usr_{u_idx:05d}",
                    f"acc_{((u_idx - 1) % 100) + 1:04d}",
                    None if is_null_sess else f"sess_{tel_seq:08d}",
                    ev_ts,
                    cur_date,
                    "EMEA",
                    "Enterprise",
                    outage_cutoff,
                ))
                tel_seq += 1

    _bulk_insert(con, "raw.telemetry_eu", telemetry_rows)

    # ------------------------------------------------------------------
    # 5. raw.trials (Mystery 4: Simpson's Paradox Mix-Shift)
    #    Baseline week (2026-11-10..2026-11-16):
    #      Enterprise: 400 trials, 45% conv (180)
    #      Self-Serve: 1600 trials, 15% conv (240) -> Overall: 21.0%
    #    Current week (2026-11-17..2026-11-23):
    #      Enterprise: 400 trials, 48% conv (192)  (+3.0pp UP)
    #      Self-Serve: 4600 trials, 16% conv (736) (+1.0pp UP) -> Overall: 18.56% (-2.44pp / -11.6% rel)
    # ------------------------------------------------------------------
    con.execute("""
        CREATE TABLE raw.trials (
            trial_id VARCHAR PRIMARY KEY,
            user_id VARCHAR,
            trial_date DATE,
            plan_tier VARCHAR,
            acquisition_channel VARCHAR,
            converted INTEGER,
            ingested_at TIMESTAMP
        );
    """)

    trials_rows = []
    tr_seq = 1

    # Earlier history (days 0..75 before baseline)
    for day_offset in range(76):
        cur_date = (REF_NOW - timedelta(days=89 - day_offset)).date()
        for i in range(40):
            tier = "Enterprise" if i < 8 else "Self-Serve"
            conv = 1 if (i % 2 == 0 if tier == "Enterprise" else i % 7 == 0) else 0
            trials_rows.append((
                f"trl_{tr_seq:07d}", f"usr_{rng.randint(1, 1500):05d}", cur_date,
                tier, "Organic", conv, REF_NOW - timedelta(minutes=15),
            ))
            tr_seq += 1

    # Baseline week: 2026-11-10 .. 2026-11-16 (exact counts for deterministic Simpson's Paradox)
    base_start = datetime(2026, 11, 10).date()
    for d in range(7):
        cur_date = base_start + timedelta(days=d)
        # ~57 Enterprise/day, 400 total; ~228 Self-Serve/day, 1600 total
        ent_n = 58 if d < 1 else 57  # 58 + 6*57 = 400
        ss_n = 229 if d < 4 else 228  # 4*229 + 3*228 = 1600
        for i in range(ent_n):
            conv = 1 if i < round(ent_n * 0.45) else 0
            trials_rows.append((
                f"trl_{tr_seq:07d}", f"usr_{rng.randint(1, 1500):05d}", cur_date,
                "Enterprise", "Paid_Search", conv, REF_NOW - timedelta(minutes=15),
            ))
            tr_seq += 1
        for i in range(ss_n):
            conv = 1 if i < round(ss_n * 0.15) else 0
            trials_rows.append((
                f"trl_{tr_seq:07d}", f"usr_{rng.randint(1, 1500):05d}", cur_date,
                "Self-Serve", "Organic", conv, REF_NOW - timedelta(minutes=15),
            ))
            tr_seq += 1

    # Current week: 2026-11-17 .. 2026-11-23
    curr_start = datetime(2026, 11, 17).date()
    for d in range(7):
        cur_date = curr_start + timedelta(days=d)
        ent_n = 58 if d < 1 else 57  # 400 total
        ss_n = 658 if d < 1 else 657  # 658 + 6*657 = 4600 total (viral surge!)
        for i in range(ent_n):
            conv = 1 if i < round(ent_n * 0.48) else 0
            trials_rows.append((
                f"trl_{tr_seq:07d}", f"usr_{rng.randint(1, 1500):05d}", cur_date,
                "Enterprise", "Paid_Search", conv, REF_NOW - timedelta(minutes=15),
            ))
            tr_seq += 1
        for i in range(ss_n):
            conv = 1 if i < round(ss_n * 0.16) else 0
            trials_rows.append((
                f"trl_{tr_seq:07d}", f"usr_{rng.randint(1, 1500):05d}", cur_date,
                "Self-Serve", "Viral_Social", conv, REF_NOW - timedelta(minutes=15),
            ))
            tr_seq += 1

    _bulk_insert(con, "raw.trials", trials_rows)

    counts = {
        "users": len(users_rows),
        "orders": len(orders_rows),
        "order_items": len(order_items_rows),
        "payments": len(payments_rows),
        "support_tickets": len(tickets_rows),
        "checkout_events": len(checkout_rows),
        "telemetry_eu": len(telemetry_rows),
        "trials": len(trials_rows),
    }
    con.close()
    return counts


if __name__ == "__main__":
    summary = seed_database()
    print("Seeded MetricPulse warehouse:", summary)
