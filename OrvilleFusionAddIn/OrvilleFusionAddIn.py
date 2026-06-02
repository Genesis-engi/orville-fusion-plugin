"""Autodesk Fusion entry point for the Orville add-in."""

from __future__ import annotations

import json
import importlib
import os
import queue
import sys
import traceback
from pathlib import Path
from typing import Any

ADDIN_DIR = Path(__file__).resolve().parent
if str(ADDIN_DIR) not in sys.path:
    sys.path.insert(0, str(ADDIN_DIR))

try:
    import adsk.core  # type: ignore
except ImportError:
    adsk = None  # type: ignore

import lib.api_client as _api_client
import lib.events as _events
import lib.fusion_import as _fusion_import
import lib.job_state as _job_state
import lib.secure_store as _secure_store

_api_client = importlib.reload(_api_client)
_events = importlib.reload(_events)
_fusion_import = importlib.reload(_fusion_import)
_job_state = importlib.reload(_job_state)
_secure_store = importlib.reload(_secure_store)

OrvilleClient = _api_client.OrvilleClient
validate_images = _api_client.validate_images
TaskRunner = _events.TaskRunner
FusionImportError = _fusion_import.FusionImportError
import_step_into_active_design = _fusion_import.import_step_into_active_design
StateStore = _job_state.StateStore
JobState = _job_state.JobState
SecureStore = _secure_store.SecureStore
SecureStoreUnavailable = _secure_store.SecureStoreUnavailable

COMMAND_ID = "OrvilleFusionPluginCommand"
COMMAND_NAME = "Orville"
COMMAND_DESCRIPTION = "Chat with Orville and import generated STEP files."
PALETTE_ID = "OrvilleFusionPluginPalette"
CUSTOM_EVENT_ID = "OrvilleFusionPluginWorkerEvent"
PANEL_ID = "SolidScriptsAddinsPanel"
PALETTE_WIDTH = 430
PALETTE_HEIGHT = 720

_app = None
_ui = None
_controller: "OrvilleController | None" = None
_handlers: list[Any] = []


def run(context: Any) -> None:
    if adsk is None:
        raise RuntimeError("This add-in must run inside Autodesk Fusion.")

    global _app, _ui, _controller
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        _controller = OrvilleController(_app, _ui)

        remove_toolbar_control(_ui)
        existing_command_def = _ui.commandDefinitions.itemById(COMMAND_ID)
        if existing_command_def:
            existing_command_def.deleteMe()

        command_def = _ui.commandDefinitions.addButtonDefinition(
            COMMAND_ID,
            COMMAND_NAME,
            COMMAND_DESCRIPTION,
            str(ADDIN_DIR / "resources"),
        )

        command_handler = OrvilleCommandCreatedHandler(_controller)
        command_def.commandCreated.add(command_handler)
        _handlers.append(command_handler)

        panel = _ui.allToolbarPanels.itemById(PANEL_ID)
        if panel and not panel.controls.itemById(COMMAND_ID):
            button_control = panel.controls.addCommand(command_def)
            button_control.isPromotedByDefault = True
            button_control.isPromoted = True

        try:
            _app.unregisterCustomEvent(CUSTOM_EVENT_ID)
        except Exception:
            pass
        worker_event = _app.registerCustomEvent(CUSTOM_EVENT_ID)
        worker_handler = OrvilleWorkerEventHandler(_controller)
        worker_event.add(worker_handler)
        _handlers.append(worker_handler)

        _controller.show_palette(raise_on_failure=False)
    except Exception:
        if _ui:
            _ui.messageBox("Orville failed to start:\n{}".format(traceback.format_exc()))


def stop(context: Any) -> None:
    if adsk is None:
        return

    global _controller
    if _controller:
        _controller.stop()

    app = adsk.core.Application.get()
    ui = app.userInterface

    remove_toolbar_control(ui)

    command_def = ui.commandDefinitions.itemById(COMMAND_ID)
    if command_def:
        command_def.deleteMe()

    palette = ui.palettes.itemById(PALETTE_ID)
    if palette:
        palette.deleteMe()

    try:
        app.unregisterCustomEvent(CUSTOM_EVENT_ID)
    except Exception:
        pass

    _handlers.clear()
    _controller = None


