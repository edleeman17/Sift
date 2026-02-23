"""Route modules for the notification processor."""

from fastapi import APIRouter

from routes.notification import router as notification_router
from routes.status import router as status_router
from routes.rules import router as rules_router
from routes.dashboard import router as dashboard_router


def include_all_routes(app):
    """Include all route modules in the app."""
    app.include_router(notification_router)
    app.include_router(status_router)
    app.include_router(rules_router)
    app.include_router(dashboard_router)
