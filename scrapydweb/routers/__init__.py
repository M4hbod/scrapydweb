# coding: utf-8
"""Router registration. Each area gets its own module under this package."""


def register_routers(app):
    # Routers are added here phase by phase during the FastAPI migration.
    from . import metadata
    app.include_router(metadata.router)