def remove_toolbar_control(ui: Any) -> None:
    panel = ui.allToolbarPanels.itemById(PANEL_ID)
    if panel:
        control = panel.controls.itemById(COMMAND_ID)
        if control:
            control.deleteMe()


def is_palette_area_error(exc: Exception) -> bool:
    text = f"{exc!r} {exc}"
    return "InternalValidationError" in text and "pArea" in text


class OrvilleController:
    def __init__(self, app: Any, ui: Any) -> None:
        self.app = app
        self.ui = ui
        self.secure_store = SecureStore()
        self.data_dir = user_data_dir()
        self.downloads_dir = self.data_dir / "downloads"
        self.state_store = StateStore(self.data_dir / "orville_job_state.json")
        self.state = JobState()
        self.state_store.clear()
        self.selected_images: list[str] = []
        self.event_queue: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self.task_runner = TaskRunner(self.event_queue, self.fire_worker_event)
        self.active_poll_job_id: str | None = None
        self.workflow_generation = 0
        self.palette_handlers_registered = False

    def stop(self) -> None:
        self.task_runner.stop()

    def fire_worker_event(self) -> None:
        try:
            self.app.fireCustomEvent(CUSTOM_EVENT_ID, "")
        except Exception:
            pass

    def show_palette(self, *, raise_on_failure: bool = True) -> None:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                palette = self.ensure_palette(recreate=attempt > 0)
                self.show_palette_object(palette)
                self.nudge_palette_repaint(palette)
                self.send_state()
                return
            except Exception as exc:
                last_error = exc
                if not is_palette_area_error(exc):
                    break
                self.delete_palette()

        if raise_on_failure and last_error:
            raise last_error

    def ensure_palette(self, *, recreate: bool = False) -> Any:
        if recreate:
            self.delete_palette()

        palette = self.ui.palettes.itemById(PALETTE_ID)
        if palette and not self.palette_handlers_registered:
            self.delete_palette()
            palette = None
        if palette:
            return palette

        html_file = (ADDIN_DIR / "ui" / "index.html").resolve().as_uri()
        palette = self.ui.palettes.add(
            PALETTE_ID,
            "Orville",
            html_file,
            False,
            True,
            True,
            PALETTE_WIDTH,
            PALETTE_HEIGHT,
            True,
        )
        if not palette:
            raise RuntimeError("Fusion did not create the Orville palette.")

        incoming_handler = OrvilleHtmlEventHandler(self)
        palette.incomingFromHTML.add(incoming_handler)
        _handlers.append(incoming_handler)

        closed_handler = OrvillePaletteClosedHandler()
        palette.closed.add(closed_handler)
        _handlers.append(closed_handler)

        self.palette_handlers_registered = True
        return palette

    def show_palette_object(self, palette: Any) -> None:
        if hasattr(adsk, "doEvents"):
            try:
                adsk.doEvents()
            except Exception:
                pass
        palette.isVisible = True

    def delete_palette(self) -> None:
        palette = self.ui.palettes.itemById(PALETTE_ID)
        self.palette_handlers_registered = False
        if palette:
            try:
                palette.deleteMe()
            except Exception:
                pass

    def nudge_palette_repaint(self, palette: Any) -> None:
        try:
            if hasattr(adsk, "doEvents"):
                adsk.doEvents()
        except Exception:
            pass

        try:
            width = palette.width
            height = palette.height
            if width and height:
                palette.width = width + 1
                palette.height = height + 1
                try:
                    if hasattr(adsk, "doEvents"):
                        adsk.doEvents()
                except Exception:
                    pass
                palette.width = width
                palette.height = height
        except Exception:
            pass

    def handle_html_event(self, action: str, data: str | None) -> dict[str, Any]:
        if action == "response":
            return {"ok": True}

        payload = parse_payload(data)
        try:
            if action == "ready":
                self.new_job()
            elif action == "save_api_key":
                self.secure_store.set_api_key(payload.get("api_key", ""))
                self.send_notification("API key saved.")
                self.send_state()
                self.refresh_recent_jobs()
            elif action == "delete_api_key":
                self.secure_store.delete_api_key()
                self.send_notification("API key deleted.")
                self.send_state()
                self.send_to_palette("recent_jobs", {"jobs": [], "next_cursor": None})
            elif action == "select_images":
                self.select_images()
            elif action == "clear_images":
                self.selected_images = []
                self.send_state()
            elif action == "new_job":
                self.new_job()
            elif action == "submit_prompt":
                self.submit_prompt(payload.get("prompt", ""), mode=payload.get("mode", "iterate"))
            elif action == "refresh_job":
                self.refresh_job()
            elif action == "refresh_recent_jobs":
                self.refresh_recent_jobs(query=payload.get("query", ""))
            elif action == "load_recent_job":
                self.load_recent_job(payload.get("job_id", ""))
            elif action == "download_artifact":
                self.download_artifact(payload.get("artifact_id", ""))
            elif action == "import_artifact":
                self.import_artifact(payload.get("artifact_id", ""))
            elif action == "download_import_artifact":
                self.download_and_import_artifact(payload.get("artifact_id", ""))
            else:
                self.send_error(f"Unknown action: {action}")
        except (ValueError, SecureStoreUnavailable, FusionImportError) as exc:
            self.send_error(str(exc))
        return {"ok": True}

    def select_images(self) -> None:
        dialog = self.ui.createFileDialog()
        dialog.title = "Attach reference images"
        dialog.isMultiSelectEnabled = True
        dialog.filter = "Image files (*.png;*.jpg;*.jpeg;*.webp;*.gif;*.heic;*.heif)"
        result = dialog.showOpen()
        if result != adsk.core.DialogResults.DialogOK:
            return

        filenames = list(dialog.filenames)
        validate_images(filenames)
        self.selected_images = filenames
        self.send_state()

    def submit_prompt(self, prompt: str, *, mode: str) -> None:
        prompt = (prompt or "").strip()
        if not prompt:
            raise ValueError("Enter a prompt first.")
        if self.state.status in {"queued", "running"}:
            raise ValueError("Wait for the active job to finish before sending another request.")

        images = list(self.selected_images)
        validate_images(images)

        if mode == "review":
            if not self.state.current_job_id or self.state.status != "completed":
                raise ValueError("Review requires a completed Orville job.")
            if images:
                raise ValueError("Review mode does not support attached images yet.")
            job_id = self.state.current_job_id or ""
            revision_id = self.state.latest_revision_id
            self.send_status("Reviewing result...")
            self.submit_workflow_task(
                "review_completed",
                lambda: self.client().review_job(job_id, prompt, revision_id=revision_id),
            )
        elif self.state.current_job_id:
            job_id = self.state.current_job_id
            self.send_status("Sending iteration...")
            self.submit_workflow_task(
                "followup_sent",
                lambda: self.client().send_followup(job_id, prompt, image_paths=images),
            )
        else:
            self.send_status("Creating CAD job...")
            self.submit_workflow_task(
                "job_created",
                lambda: self.client().create_job(prompt, image_paths=images),
            )

    def new_job(self) -> None:
        self.workflow_generation += 1
        self.active_poll_job_id = None
        self.selected_images = []
        self.state = JobState()
        self.state_store.clear()
        self.send_to_palette("conversation_cleared", {})
        self.send_state()

    def refresh_job(self) -> None:
        if not self.state.current_job_id:
            raise ValueError("No job to refresh.")
        job_id = self.state.current_job_id
        self.submit_workflow_task("job_status", lambda: self.client().get_job(job_id))

    def refresh_recent_jobs(self, *, query: str = "", silent: bool = False) -> None:
        if not self.api_key_present():
            if not silent:
                raise ValueError("Save an API key before loading recent jobs.")
            return
        self.send_status("Loading recent jobs...")
        self.task_runner.submit(
            "recent_jobs_loaded",
            lambda: self.client().list_jobs(limit=20, query=(query or "").strip() or None),
        )

    def load_recent_job(self, job_id: str) -> None:
        job_id = (job_id or "").strip()
        if not job_id:
            raise ValueError("Select a recent job first.")
        self.workflow_generation += 1
        self.active_poll_job_id = None
        self.send_status("Loading job history...")

        def worker() -> dict[str, Any]:
            client = self.client()
            job = client.get_job(job_id)
            messages = client.list_messages(job_id).get("messages") or []
            return {"job": job, "messages": messages}

        self.submit_workflow_task("recent_job_loaded", worker)

    def download_artifact(self, artifact_id: str) -> None:
        artifact = self.find_artifact(artifact_id)
        if not artifact:
            raise ValueError("Artifact not found.")
        filename = artifact.get("filename") or f"{artifact_id}.step"
        self.send_status(f"Downloading {filename}...")
        self.submit_workflow_task(
            "artifact_downloaded",
            lambda: {
                "artifact_id": artifact_id,
                "filename": filename,
                "path": str(self.client().download_artifact(artifact_id, self.downloads_dir, filename=filename)),
            },
        )

    def import_artifact(self, artifact_id: str) -> None:
        record = self.state.downloads.get(artifact_id)
        if not record:
            raise ValueError("Download the STEP artifact before importing it.")
        import_step_into_active_design(self.app, record.path)
        self.send_notification(f"Imported {record.filename}.")

    def download_and_import_artifact(self, artifact_id: str) -> None:
        artifact_id = (artifact_id or "").strip()
        record = self.state.downloads.get(artifact_id)
        if record:
            import_step_into_active_design(self.app, record.path)
            self.send_notification(f"Imported {record.filename}.")
            return

        artifact = self.find_artifact(artifact_id)
        if not artifact:
            raise ValueError("Artifact not found.")
        filename = artifact.get("filename") or f"{artifact_id}.step"
        self.send_status(f"Downloading and importing {filename}...")
        self.submit_workflow_task(
            "artifact_downloaded_for_import",
            lambda: {
                "artifact_id": artifact_id,
                "filename": filename,
                "path": str(self.client().download_artifact(artifact_id, self.downloads_dir, filename=filename)),
            },
        )

    def drain_worker_events(self) -> None:
        while True:
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                break
            self.handle_worker_event(event)

    def handle_worker_event(self, event: dict[str, Any]) -> None:
        event_name = event.get("event")
        payload = event.get("payload") or {}
        if isinstance(payload, dict):
            payload = dict(payload)
            generation = payload.pop("_workflow_generation", None)
            if generation is not None and generation != self.workflow_generation:
                return

        if event_name in {"job_created", "followup_sent", "job_status"}:
            if event_name in {"followup_sent", "job_status"} and not self.should_accept_job_update(event_name, payload):
                return
            previous_status = self.state.status
            self.state.apply_job_response(payload)
            self.state_store.save(self.state)
            self.selected_images = []
            self.send_job(payload)
            self.send_state()
            if event_name in {"job_created", "followup_sent"} and payload.get("id"):
                self.start_polling(payload["id"])
            if previous_status != "completed" and payload.get("status") == "completed":
                self.send_notification("Orville job completed.")
            elif previous_status != "failed" and payload.get("status") == "failed":
                self.send_error("Orville job failed.", payload)
        elif event_name == "artifact_downloaded":
            if not self.find_artifact(payload.get("artifact_id", "")):
                return
            self.state.record_download(payload["artifact_id"], payload["filename"], payload["path"])
            self.state_store.save(self.state)
            self.send_notification(f"Downloaded {payload['filename']}.")
            self.send_state()
        elif event_name == "artifact_downloaded_for_import":
            if not self.find_artifact(payload.get("artifact_id", "")):
                return
            self.state.record_download(payload["artifact_id"], payload["filename"], payload["path"])
            self.state_store.save(self.state)
            try:
                import_step_into_active_design(self.app, payload["path"])
                self.send_notification(f"Imported {payload['filename']}.")
            except FusionImportError as exc:
                self.send_error(str(exc))
            self.send_state()
        elif event_name == "review_completed":
            job_id = payload.get("job_id")
            if job_id and job_id != self.state.current_job_id:
                return
            self.state.current_job_id = payload.get("job_id") or self.state.current_job_id
            self.state.latest_revision_id = payload.get("revision_id") or self.state.latest_revision_id
            self.state.request_id = payload.get("request_id") or self.state.request_id
            self.state_store.save(self.state)
            self.send_to_palette("review", payload)
            self.send_state()
        elif event_name == "recent_jobs_loaded":
            self.send_to_palette("recent_jobs", payload)
        elif event_name == "recent_job_loaded":
            job = payload.get("job") or {}
            self.state.apply_job_response(job)
            self.state_store.save(self.state)
            self.selected_images = []
            self.send_to_palette("recent_job_loaded", payload)
            self.send_state()
        elif event_name == "task_error":
            details = payload.get("details") if isinstance(payload, dict) else None
            message = payload.get("message", "Background task failed.") if isinstance(payload, dict) else "Background task failed."
            self.send_error(message, details)
        else:
            self.send_error(f"Unknown worker event: {event_name}")

    def submit_workflow_task(self, event_name: str, fn: Any) -> None:
        generation = self.workflow_generation

        def worker() -> Any:
            result = fn()
            if isinstance(result, dict):
                result = dict(result)
                result["_workflow_generation"] = generation
            return result

        self.task_runner.submit(event_name, worker)

    def should_accept_job_update(self, event_name: str, payload: dict[str, Any]) -> bool:
        job_id = payload.get("id")
        if not job_id:
            return True
        if self.state.current_job_id:
            return job_id == self.state.current_job_id
        if event_name == "job_status":
            return self.active_poll_job_id == job_id
        return False

    def start_polling(self, job_id: str) -> None:
        self.active_poll_job_id = job_id
        generation = self.workflow_generation

        def on_update(job: dict[str, Any]) -> None:
            payload = dict(job)
            payload["_workflow_generation"] = generation
            self.event_queue.put({"event": "job_status", "payload": payload})
            self.fire_worker_event()

        self.submit_workflow_task(
            "job_status",
            lambda: self.client().poll_until_terminal(
                job_id,
                on_update=on_update,
                stop=lambda: self.task_runner.stop_event.is_set() or self.active_poll_job_id != job_id,
            ),
        )

    def client(self) -> OrvilleClient:
        return OrvilleClient(self.secure_store.get_api_key() or "")

    def find_artifact(self, artifact_id: str) -> dict[str, Any] | None:
        for artifact in self.state.artifacts:
            if artifact.get("id") == artifact_id:
                return artifact
        return None

    def send_state(self) -> None:
        self.send_to_palette(
            "state",
            {
                "api_key_present": self.api_key_present(),
                "selected_images": [Path(path).name for path in self.selected_images],
                "job_state": self.state.to_dict(),
            },
        )

    def send_job(self, job: dict[str, Any]) -> None:
        self.send_to_palette("job", job)

    def send_status(self, message: str) -> None:
        self.send_to_palette("status", {"message": message})

    def send_notification(self, message: str) -> None:
        self.send_to_palette("notification", {"message": message})

    def send_error(self, message: str, details: Any | None = None) -> None:
        self.send_to_palette("error", {"message": message, "details": details})

    def send_to_palette(self, action: str, payload: dict[str, Any]) -> None:
        palette = self.ui.palettes.itemById(PALETTE_ID)
        if not palette:
            return
        try:
            palette.sendInfoToHTML(action, json.dumps(payload))
        except Exception:
            pass

    def api_key_present(self) -> bool:
        try:
            return bool(self.secure_store.get_api_key())
        except (SecureStoreUnavailable, ValueError):
            return False


