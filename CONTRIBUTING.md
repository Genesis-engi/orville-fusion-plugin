# Contributing

## Development Principles

- Keep the add-in self-contained so users can install it by copying the add-in folder into Fusion's AddIns directory.
- Do not commit API keys, signed artifact URLs, generated STEP downloads, or local job state.
- Keep Fusion API calls in Fusion-facing modules and keep API/client logic separately testable outside Fusion.
- Prefer standard-library Python unless Fusion packaging constraints are explicitly solved.

## Local Verification

Early work should include normal Python tests for modules that do not require Fusion:

```bash
python -m unittest discover -s tests
```

Fusion integration behavior must also be manually verified in Autodesk Fusion because the `adsk` runtime is supplied by Fusion.
