import os
import sys
import django

sys.path.insert(0, os.path.abspath('../..'))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'global_exchange.settings')
django.setup()

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'is2-proyecto'
copyright = '2026, grupo 1'
author = 'grupo 1'
release = '2'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = ['sphinx.ext.autodoc',      
    'sphinx.ext.napoleon',     
    'sphinx.ext.viewcode',
    ]

templates_path = ['_templates']
exclude_patterns = []

language = 'es'

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'alabaster'
html_static_path = ['_static']