def user_data_dir() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", Path.home()))
        return root / "OrvilleFusionPlugin"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "OrvilleFusionPlugin"
    return Path.home() / ".orville-fusion-plugin"


def parse_payload(data: str | None) -> dict[str, Any]:
    if not data:
        return {}
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


if adsk is not None:

    class OrvilleCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):  # type: ignore[name-defined]
        def __init__(self, controller: OrvilleController) -> None:
            super().__init__()
            self.controller = controller

        def notify(self, args: Any) -> None:
            try:
                self.controller.show_palette()
            except Exception:
                self.controller.ui.messageBox("Orville palette failed to open:\n{}".format(traceback.format_exc()))


    class OrvilleHtmlEventHandler(adsk.core.HTMLEventHandler):  # type: ignore[name-defined]
        def __init__(self, controller: OrvilleController) -> None:
            super().__init__()
            self.controller = controller

        def notify(self, args: Any) -> None:
            result = self.controller.handle_html_event(args.action, args.data)
            args.returnData = json.dumps(result)


    class OrvilleWorkerEventHandler(adsk.core.CustomEventHandler):  # type: ignore[name-defined]
        def __init__(self, controller: OrvilleController) -> None:
            super().__init__()
            self.controller = controller

        def notify(self, args: Any) -> None:
            self.controller.drain_worker_events()


    class OrvillePaletteClosedHandler(adsk.core.UserInterfaceGeneralEventHandler):  # type: ignore[name-defined]
        def __init__(self) -> None:
            super().__init__()

        def notify(self, args: Any) -> None:
            pass
