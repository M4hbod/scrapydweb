# coding: utf-8
import logging

from .__version__ import __version__
from .app import create_app

__all__ = ['create_app', '__version__']

logging.getLogger('sqlalchemy.engine.Engine').setLevel(logging.WARNING)
