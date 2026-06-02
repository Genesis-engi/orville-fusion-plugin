"""Fusion-specific STEP import helpers."""

from __future__ import annotations

from pathlib import Path


class FusionImportError(RuntimeError):
    """Raised when a STEP artifact cannot be imported into Fusion."""


def import_step_into_active_design(app, step_path: str | Path) -> bool:
    """Import a STEP file into the active Fusion design root component."""

    try:
        import adsk.fusion  # type: ignore
    except ImportError as exc:
        raise FusionImportError("Fusion API is not available outside Autodesk Fusion.") from exc

    path = Path(step_path)
    if not path.exists():
        raise FusionImportError(f"STEP file does not exist: {path}")
    if path.suffix.lower() not in {".step", ".stp"}:
        raise FusionImportError(f"Expected a STEP file, got: {path.name}")

    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        raise FusionImportError("Open or create a Fusion design before importing STEP files.")

    root = design.rootComponent
    body_count = collection_count(root.bRepBodies)
    occurrence_count = collection_count(root.occurrences)

    import_manager = app.importManager
    options = import_manager.createSTEPImportOptions(str(path))
    options.isViewFit = True
    ok = import_manager.importToTarget(options, root)
    if not ok:
        raise FusionImportError("Fusion reported that STEP import failed.")

    reveal_imported_geometry(app, root, body_count, occurrence_count)
    return True


def collection_count(collection) -> int:
    try:
        return int(collection.count)
    except Exception:
        return 0


def set_light_bulb_on(target) -> None:
    try:
        if hasattr(target, "isLightBulbOn"):
            target.isLightBulbOn = True
    except Exception:
        pass


def set_bodies_folder_on(component) -> None:
    try:
        if hasattr(component, "isBodiesFolderLightBulbOn"):
            component.isBodiesFolderLightBulbOn = True
    except Exception:
        pass


def reveal_imported_geometry(app, root_component, previous_body_count: int, previous_occurrence_count: int) -> None:
    """Turn on imported bodies/components and force Fusion to redraw them."""

    set_bodies_folder_on(root_component)

    for index in range(previous_body_count, collection_count(root_component.bRepBodies)):
        body = root_component.bRepBodies.item(index)
        set_light_bulb_on(body)

    for index in range(previous_occurrence_count, collection_count(root_component.occurrences)):
        occurrence = root_component.occurrences.item(index)
        reveal_occurrence(occurrence)

    try:
        viewport = app.activeViewport
        if viewport:
            viewport.fit()
            viewport.refresh()
    except Exception:
        pass


def reveal_occurrence(occurrence) -> None:
    set_light_bulb_on(occurrence)

    try:
        component = occurrence.component
    except Exception:
        component = None
    if not component:
        return

    set_bodies_folder_on(component)
    for index in range(collection_count(component.bRepBodies)):
        set_light_bulb_on(component.bRepBodies.item(index))
    for index in range(collection_count(component.occurrences)):
        reveal_occurrence(component.occurrences.item(index))
