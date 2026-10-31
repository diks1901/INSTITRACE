"""Admin/demo-maintenance endpoints (ADMIN role only)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import DemoUser
from ..security import require_roles
from ..seed import seed_demo
from ..services.audit import record_audit

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/demo-reset")
def demo_reset(
    db: Session = Depends(get_db),
    user: DemoUser = Depends(require_roles("ADMIN")),
):
    """Explicit, safe demo reset: wipes all rows and reseeds synthetic data."""
    record_audit(db, actor=user.username, event_type="DEMO_RESET_REQUESTED",
                 entity_type="system", entity_id="database",
                 summary="Explicit demo reset requested")
    db.commit()
    result = seed_demo(db, reset=True)
    return result
