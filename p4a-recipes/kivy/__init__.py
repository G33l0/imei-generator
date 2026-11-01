"""Local override of python-for-android's Kivy recipe.

Why: the stock recipe declares python_depends = certifi, chardet, idna,
requests, urllib3, filetype. `requests` pulls in `charset-normalizer`, which
now publishes Android wheels. python-for-android (v2026.05.09 and develop)
resolves that Android wheel as "pure Python" and then hands it to a host
`pip install`, which fails with:

    charset_normalizer-...-android_24_arm64_v8a.whl is not a supported wheel
    on this platform.

This app never uses Kivy's UrlRequest (the only user of requests/certifi),
so we keep just `filetype`, which kivy.core.image imports. Everything else
about the recipe -- version, build steps, patches -- is the stock one.

Enabled by `p4a.local_recipes = ./p4a-recipes` in buildozer.spec.
"""
import importlib.util
import os

import pythonforandroid

_STOCK_DIR = os.path.join(os.path.dirname(pythonforandroid.__file__), "recipes", "kivy")

# Load the stock recipe by path: this file is itself imported under the name
# pythonforandroid.recipes.kivy, so a normal import would find ourselves.
_spec = importlib.util.spec_from_file_location(
    "_p4a_stock_kivy_recipe", os.path.join(_STOCK_DIR, "__init__.py"))
_stock = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_stock)


class G2KivyRecipe(_stock.KivyRecipe):
    python_depends = ["filetype"]

    def get_recipe_dir(self):
        # The stock patches live next to the stock recipe, not here.
        return _STOCK_DIR


recipe = G2KivyRecipe()
