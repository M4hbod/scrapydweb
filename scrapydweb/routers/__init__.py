# coding: utf-8
"""Router registration. Each area gets its own module under this package."""


def register_routers(app):
    # Routers are added here phase by phase during the FastAPI migration.
    from . import api, metadata, settings
    app.include_router(metadata.router)
    app.include_router(api.router)
    app.include_router(settings.router)
