# MTAR-V2

Separate V2 workspace for the Mold Testing and Removal report automation project.

The original production report generator is not modified by this repository.

## Sprint RG-1 — Structured job record

RG-1 rebuilt the app around one reusable job record:

- client/property information
- inspection areas
- samples linked to areas
- photos linked to stable area IDs
- lab result rows linked to samples
- consultant-selected overall report outcome
- DOCX generation using the existing report appearance and language

## Sprint RG-2 — PRO-LAB import

RG-2 adds a reviewed PRO-LAB PDF import workflow:

- reads report metadata such as project name and PRO-LAB report number
- reads populated sample columns from the structured result table
- extracts COC/line number, sample location, sample type, volume, serial number, dates, and PRO-LAB determination
- extracts air-sample fungal types, spores/m³, and total spores from the result table
- ignores narrative definition text and mold reference pages when determining findings
- suggests mappings from PRO-LAB samples to the existing V2 job samples
- requires the consultant to review those mappings before importing
- keeps all imported rows editable after import
- does **not** decide the professional report outcome or whether remediation is required

The parser is in `prolab_parser.py`.

## Current safety rule

The application treats the PRO-LAB report as source data. Parsed numbers and laboratory determinations can be imported automatically, but the licensed consultant still reviews the data and selects the final report outcome.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Folder layout

- `app.py` — Streamlit V2 UI
- `models.py` — job/area/sample state model
- `prolab_parser.py` — structured PRO-LAB PDF parser and reviewed import mapping
- `report_builder.py` — DOCX generation
- `assets/` — logo and signature images

## Next report-automation sprint

RG-3 will focus on multi-photo upload, photo categories, and automatic photo layout in the generated report.
