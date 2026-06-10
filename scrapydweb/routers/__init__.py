# coding: utf-8
"""Router registration.

The UI is the React SPA served from frontend/dist (see app.py). What remains
here is the JSON surface:
- apiv2: /api/... endpoints the SPA reads from
- api: the legacy scrapyd JSON proxy (/{node}/api/{opt}/...) used for actions
- tasks/schedule/deploy xhr + run/check/upload endpoints (JSON)
- log: stats/utf8/report JSON (also polled by the monitor subprocess)
- alerts (test sends), metadata
"""


def register_routers(app):
    from . import api, auth, metadata, settings
    app.include_router(auth.router)
    app.include_router(metadata.router)
    app.include_router(settings.router)
    app.include_router(api.router)
    from . import alerts, deploy, deploy_ci, log, projects, schedule, tasks, webhooks
    app.include_router(log.router)
    app.include_router(alerts.router)
    app.include_router(deploy.router)
    app.include_router(deploy_ci.router)
    app.include_router(projects.router)
    app.include_router(webhooks.router)
    app.include_router(schedule.router)
    app.include_router(tasks.router)
    # JSON API for the React (shadcn) frontend
    from . import apiv2
    app.include_router(apiv2.router)
