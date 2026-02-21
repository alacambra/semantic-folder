"""Pytest configuration — adds src/ to sys.path for test discovery."""

import os
import sys

# Add src/ to Python path so tests can import from semantic_folder
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
