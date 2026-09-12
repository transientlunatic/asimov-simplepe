# Configuration file for the Sphinx documentation builder.

# ---------------------------------------------------------------------------
# Project information
# ---------------------------------------------------------------------------

project = "asimov-simplepe"
copyright = "2026, Daniel Williams"
author = "Daniel Williams"

try:
    from importlib.metadata import version as _get_version

    release = _get_version("asimov-simplepe")
except Exception:
    release = "unknown"

# ---------------------------------------------------------------------------
# General configuration
# ---------------------------------------------------------------------------

extensions = [
    "kentigern",
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "numpydoc",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Autodoc
autodoc_member_order = "bysource"
autodoc_typehints = "description"

# numpydoc
numpydoc_show_class_members = False

# Intersphinx -- link into the Python stdlib
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# ---------------------------------------------------------------------------
# HTML output
# ---------------------------------------------------------------------------

html_theme = "kentigern"
html_theme_options = {
    "navbar_title": "asimov-simplepe",
}
