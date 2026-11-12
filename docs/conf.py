#!/usr/bin/env python
"""Sphinx configuration for bilingual Powder Level Monitor documentation."""
from pathlib import Path
import sys

DOCS = Path(__file__).resolve().parent
sys.path.insert(0, str(DOCS.parent / "src"))
project = "Powder Level Monitor"
release = "0.1.0"
root_doc = "index"
source_suffix = {".rst": "restructuredtext", ".md": "markdown"}
extensions = ["myst_parser", "sphinx.ext.autodoc", "sphinx.ext.autosummary", "sphinx.ext.napoleon", "sphinx.ext.viewcode"]
autosummary_generate = True
autodoc_typehints = "description"
autodoc_mock_imports = ["grpc_frame", "grpc", "x_logger", "cv2", "PySide6"]
html_theme = "sphinx_rtd_theme"
html_theme_options = {"collapse_navigation": False, "navigation_depth": 4, "titles_only": False}
exclude_patterns = ["_build", "_static", "en", "ja"]
