# Orville Fusion Plugin Implementation Plan

Date: 2026-05-21

## Scope

Build an open-source Autodesk Fusion desktop add-in that exposes Orville as an in-product chat workflow. The add-in must let a user enter prompts, attach reference images, create and iterate CAD jobs through the Orville API, show job status, download STEP artifacts, and import a selected STEP file into the active Fusion design.

Source spec: `../../CAD_plugin_spec.md` from the GENESIS workspace.

## Verified Source Baseline

Autodesk Fusion API docs checked on 2026-05-21:

- Fusion API User's Manual: https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/UserManualIndex_UM.htm
- Creating scripts and add-ins, add-in folders, manifest JSON, startup loading, and install/link behavior: https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/WritingDebugging_UM.htm
- Manual add-in install locations: https://help.autodesk.com/view/fusion360/ENU/?caas=caas%2Fsfdcarticles%2Fsfdcarticles%2FHow-to-install-an-ADD-IN-and-Script-in-Fusion-360.html
- Palettes and browser command inputs, including HTML-to-add-in event communication and the constraint that JavaScript cannot call the Fusion API directly: https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Palettes_UM.htm
- File picker support through `UserInterface.createFileDialog` and `FileDialog.filenames`: https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/UserInterface_createFileDialog.htm and https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/FileDialog_filenames.htm
- Worker-thread handoff through custom events: https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Application_registerCustomEvent.htm
- STEP import options: https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/STEPImportOptions.htm
- Import into an existing design/component with `ImportManager.importToTarget`: https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/ImportManager_importToTarget.htm

Orville API docs checked on 2026-05-21:

- Human docs: https://www.ballistalabs.ai/docs/api
- Machine contract: https://www.ballistalabs.ai/api/v1/openapi.json
- Verified OpenAPI `info.version`: `2026-05-21`
- Verified paths:
  - `POST /api/v1/cad/jobs`
  - `GET /api/v1/cad/jobs/{jobId}`
  - `GET /api/v1/cad/jobs/{jobId}/messages`
  - `POST /api/v1/cad/jobs/{jobId}/messages`
  - `GET /api/v1/cad/jobs/{jobId}/artifacts`
  - `GET /api/v1/artifacts/{artifactId}/download`
  - `GET /api/v1/billing/balance`

## Architecture Decision

Use a Python Fusion add-in, not Autodesk Platform Services Automation API TypeScript.

Reason: the requested product is an in-Fusion UI that imports generated STEP files into the user's current workspace/design. Autodesk's desktop add-in docs support Python and C++ add-ins, palettes, file dialogs, custom events, and direct import into the active design. The Automation API is useful for cloud automation, but it is not the right primary surface for a local in-product chat panel.

## Repository Shape

Planned layout:

```text
orville-fusion-plugin/
  OrvilleFusionAddIn/
    OrvilleFusionAddIn.py
    OrvilleFusionAddIn.manifest
    lib/
      api_client.py
      secure_store.py
      job_state.py
      fusion_import.py
      events.py
    ui/
      index.html
      app.js
      styles.css
    resources/
      AddInIcon.svg
  tests/
    test_api_client.py
    test_secure_store.py
    test_job_state.py
  docs/
    FUSION_IMPLEMENTATION_PLAN.md
  README.md
  LICENSE
  CONTRIBUTING.md
```

The add-in folder and main Python/manifest names must match Fusion's add-in expectations. Keep icons and UI files inside the add-in folder so manual install is a single folder copy.

## Fusion Add-In Plan

1. Create `OrvilleFusionAddIn.manifest`.
   - `autodeskProduct`: `Fusion`
   - `type`: `addin`
   - `runOnStartup`: `true`
   - `supportedOS`: `windows|mac`
   - include an icon file if available

2. Add a toolbar command.
   - Register command definitions in `run(context)`.
   - Add a visible "Orville" command under the ADD-INS surface.
   - Command opens or focuses the palette.
   - Cleanly remove controls, handlers, palettes, and custom events in `stop(context)`.

3. Build the palette UI.
   - HTML/CSS/JS chat surface with prompt box, submit button, attach-images button, settings button, status area, artifact list, and import button.
   - Palette JavaScript sends actions to Python with `adsk.fusionSendData`.
   - Python sends job status, messages, selected image names, and artifact metadata back with `sendInfoToHTML`.
   - The palette must not store or display the API key after entry.

