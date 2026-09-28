from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import streamlit as st

from models import new_job_state, sample_location, validate_job
from prolab_parser import build_draft_job_from_prolab, parse_prolab_pdf
from report_builder import MOLD_DESCRIPTIONS, create_report

BASE_DIR = Path(__file__).resolve().parent

st.set_page_config(
    page_title="MTAR V2 - Mold Assessment Report",
    page_icon="🦠",
    layout="wide",
)

st.markdown(
    """
<style>
    .main-header {font-size: 2.35rem; color: #184058; text-align: center; margin-bottom: 0.25rem;}
    .sub-header {font-size: 1.05rem; color: #666; text-align: center; margin-bottom: 1.5rem;}
    .section-header {font-size: 1.25rem; color: #184058; border-bottom: 2px solid #184058; padding-bottom: 0.35rem; margin-top: 1rem;}
    .review-note {background: #fff8e8; border-left: 4px solid #d69e2e; padding: 0.8rem 1rem; border-radius: 4px; margin-bottom: 1rem;}
    .success-note {background: #eef8f2; border-left: 4px solid #2f855a; padding: 0.8rem 1rem; border-radius: 4px; margin-bottom: 1rem;}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown('<h1 class="main-header">MTAR V2 — Mold Assessment Report</h1>', unsafe_allow_html=True)
st.markdown(
    '<p class="sub-header">Upload PRO-LAB → automatic draft → consultant review → final report</p>',
    unsafe_allow_html=True,
)

if "job" not in st.session_state:
    st.session_state.job = new_job_state()
if "draft_docx" not in st.session_state:
    st.session_state.draft_docx = None
if "final_docx" not in st.session_state:
    st.session_state.final_docx = None
if "parsed_lab" not in st.session_state:
    st.session_state.parsed_lab = None
if "lab_pdf_bytes" not in st.session_state:
    st.session_state.lab_pdf_bytes = None
if "lab_pdf_hash" not in st.session_state:
    st.session_state.lab_pdf_hash = None

job = st.session_state.job


def sample_label(sample: dict) -> str:
    if sample.get("outdoor_control"):
        return "Outdoor Control"
    return sample_location(sample, job.get("areas", []))


def collect_photos() -> dict:
    photos = {}
    property_photo = st.session_state.get("photo_property")
    if property_photo:
        photos["property"] = property_photo
    for area in job.get("areas", []):
        upload = st.session_state.get(f"photo_{area['id']}")
        if upload:
            photos[area["id"]] = upload
    return photos


def build_report_bytes() -> bytes:
    report_job = copy.deepcopy(job)
    output = create_report(
        report_job,
        collect_photos(),
        st.session_state.get("lab_pdf_bytes"),
    )
    return output.getvalue()


def build_draft():
    st.session_state.draft_docx = build_report_bytes()
    st.session_state.final_docx = None


def reset_job():
    preserved = {"job": new_job_state()}
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.session_state.update(preserved)
    st.rerun()


def final_review_issues() -> list[str]:
    issues = validate_job(job, lab_pdf_present=st.session_state.get("lab_pdf_bytes") is not None)
    if any(a.get("finding") == "Needs consultant review" for a in job.get("areas", [])):
        issues.append("Review every inspection-area finding")
    return issues


tab1, tab2, tab3, tab4 = st.tabs(
    [
        "1. Upload & Draft",
        "2. Review Report",
        "3. Photos",
        "4. Lab Details",
    ]
)

with tab1:
    st.markdown('<p class="section-header">Upload PRO-LAB Certificate</p>', unsafe_allow_html=True)
    st.write(
        "Upload the laboratory report first. MTAR will extract the supported lab data, "
        "create the initial job record, and generate a draft report automatically."
    )

    lab_pdf = st.file_uploader(
        "PRO-LAB Certificate of Mold Analysis (PDF)",
        type=["pdf"],
        key="lab_pdf_upload",
    )

    if lab_pdf is not None:
        pdf_bytes = lab_pdf.getvalue()
        pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()

        if pdf_hash != st.session_state.get("lab_pdf_hash"):
            with st.spinner("Reading PRO-LAB report and building draft..."):
                parsed = parse_prolab_pdf(pdf_bytes)
                st.session_state.parsed_lab = parsed
                st.session_state.lab_pdf_bytes = pdf_bytes
                st.session_state.lab_pdf_hash = pdf_hash

                if parsed.get("samples"):
                    build_draft_job_from_prolab(
                        job,
                        parsed,
                        supported_molds=MOLD_DESCRIPTIONS.keys(),
                    )
                    build_draft()
                else:
                    st.session_state.draft_docx = None

        parsed = st.session_state.get("parsed_lab") or {}
        metadata = parsed.get("metadata", {})

        if parsed.get("samples"):
            st.markdown(
                '<div class="success-note"><b>Draft created.</b> Lab data was imported and a review-required Mold Assessment Report was generated.</div>',
                unsafe_allow_html=True,
            )
            c1, c2, c3 = st.columns(3)
            c1.metric("PRO-LAB Report #", metadata.get("report_number") or "—")
            c2.metric("Project", metadata.get("project_name") or "—")
            c3.metric("Samples Parsed", len(parsed.get("samples", [])))

            if metadata.get("test_location"):
                st.write(f"**Property from lab:** {metadata['test_location']}")

            if st.session_state.draft_docx:
                safe_name = (job.get("client_name") or "Client").replace(" ", "_")
                st.download_button(
                    "Download Automatic Draft DOCX",
                    data=st.session_state.draft_docx,
                    file_name=f"{safe_name}_Mold_Assessment_DRAFT.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    type="primary",
                )

            st.info(
                "Next: open **2. Review Report**. Anything the lab report cannot support is intentionally left for you to review."
            )
        else:
            st.error("I could not find a structured PRO-LAB result table in this PDF.")
            for warning in parsed.get("warnings", []):
                st.warning(warning)

with tab2:
    st.markdown('<p class="section-header">Consultant Review</p>', unsafe_allow_html=True)
    st.markdown(
        '<div class="review-note"><b>Review required:</b> lab data may be prefilled, but inspection observations, moisture findings, affected-area names, and the professional conclusion remain your decision.</div>',
        unsafe_allow_html=True,
    )

    if not st.session_state.get("parsed_lab"):
        st.info("Upload a PRO-LAB PDF in **1. Upload & Draft** first.")
    else:
        st.markdown("### Client & Property")
        c1, c2 = st.columns(2)
        with c1:
            job["client_name"] = st.text_input("Client Name", value=job.get("client_name", ""))
            job["address"] = st.text_input("Property Address", value=job.get("address", ""))
            job["city"] = st.text_input("City", value=job.get("city", ""))
        with c2:
            job["state"] = st.text_input("State", value=job.get("state", "TX"))
            job["zip"] = st.text_input("ZIP", value=job.get("zip", ""))
            job["phone"] = st.text_input("Phone", value=job.get("phone", ""))
            job["email"] = st.text_input("Email", value=job.get("email", ""))

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            job["inspection_date"] = st.date_input(
                "Assessment Date",
                value=job["inspection_date"],
            )
        with c2:
            job["report_date"] = st.date_input(
                "Report Date",
                value=job["report_date"],
            )
        with c3:
            humidity_unknown = job.get("humidity") is None
            known_humidity = st.checkbox(
                "RH measured",
                value=not humidity_unknown,
                key="rh_measured",
            )
        with c4:
            if known_humidity:
                default_humidity = 50 if job.get("humidity") is None else int(job["humidity"])
                job["humidity"] = st.number_input(
                    "Indoor RH (%)",
                    min_value=0,
                    max_value=100,
                    value=default_humidity,
                )
            else:
                job["humidity"] = None

        st.markdown("### Inspection Areas")
        finding_options = [
            "Needs consultant review",
            "Active mold growth confirmed",
            "Elevated spore counts",
            "Visual mold present",
            "No mold detected",
        ]

        for i, area in enumerate(job.get("areas", []), 1):
            with st.expander(area.get("name") or f"Area {i}", expanded=True):
                area["name"] = st.text_input(
                    "Area Name",
                    value=area.get("name", ""),
                    key=f"review_area_name_{area['id']}",
                    help="Generic lab locations such as 'INDOORS' are intentionally converted to an Area of Concern placeholder for you to rename.",
                )
                current_finding = area.get("finding", "Needs consultant review")
                if current_finding not in finding_options:
                    current_finding = "Needs consultant review"
                area["finding"] = st.selectbox(
                    "Consultant Finding",
                    finding_options,
                    index=finding_options.index(current_finding),
                    key=f"review_area_finding_{area['id']}",
                )
                area["description"] = st.text_area(
                    "Visual Observations",
                    value=area.get("description", ""),
                    key=f"review_area_desc_{area['id']}",
                    placeholder="Enter what you observed during the inspection.",
                )
                area["moisture_notes"] = st.text_area(
                    "Moisture Assessment",
                    value=area.get("moisture_notes", ""),
                    key=f"review_area_moisture_{area['id']}",
                    placeholder="Enter measured moisture findings and locations.",
                )

        st.markdown("### Imported Air Results")
        st.caption(
            "These rows came from the PRO-LAB result table. PRO-LAB's original sample-level determination is preserved in Lab Details."
        )

        air_rows = job.get("air_lab_rows", [])
        for row in air_rows:
            sample = next(
                (s for s in job.get("samples", []) if s.get("id") == row.get("sample_id")),
                {},
            )
            c1, c2, c3, c4 = st.columns([1.8, 2.0, 1.0, 1.3])
            c1.text_input(
                "Sample",
                value=sample_label(sample),
                disabled=True,
                key=f"review_sample_{row['id']}",
            )
            c2.text_input(
                "Fungal Type",
                value=row.get("fungal_type", ""),
                disabled=True,
                key=f"review_fungus_{row['id']}",
            )
            row["spore_count"] = st.number_input(
                "Spores/m³",
                min_value=0,
                value=int(row.get("spore_count", 0)),
                key=f"review_spores_{row['id']}",
            )
            int_options = ["Baseline (Reference)", "ELEVATED", "Not Elevated"]
            current_int = row.get("interpretation", "Not Elevated")
            if current_int not in int_options:
                current_int = "Not Elevated"
            row["interpretation"] = st.selectbox(
                "Consultant Comparison",
                int_options,
                index=int_options.index(current_int),
                key=f"review_interp_{row['id']}",
            )

        st.markdown("### Overall Professional Conclusion")
        outcome_options = [
            "Pending consultant review",
            "Mold remediation required",
            "No significant mold contamination identified",
        ]
        current_outcome = job.get("report_outcome", "Pending consultant review")
        if current_outcome not in outcome_options:
            current_outcome = "Pending consultant review"
        job["report_outcome"] = st.selectbox(
            "Overall Report Outcome",
            outcome_options,
            index=outcome_options.index(current_outcome),
        )

        st.markdown("### Draft / Final Report")
        c1, c2 = st.columns(2)

        with c1:
            if st.button("Refresh Draft Report", use_container_width=True):
                build_draft()
                st.success("Draft refreshed with your current review edits.")

            if st.session_state.get("draft_docx"):
                safe_name = (job.get("client_name") or "Client").replace(" ", "_")
                st.download_button(
                    "Download Current Draft",
                    data=st.session_state.draft_docx,
                    file_name=f"{safe_name}_Mold_Assessment_DRAFT.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )

        issues = final_review_issues()
        with c2:
            if issues:
                st.warning("Before finalizing: " + ", ".join(issues))

            reviewed = st.checkbox(
                "I reviewed the imported lab data, inspection findings, and professional conclusion.",
                value=False,
            )
            if st.button(
                "Approve & Generate Final Report",
                type="primary",
                use_container_width=True,
                disabled=bool(issues) or not reviewed,
            ):
                st.session_state.final_docx = build_report_bytes()
                st.success("Final report generated from the reviewed job data.")

            if st.session_state.get("final_docx"):
                safe_name = (job.get("client_name") or "Client").replace(" ", "_")
                st.download_button(
                    "Download FINAL DOCX",
                    data=st.session_state.final_docx,
                    file_name=f"{safe_name}_Mold_Assessment_Report.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    type="primary",
                    use_container_width=True,
                )

with tab3:
    st.markdown('<p class="section-header">Photos</p>', unsafe_allow_html=True)
    st.caption(
        "RG-2 keeps one primary photo per area. Multi-photo categorization and automatic grids are planned for RG-3."
    )

    st.file_uploader(
        "Property Exterior Photo",
        type=["jpg", "jpeg", "png"],
        key="photo_property",
    )

    for area in job.get("areas", []):
        st.file_uploader(
            f"{area.get('name') or 'Unnamed Area'} — Primary Photo",
            type=["jpg", "jpeg", "png"],
            key=f"photo_{area['id']}",
        )

    if st.button("Refresh Draft With Photos"):
        if st.session_state.get("parsed_lab"):
            build_draft()
            st.success("Draft refreshed with the currently uploaded photos.")
        else:
            st.warning("Upload a lab report first.")

with tab4:
    st.markdown('<p class="section-header">Parsed PRO-LAB Details</p>', unsafe_allow_html=True)
    parsed = st.session_state.get("parsed_lab")
    if not parsed:
        st.info("No lab report has been uploaded yet.")
    else:
        metadata = parsed.get("metadata", {})
        st.json(metadata, expanded=False)

        for warning in parsed.get("warnings", []):
            st.warning(warning)

        for index, lab_sample in enumerate(parsed.get("samples", []), 1):
            with st.expander(
                f"Lab Sample {index}: {lab_sample.get('location') or 'Unnamed'}",
                expanded=True,
            ):
                st.write(f"**COC / Line:** {lab_sample.get('coc_line') or '—'}")
                st.write(f"**Serial:** {lab_sample.get('serial_number') or '—'}")
                st.write(f"**Sample Type:** {lab_sample.get('sample_type') or '—'}")
                st.write(f"**Volume:** {lab_sample.get('volume') or '—'}")
                st.write(f"**Collection Date:** {lab_sample.get('collection_date') or '—'}")
                st.write(f"**Analysis Date:** {lab_sample.get('analysis_date') or '—'}")
                st.write(f"**PRO-LAB Determination:** {lab_sample.get('determination') or '—'}")
                if lab_sample.get("fungi"):
                    st.dataframe(
                        [
                            {"Fungal Type": fungus, "Spores/m³": count}
                            for fungus, count in lab_sample["fungi"].items()
                        ],
                        hide_index=True,
                        use_container_width=True,
                    )
                if lab_sample.get("total_spores") is not None:
                    st.write(f"**Total Spores:** {lab_sample['total_spores']} spores/m³")

with st.sidebar:
    st.markdown("## MTAR V2")
    st.write("Current sprint: **RG-2 — upload-to-draft workflow**")
    st.markdown(
        """
**Workflow**
1. Upload PRO-LAB PDF
2. Automatic draft is generated
3. Review inspection details
4. Add photos
5. Approve and generate final DOCX
"""
    )
    if st.button("Start New Report", use_container_width=True):
        reset_job()
