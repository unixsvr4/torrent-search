"""Importing this package registers every built-in source.

Add a tracker/index by dropping a module here and importing it below.
"""
from . import internet_archive, linux_distros  # noqa: F401

__all__ = ["internet_archive", "linux_distros"]
