# MTAR-V2

V2 workspace for Mold Testing and Removal report automation.

## RG-2 review-fixes branch

This branch refines the report review workflow based on real testing.

### Updated workflow

1. Upload the PRO-LAB Certificate of Mold Analysis.
2. MTAR imports supported lab data.
3. Inspection Areas are created manually and remain separate from lab samples.
4. Each indoor or surface sample is manually assigned to an Inspection Area.
5. Indoor RH is blank and required.
6. Visual observations, moisture findings, area findings, and the final professional conclusion are reviewed in Streamlit.
7. Property and area photos are added.
8. The Current Draft is regenerated from the latest review values.
9. The final DOCX is generated only after validation and consultant approval.

### Current fixes

- Lab sample names are visible in Review Report.
- Samples and Inspection Areas are separate entities.
- Inspection Areas can be added, renamed, edited, and removed.
- Samples can be assigned to areas manually.
- Surface samples have a review section when present.
- Client phone/email fields were removed from the report-review UI.
- Indoor RH is required and starts blank.
- Draft generation uses the current selected report outcome, preventing stale conclusion text.
- Visual Observation and Moisture Assessment edits flow into the current draft.
- Property photos use fresh in-memory image streams and are included in regenerated drafts/final reports.
- Air results are shown side by side by sample in Streamlit and in the DOCX.
- The Surface Sample Results section is omitted when no surface samples exist.
- The report introduction only mentions sample types actually present.

### Surface-sample note

Surface sample entities, assignment, PRO-LAB determination review, and report output are implemented. Detailed organism extraction for every possible PRO-LAB surface-report layout still needs validation against a real surface/swab certificate before it should be considered complete.

## Run locally

```powershell
git checkout rg-2-review-fixes
git pull
py -m pip install -r requirements.txt
py -m streamlit run app.py
```
