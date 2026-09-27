# MTAR-V2

Separate V2 workspace for the Mold Testing and Removal report automation project.

The original `/mnt/data/app.py` is not modified.

## Sprint RG-1

This version restructures the app around one reusable job record:

- client/property information
- inspection areas
- samples linked to areas
- photos linked to stable area IDs
- lab result rows linked to samples
- consultant-selected overall report outcome
- DOCX generation using the existing report appearance and language

The V2 structure is intentionally designed so later sprints can automate PRO-LAB parsing, multi-photo layout, and final QA without re-entering the same job data.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Folder layout

- `app.py` — Streamlit V2 UI
- `models.py` — job/area/sample state model
- `report_builder.py` — DOCX generation
- `assets/` — logo and signature images

## Next Sprint

RG-2 will replace manual lab entry with a PRO-LAB parser that reads actual sample-table data rather than searching the full PDF for keywords.
