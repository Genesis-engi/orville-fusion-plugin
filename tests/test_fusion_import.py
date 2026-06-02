from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "OrvilleFusionAddIn"))

from lib.fusion_import import reveal_imported_geometry


class FakeCollection:
    def __init__(self, items):
        self._items = list(items)

    @property
    def count(self):
        return len(self._items)

    def item(self, index):
        return self._items[index]


class FakeBody:
    def __init__(self):
        self.isLightBulbOn = False


class FakeOccurrence:
    def __init__(self, component):
        self.isLightBulbOn = False
        self.component = component


class FakeComponent:
    def __init__(self, bodies=None, occurrences=None):
        self.isBodiesFolderLightBulbOn = False
        self.bRepBodies = FakeCollection(bodies or [])
        self.occurrences = FakeCollection(occurrences or [])


class FakeViewport:
    def __init__(self):
        self.fit_called = False
        self.refresh_called = False

    def fit(self):
        self.fit_called = True
        return True

    def refresh(self):
        self.refresh_called = True
        return True


class FakeApp:
    def __init__(self):
        self.activeViewport = FakeViewport()


class FusionImportTests(unittest.TestCase):
    def test_reveal_imported_geometry_turns_on_new_imported_items(self):
        existing_body = FakeBody()
        imported_body = FakeBody()
        child_body = FakeBody()
        child_component = FakeComponent(bodies=[child_body])
        imported_occurrence = FakeOccurrence(child_component)
        root = FakeComponent(
            bodies=[existing_body, imported_body],
            occurrences=[imported_occurrence],
        )
        app = FakeApp()

        reveal_imported_geometry(app, root, previous_body_count=1, previous_occurrence_count=0)

        self.assertFalse(existing_body.isLightBulbOn)
        self.assertTrue(imported_body.isLightBulbOn)
        self.assertTrue(imported_occurrence.isLightBulbOn)
        self.assertTrue(root.isBodiesFolderLightBulbOn)
        self.assertTrue(child_component.isBodiesFolderLightBulbOn)
        self.assertTrue(child_body.isLightBulbOn)
        self.assertTrue(app.activeViewport.fit_called)
        self.assertTrue(app.activeViewport.refresh_called)


if __name__ == "__main__":
    unittest.main()
