"""Simple-PE pipeline integration for Asimov."""

from .simplepe import SimplePE

__all__ = ["SimplePE"]

try:
    from importlib.metadata import PackageNotFoundError, version
except ImportError:
    from importlib_metadata import PackageNotFoundError, version

try:
    __version__ = version(__name__)
except PackageNotFoundError:
    __version__ = "unknown"
