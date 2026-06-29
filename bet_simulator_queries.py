"""Read-only flat-stake simulation over archived Top-1 predictions."""
from __future__ import annotations

import sqlite3
from typing import Any, Iterator

from performance_queries import PERFORMANCE_CTE, PAGE_SIZE, normalize_filters, _where
from race_scope import configure_sqlite


def normalize_bet_filters(date=None, track=None, model="Ensemble", outcome="all", stake=20) -> dict[str, Any]:
    base = normalize_filters(date, track, model or "Ensemble", outcome)
    try:
        amount = float(stake)
    except (TypeError, ValueError) as exc:
        raise ValueError("stake must be numeric") from exc
    if not 0 < amount <= 1_000_000:
        raise ValueError("stake must be greater than 0 and at most 1000000")
    return {**base, "stake": amount}


def _parts(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    return _where(filters)


def _row_sql(where: str) -> str:
    return f"""SELECT race_date,city AS track,race_no,race_time,model,predicted_horse,
               winner_name,correct,decimal_odds,race_start_at,prediction_time,race_id,
               CASE WHEN correct=0 OR decimal_odds>0 THEN 1 ELSE 0 END AS bet_eligible
        FROM evaluated{where}"""


def _money(row: dict[str, Any], stake: float) -> dict[str, Any]:
    eligible = bool(row["bet_eligible"])
    if not eligible:
        returned = net = None
    elif row["correct"]:
        returned = stake * float(row["decimal_odds"]); net = returned - stake
    else:
        returned = 0.0; net = -stake
    return {**row, "stake": stake, "return_amount": returned, "net_profit": net,
            "odds_status": "AVAILABLE" if eligible else "ODDS_MISSING"}


def history(connection: sqlite3.Connection, filters: dict[str, Any], page: int = 1) -> dict[str, Any]:
    configure_sqlite(connection); page=max(1,int(page)); where,params=_parts(filters)
    rows=connection.execute(PERFORMANCE_CTE+_row_sql(where)+"""
        ORDER BY race_start_at DESC,prediction_time DESC LIMIT ? OFFSET ?""",
        [*params,PAGE_SIZE,(page-1)*PAGE_SIZE]).fetchall()
    total=connection.execute(PERFORMANCE_CTE+f"SELECT COUNT(*) FROM evaluated{where}",params).fetchone()[0]
    return {"page":page,"page_size":PAGE_SIZE,"total":int(total),
            "pages":max(1,(int(total)+PAGE_SIZE-1)//PAGE_SIZE),
            "rows":[_money(dict(row),filters["stake"]) for row in rows]}


def summary(connection: sqlite3.Connection, filters: dict[str, Any]) -> dict[str, Any]:
    configure_sqlite(connection); where,params=_parts(filters); stake=filters["stake"]
    rows=[_money(dict(row),stake) for row in connection.execute(
        PERFORMANCE_CTE+_row_sql(where)+" ORDER BY race_start_at,prediction_time",params
    ).fetchall()]
    bets=[row for row in rows if row["bet_eligible"]]; correct=sum(int(row["correct"]) for row in rows)
    invested=stake*len(bets); returned=sum(float(row["return_amount"] or 0) for row in bets)
    streak=max_streak=current=0
    for row in rows:
        if row["bet_eligible"] and not row["correct"]: current+=1; max_streak=max(max_streak,current)
        else: current=0
    profitable=[row for row in bets if row["net_profit"] is not None]
    best=max(profitable,key=lambda row:row["net_profit"],default=None)
    return {"has_data":bool(rows),"stake":stake,"total_races":len(rows),"bet_races":len(bets),
            "correct_predictions":correct,"accuracy_percent":100*correct/len(rows) if rows else 0,
            "total_invested":invested,"total_return":returned,"net_profit":returned-invested,
            "roi_percent":100*(returned-invested)/invested if invested else 0,
            "most_profitable_race":best,"largest_losing_streak":max_streak,
            "odds_missing_races":sum(not row["bet_eligible"] for row in rows)}


def export_rows(connection: sqlite3.Connection, filters: dict[str, Any]) -> Iterator[dict[str, Any]]:
    configure_sqlite(connection); where,params=_parts(filters)
    for row in connection.execute(PERFORMANCE_CTE+_row_sql(where)+" ORDER BY race_start_at DESC",params):
        yield _money(dict(row),filters["stake"])
