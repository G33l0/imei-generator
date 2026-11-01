"""Guards for the Android build configuration (no Buildozer needed)."""
import ast
import configparser
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def spec():
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(os.path.join(ROOT, "buildozer.spec"))
    return cp["app"]


class BuildConfigTests(unittest.TestCase):
    def test_embedded_files_are_packaged(self):
        exts = [e.strip() for e in spec()["source.include_exts"].split(",")]
        for ext in ("py", "kv", "sqlite", "ttf", "png"):
            self.assertIn(ext, exts)
        self.assertTrue(os.path.getsize(os.path.join(ROOT, "data", "tac.sqlite")) > 100000)

    def test_requirements(self):
        reqs = [r.strip().split("==")[0] for r in spec()["requirements"].split(",")]
        self.assertIn("sqlite3", reqs)
        self.assertIn("kivy", reqs)
        self.assertIn("certifi", reqs)  # HTTPS certificate store for DB updates

    def test_internet_permission(self):
        perms = [p.strip() for p in spec()["android.permissions"].split(",")]
        self.assertIn("INTERNET", perms)

    def test_kivy_recipe_override_is_wired(self):
        s = spec()
        self.assertEqual(s["p4a.local_recipes"], "./p4a-recipes")
        self.assertTrue(s["p4a.branch"].startswith("v"), "pin python-for-android to a release tag")
        self.assertIn("p4a-recipes", s["source.exclude_dirs"])

    def test_kivy_override_drops_requests(self):
        path = os.path.join(ROOT, "p4a-recipes", "kivy", "__init__.py")
        tree = ast.parse(open(path, encoding="utf-8").read())
        deps = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                    getattr(t, "id", None) == "python_depends" for t in node.targets):
                deps = ast.literal_eval(node.value)
        self.assertEqual(deps, ["filetype"])

    def test_pip_constraint_wired_into_ci(self):
        constraints = open(os.path.join(ROOT, "tools", "pip-constraints.txt")).read()
        self.assertIn("pip==25.3", constraints)
        wf = open(os.path.join(ROOT, ".github", "workflows", "build-apk.yml")).read()
        self.assertEqual(wf.count("PIP_CONSTRAINT: ${{ github.workspace }}/tools/pip-constraints.txt"), 2)


if __name__ == "__main__":
    unittest.main()
