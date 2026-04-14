from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Session as SessionModel
from app.models import VPNServer


def select_best_server(db: Session, country_preference: str | None) -> VPNServer:
    stmt = (
        select(
            VPNServer,
            func.count(SessionModel.id).filter(SessionModel.status == "active").label("active_count"),
        )
        .outerjoin(SessionModel, SessionModel.server_id == VPNServer.id)
        .where(VPNServer.is_active.is_(True))
        .group_by(VPNServer.id)
    )
    rows = db.execute(stmt).all()
    if not rows:
        raise ValueError("No active servers available")

    if country_preference:
        pref = country_preference.upper()
        preferred = [r for r in rows if r[0].country_code == pref]
        if preferred:
            rows = preferred

    # Least utilization first
    rows.sort(key=lambda r: (r[1] / max(r[0].max_sessions, 1), r[1], r[0].id))
    selected_server, active_count = rows[0]
    if active_count >= selected_server.max_sessions:
        raise ValueError("Server capacity reached")
    return selected_server
