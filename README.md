# MTAR-V2

V2 workspace for Mold Testing and Removal report automation.

## Current workflow — RG-2

The report workflow is now designed around the PRO-LAB certificate:

1. Upload the PRO-LAB Certificate of Mold Analysis.
2. MTAR parses supported data from the structured result table.
3. MTAR automatically creates a **review-required draft DOCX**.
4. The consultant reviews and completes information the lab report cannot provide.
5. Photos can be added.
6. The consultant explicitly approves the findings and generates the final DOCX.

### Automatically imported from PRO-LAB when available

- project/client name
- property/test location
- PRO-LAB report number
- report date
- sample collection date
- COC / line number
- sample location
- sample type
- volume
- serial number
- PRO-LAB determination
- fungal types
- spores/m³
- total spores

### Intentionally left for consultant review

The application does not invent inspection facts that are absent from the laboratory certificate. These remain review fields:

- exact affected-area name when the lab only says "INDOORS"
- visual observations
- moisture readings
- inspection-area finding
- indoor RH when not supplied
- final professional conclusion
- remediation/no-remediation decision

A new job defaults to **Pending consultant review**. A draft report shows **DRAFT - CONSULTANT REVIEW REQUIRED** and withholds final recommendations until the licensed consultant completes review.

## Files

- `app.py` — Streamlit upload → draft → review → final workflow
- `models.py` — job/area/sample data model and final validation
- `prolab_parser.py` — structured PRO-LAB parser and automatic draft-job builder
- `report_builder.py` — DOCX generator with draft/final behavior
- `assets/` — MTAR logo and signature assets

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

On Windows, if `streamlit` is not on PATH:

```powershell
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

## Next sprint

RG-3 will focus on multi-photo upload, photo categories, and automatic photo layout in the generated report.
