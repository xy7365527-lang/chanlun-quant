"""Integration utilities for external adapters."""

from .factory import ExternalBundle, load_external_components
from .inspector import inspect_external

__all__ = ["inspect_external", "ExternalBundle", "load_external_components"]

