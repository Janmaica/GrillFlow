"""Adapt the v2026.05.09 Kivy recipe for the 2.3.2 source release."""

from pathlib import Path
from runpy import run_path

import pythonforandroid


upstream = Path(pythonforandroid.__file__).resolve().parent / "recipes" / "kivy"
recipe = run_path(str(upstream / "__init__.py"))["recipe"]

patches = []
for patch in recipe.patches:
    if patch == "no-ast-str.patch":
        # Kivy 2.3.2 already includes this fix.
        continue
    if isinstance(patch, tuple):
        name, condition = patch
        patches.append((str(upstream / name), condition))
    else:
        patches.append(str(upstream / patch))
recipe.patches = patches
recipe.hostpython_prerequisites = ["Cython==3.0.11"]
