# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import sys
import shutil
from pathlib import Path

sys.path.insert(0, os.path.abspath("../.."))


# -- Project information -----------------------------------------------------

project = "NodeGraph"
copyright = "2023, Xing Wang"
author = "Xing Wang"

# The full version, including alpha/beta/rc tags
release = "0.0.1"


# -- Any type configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "sphinx_rtd_theme",
    "sphinx.ext.autodoc",
    "sphinx.ext.coverage",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "nbsphinx",
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
# html_theme = 'alabaster'
html_theme = "sphinx_rtd_theme"

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]
html_css_files = []


# Function to copy HTML files
def copy_html_files(app, exception):
    """
    Copy all .html files from source to build directory, maintaining the directory structure.
    """
    copy_print_info = "Copying HTML files to build directory"
    print()
    print(copy_print_info)
    print(len(copy_print_info) * "=")
    if exception is not None:  # Only copy files if the build succeeded
        print(
            "Build failed, but we still try to copy the HTML files to the build directory"
        )
    try:
        src_path = Path(app.builder.srcdir)
        build_path = Path(app.builder.outdir)

        copy_print_info = f"Copying html files from sphinx src directory {src_path}"
        print()
        print(copy_print_info)
        print(len(copy_print_info) * "-")
        for html_file in src_path.rglob("*.html"):
            relative_path = html_file.relative_to(src_path)
            destination_file = build_path / relative_path
            destination_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(html_file, destination_file)
            print(f"Copy {html_file} to {destination_file}")
    except Exception as e:
        print(f"Failed to copy HTML files: {e}")


def setup(app):
    app.connect("build-finished", copy_html_files)
