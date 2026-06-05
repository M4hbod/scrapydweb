# coding: utf-8
import logging

from .app import create_app

__all__ = ['create_app']

logging.getLogger('sqlalchemy.engine.Engine').setLevel(logging.WARNING)
