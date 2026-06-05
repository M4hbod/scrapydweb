# coding: utf-8
"""Router registration. Each area gets its own module under this package."""


def register_routers(app):
    # Routers are added here phase by phase during the FastAPI migration.
    from . import (api, clusterreports, index, items, jobs, logs, metadata,
                   multinode, nodereports, projects, servers, settings)
    app.include_router(index.router)
    app.include_router(metadata.router)
    app.include_router(api.router)
    app.include_router(settings.router)
    app.include_router(servers.router)
    app.include_router(jobs.router)
    app.include_router(nodereports.router)
    app.include_router(clusterreports.router)
    app.include_router(multinode.router)
    app.include_router(projects.router)
    app.include_router(logs.router)
    app.include_router(items.router)
    from . import deploy, log, parse, schedule, send_text, tasks
    app.include_router(log.router)
    app.include_router(send_text.router)
    app.include_router(parse.router)
    app.include_router(deploy.router)
    app.include_router(schedule.router)
    app.include_router(tasks.router)
