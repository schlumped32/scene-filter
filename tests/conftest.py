"""Puts app/ on the path so tests import the app's modules the same way the app does
(`import theme`, `from scene_filter import core`)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
