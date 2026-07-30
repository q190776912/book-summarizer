"""book-summarizer shared library.

Pure cross-stage helpers collected here so the flat scripts stop duplicating
constants and utilities. Imported by the root scripts via
``sys.path.insert(0, dirname(__file__))`` + ``from lib.xxx import ...``.
"""