4. Handle image attachment with Fusion's native file dialog.
   - The palette asks Python to open a file picker.
   - Python uses `ui.createFileDialog()`.
   - Enable multi-select and filter to JPEG, PNG, WebP, GIF, HEIC, and HEIF.
   - Store only local file paths in in-memory state for the pending request.
   - Enforce Orville limits before request: maximum 5 images and 10 MB per image.

5. Store the API key securely.
   - Do not store the key in JavaScript, localStorage, the manifest, plain JSON, or git-tracked files.
   - Implement `secure_store.py` with OS-backed storage:
     - Windows: Credential Manager via WinCred APIs through `ctypes`.
     - macOS: Keychain via the `/usr/bin/security` command.
   - Provide environment-variable override only for development, e.g. `ORVILLE_API_KEY`.
   - Store non-secret job state separately as JSON under the user's add-in data directory.

6. Implement Orville API client.
   - Base URL default: `https://www.ballistalabs.ai`.
   - Send `Authorization: Bearer <api key>`.
   - Use JSON for prompt-only create/follow-up requests.
   - Use multipart form data with repeated field name `images` when attachments exist.
   - Send a new `Idempotency-Key` on every create/follow-up, reusing only for exact retries.
   - Respect `poll_after_seconds` and `Retry-After`.
   - Preserve `request_id` in local logs and UI error details.

7. Poll jobs without blocking Fusion.
   - Run HTTP polling on a background thread.
   - Use `Application.registerCustomEvent` to marshal UI/Fusion updates back to the main thread.
   - Never call Fusion API objects directly from worker threads.
   - Stop polling when status becomes `completed` or `failed`.

8. Display completion and artifacts.
   - On `completed`, show assistant explanation, cost if present, revision ID, and STEP artifacts.
   - On `failed`, show error code/message and request ID if available.
   - Keep the import button disabled until at least one STEP artifact is downloaded or downloadable.

9. Download STEP artifacts.
   - Prefer `GET /api/v1/artifacts/{artifactId}/download?redirect=false` to obtain a signed URL and filename.
   - Download the STEP to a local add-in downloads directory.
   - Sanitize filenames and avoid overwriting unless explicitly confirmed.
   - Treat signed URLs as sensitive ephemeral data and do not log them.

10. Import into active Fusion design.
   - Require an active design and root component.
   - Create `STEPImportOptions` with `ImportManager.createSTEPImportOptions`.
   - Use `ImportManager.importToTarget(importOptions, targetComponent)` to insert into the active design/root component.
   - Avoid calling `importToTarget` from command-related event handlers because Autodesk documents a limitation there. Route import through the palette/custom-event main-thread path.
   - Set `isViewFit` intentionally, probably `true` for first release so the user can immediately see the imported model.

## Open-Source Release Plan

1. Add the scaffolded Fusion add-in folder and manifest.
2. Add pure Python modules for the API client, secure storage, local state, and import orchestration.
3. Add unit tests for all modules that can run outside Fusion.
4. Add manual Fusion verification checklist.
5. Add screenshots or short GIFs only after the UI exists.
6. Add release packaging instructions:
   - Windows add-in directory: `%appdata%\Autodesk\Autodesk Fusion\API\AddIns`
   - macOS add-in directory: `~/Library/Application Support/Autodesk/Autodesk Fusion/API/AddIns`
   - Alternative: link local repo folder from Fusion's Scripts and Add-Ins dialog during development.

## Manual Acceptance Checklist

- Fresh install appears in Fusion's Scripts and Add-Ins dialog.
- Add-in can run on startup and be stopped without leaving orphan toolbar controls.
- Orville palette opens from the ADD-INS toolbar command.
- API key can be saved, retrieved, and deleted from OS secure storage.
- Prompt-only job creates successfully with a unique idempotency key.
- Image-backed job creates successfully with up to 5 allowed image files.
- Polling follows `poll_after_seconds` and does not freeze Fusion.
- Completed job shows explanation, cost if present, revision ID, and STEP artifacts.
- Follow-up iteration is blocked while a job is active and works after completion/failure.
- STEP artifact downloads to local add-in cache.
- Import inserts the STEP into the active Fusion design/root component.
- Failed API calls surface actionable status, error code, message, and request ID.

## Initial Risks

- Fusion's embedded Python environment may constrain third-party packages, so the first implementation should use the Python standard library for HTTP multipart, secure storage bindings, and tests unless packaging proves reliable.
- Passing large images through palette JavaScript would be fragile. Use Fusion's native file dialog and Python-side multipart upload instead.
- STEP import should not run inside command event handlers because Autodesk documents a limitation for `importToTarget`; use the palette/custom-event path.
- API keys must never enter palette localStorage or local job state.
