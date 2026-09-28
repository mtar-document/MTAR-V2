from __future__ import annotations

import copy
import hashlib
from io import BytesIO

import streamlit as st

from models import new_area, new_job_state, sample_location, validate_job
from prolab_parser import build_draft_job_from_prolab, parse_prolab_pdf
from report_builder import MOLD_DESCRIPTIONS, create_report

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
    '<p class="sub-header">Upload PRO-LAB → review areas & samples → add photos → final report</p>',
    unsafe_allow_html=True,
)

if "job" not in st.session_state:
    st.session_state.job = new_job_state()
if "parsed_lab" not in st.session_state:
    st.session_state.parsed_lab = None
if "lab_pdf_bytes" not in st.session_state:
    st.session_state.lab_pdf_bytes = None
if "lab_pdf_hash" not in st.session_state:
    st.session_state.lab_pdf_hash = None
if "automatic_draft" not in st.session_state:
    st.session_state.automatic_draft = None
if "final_docx" not in st.session_state:
    st.session_state.final_docx = None

job = st.session_state.job


def sample_label(sample: dict) -> str:
    name = (sample.get("name") or "").strip()
    if name:
        return name
    if sample.get("outdoor_control"):
        return "Outdoor Control"
    return sample_location(sample, job.get("areas", []))


def collect_photos() -> dict:
    """Return fresh file-like objects so python-docx can read them reliably."""
    photos = {}
    property_photo = st.session_state.get("photo_property")
    if property_photo:
        photos["property"] = BytesIO(property_photo.getvalue())

    for area in job.get("areas", []):
        upload = st.session_state.get(f"photo_{area['id']}")
        if upload:
            photos[area["id"]] = BytesIO(upload.getvalue())
    return photos


def build_report_bytes() -> bytes:
    output = create_report(
        copy.deepcopy(job),
        collect_photos(),
        st.session_state.get("lab_pdf_bytes"),
    )
    return output.getvalue()


def reset_job():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.session_state.job = new_job_state()
    st.rerun()


def final_review_issues() -> list[str]:
    issues = validate_job(
        job,
        lab_pdf_present=st.session_state.get("lab_pdf_bytes") is not None,
    )
    if any(a.get("finding") == "Needs consultant review" for a in job.get("areas", [])):
        issues.append("Review every inspection-area finding")
    return issues


def area_option_map() -> dict[str, str | None]:
    result: dict[str, str | None] = {"Unassigned": None}
    for index, area in enumerate(job.get("areas", []), 1):
        name = (area.get("name") or f"Inspection Area {index}").strip()
        result[f"{name} [{area['id'][-6:]}]"] = area["id"]
    return result


def air_results_matrix() -> list[dict]:
    samples = {
        s["id"]: s
        for s in job.get("samples", [])
        if s.get("type") == "Air Sample"
    }
    sample_ids = list(samples.keys())
    species = []
    values = {}
    for row in job.get("air_lab_rows", []):
        fungus = row.get("fungal_type", "")
        if fungus and fungus not in species:
            species.append(fungus)
        values[(fungus, row.get("sample_id"))] = row.get("spore_count", 0)

    matrix = []
    for fungus in species:
        record = {"Fungal Type": fungus}
        for sample_id in sample_ids:
            record[sample_label(samples[sample_id])] = values.get((fungus, sample_id), 0)
        matrix.append(record)
    return matrix


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
        "Upload the laboratory report first. MTAR imports supported lab data and creates an initial review-required draft."
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
                st.session_state.final_docx = None

                if parsed.get("samples"):
                    build_draft_job_from_prolab(
                        job,
                        parsed,
                        supported_molds=MOLD_DESCRIPTIONS.keys(),
                    )
                    st.session_state.automatic_draft = build_report_bytes()
                else:
                    st.session_state.automatic_draft = None

        parsed = st.session_state.get("parsed_lab") or {}
        metadata = parsed.get("metadata", {})

        if parsed.get("samples"):
            st.markdown(
                '<div class="success-note"><b>Lab imported.</b> Samples are now independent from inspection areas. Create the inspection areas and assign each sample in the Review tab.</div>',
                unsafe_allow_html=True,
            )
            c1, c2, c3 = st.columns(3)
            c1.metric("PRO-LAB Report #", metadata.get("report_number") or "—")
            c2.metric("Project", metadata.get("project_name") or "—")
            c3.metric("Samples Parsed", len(parsed.get("samples", [])))

            if metadata.get("test_location"):
                st.write(f"**Property from lab:** {metadata['test_location']}")

            if st.session_state.get("automatic_draft"):
                safe_name = (job.get("client_name") or "Client").replace(" ", "_")
                st.download_button(
                    "Download Initial Review Draft",
                    data=st.session_state.automatic_draft,
                    file_name=f"{safe_name}_Mold_Assessment_INITIAL_DRAFT.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )

            st.info(
                "Next: open **2. Review Report**. The current draft there is regenerated from your latest edits."
            )
        else:
            st.error("I could not find a structured PRO-LAB result table in this PDF.")
            for warning in parsed.get("warnings", []):
                st.warning(warning)

with tab2:
    st.markdown('<p class="section-header">Consultant Review</p>', unsafe_allow_html=True)
    st.markdown(
        '<div class="review-note"><b>Review required:</b> inspection areas are separate from lab samples. Create the actual areas, assign each sample, enter RH, and select the professional findings.</div>',
        unsafe_allow_html=True,
    )

    if not st.session_state.get("parsed_lab"):
        st.info("Upload a PRO-LAB PDF in **1. Upload & Draft** first.")
    else:
        st.markdown("### Client & Property")
        c1, c2 = st.columns(2)
        with c1:
            job["client_name"] = st.text_input(
                "Client Name *",
                value=job.get("client_name", ""),
                key="review_client_name",
            )
            job["address"] = st.text_input(
                "Property Address *",
                value=job.get("address", ""),
                key="review_address",
            )
            job["city"] = st.text_input(
                "City *",
                value=job.get("city", ""),
                key="review_city",
            )
        with c2:
            job["state"] = st.text_input(
                "State",
                value=job.get("state", "TX"),
                key="review_state",
            )
            job["zip"] = st.text_input(
                "ZIP *",
                value=job.get("zip", ""),
                key="review_zip",
            )

        c1, c2, c3 = st.columns(3)
        with c1:
            job["inspection_date"] = st.date_input(
                "Assessment Date *",
                value=job["inspection_date"],
                key="review_inspection_date",
            )
        with c2:
            job["report_date"] = st.date_input(
                "Report Date *",
                value=job["report_date"],
                key="review_report_date",
            )
        with c3:
            humidity_text = st.text_input(
                "Indoor RH (%) *",
                value="" if job.get("humidity") is None else str(job["humidity"]),
                placeholder="Required",
                key="review_humidity",
            ).strip()
            if not humidity_text:
                job["humidity"] = None
            else:
                try:
                    humidity_value = float(humidity_text)
                    if 0 <= humidity_value <= 100:
                        job["humidity"] = humidity_value
                    else:
                        job["humidity"] = None
                        st.error("Indoor RH must be between 0 and 100.")
                except ValueError:
                    job["humidity"] = None
                    st.error("Indoor RH must be a number.")

        st.markdown("### Inspection Areas")
        st.caption(
            "Areas are inspection entities. They are not created from lab sample names. Add the actual rooms/areas you inspected."
        )

        finding_options = [
            "Needs consultant review",
            "Active mold growth confirmed",
            "Elevated spore counts",
            "Visual mold present",
            "No mold detected",
        ]

        for index, area in enumerate(list(job.get("areas", [])), 1):
            with st.expander(area.get("name") or f"Inspection Area {index}", expanded=True):
                area["name"] = st.text_input(
                    "Area Name *",
                    value=area.get("name", ""),
                    key=f"area_name_{area['id']}",
                )
                current_finding = area.get("finding", "Needs consultant review")
                if current_finding not in finding_options:
                    current_finding = "Needs consultant review"
                area["finding"] = st.selectbox(
                    "Consultant Finding",
                    finding_options,
                    index=finding_options.index(current_finding),
                    key=f"area_finding_{area['id']}",
                )
                area["description"] = st.text_area(
                    "Visual Observations",
                    value=area.get("description", ""),
                    key=f"area_description_{area['id']}",
                    placeholder="Enter the visual inspection observations for this area.",
                )
                area["moisture_notes"] = st.text_area(
                    "Moisture Assessment",
                    value=area.get("moisture_notes", ""),
                    key=f"area_moisture_{area['id']}",
                    placeholder="Enter moisture readings/findings for this area.",
                )

                if st.button(
                    "Remove Inspection Area",
                    key=f"remove_area_{area['id']}",
                ):
                    removed_id = area["id"]
                    job["areas"] = [a for a in job["areas"] if a["id"] != removed_id]
                    for sample in job.get("samples", []):
                        if sample.get("area_id") == removed_id:
                            sample["area_id"] = None
                    st.rerun()

        if st.button("+ Add Inspection Area", type="secondary"):
            job["areas"].append(new_area(""))
            st.rerun()

        st.markdown("### Samples & Area Assignment")
        st.caption(
            "Sample names come from the PRO-LAB report when available. Assign each indoor/surface sample to an inspection area manually."
        )

        area_map = area_option_map()
        area_labels = list(area_map.keys())
        area_id_to_label = {value: label for label, value in area_map.items()}

        for index, sample in enumerate(job.get("samples", []), 1):
            with st.container(border=True):
                c1, c2, c3 = st.columns([2.0, 1.1, 2.0])
                with c1:
                    if sample.get("outdoor_control"):
                        sample["name"] = st.text_input(
                            "Sample Name",
                            value=sample_label(sample),
                            disabled=True,
                            key=f"sample_name_{sample['id']}",
                        )
                    else:
                        sample["name"] = st.text_input(
                            "Sample Name",
                            value=sample_label(sample),
                            key=f"sample_name_{sample['id']}",
                        )
                    if sample.get("lab_coc_line"):
                        st.caption(f"COC / Line: {sample['lab_coc_line']}")
                with c2:
                    st.text_input(
                        "Sample Type",
                        value=sample.get("type", ""),
                        disabled=True,
                        key=f"sample_type_{sample['id']}",
                    )
                with c3:
                    if sample.get("outdoor_control"):
                        st.text_input(
                            "Assigned Area",
                            value="Outdoor Control",
                            disabled=True,
                            key=f"sample_area_{sample['id']}",
                        )
                    else:
                        current_label = area_id_to_label.get(sample.get("area_id"), "Unassigned")
                        selected = st.selectbox(
                            "Assign to Inspection Area *",
                            area_labels,
                            index=area_labels.index(current_label)
                            if current_label in area_labels
                            else 0,
                            key=f"sample_area_{sample['id']}",
                        )
                        sample["area_id"] = area_map[selected]

        if job.get("air_lab_rows"):
            st.markdown("### Imported Air Results")
            st.caption("Species are shown side by side by sample for easier comparison.")
            st.dataframe(
                air_results_matrix(),
                hide_index=True,
                use_container_width=True,
            )

            air_sample_map = {s["id"]: s for s in job.get("samples", [])}
            for sample_id in dict.fromkeys(
                row.get("sample_id") for row in job.get("air_lab_rows", [])
            ):
                sample = air_sample_map.get(sample_id)
                if not sample:
                    continue
                with st.expander(f"Review air comparison: {sample_label(sample)}", expanded=False):
                    for row in [
                        r for r in job.get("air_lab_rows", [])
                        if r.get("sample_id") == sample_id
                    ]:
                        c1, c2, c3 = st.columns([2.0, 1.0, 1.3])
                        c1.text_input(
                            "Fungal Type",
                            value=row.get("fungal_type", ""),
                            disabled=True,
                            key=f"fungus_{row['id']}",
                        )
                        row["spore_count"] = st.number_input(
                            "Spores/m³",
                            min_value=0,
                            value=int(row.get("spore_count", 0)),
                            key=f"spores_{row['id']}",
                        )
                        options = ["Baseline (Reference)", "ELEVATED", "Not Elevated"]
                        current = row.get("interpretation", "Not Elevated")
                        if current not in options:
                            current = "Not Elevated"
                        row["interpretation"] = st.selectbox(
                            "Consultant Comparison",
                            options,
                            index=options.index(current),
                            key=f"interpretation_{row['id']}",
                        )

        surface_rows = job.get("surface_lab_rows", [])
        if surface_rows:
            st.markdown("### Imported Surface Sample Results")
            sample_map = {s["id"]: s for s in job.get("samples", [])}
            for row in surface_rows:
                sample = sample_map.get(row.get("sample_id"), {})
                with st.container(border=True):
                    c1, c2, c3 = st.columns([2.0, 1.4, 2.0])
                    c1.text_input(
                        "Surface Sample",
                        value=sample_label(sample),
                        disabled=True,
                        key=f"surface_name_{row['id']}",
                    )
                    surface_options = [
                        "Normal",
                        "UNUSUAL / Mold Present",
                        "UNUSUAL / Mold Present (Stachybotrys)",
                    ]
                    current_result = row.get("result", "Normal")
                    if current_result not in surface_options:
                        current_result = "Normal"
                    row["result"] = c2.selectbox(
                        "Consultant Result",
                        surface_options,
                        index=surface_options.index(current_result),
                        key=f"surface_result_{row['id']}",
                    )
                    determination = sample.get("lab_determination") or "—"
                    c3.text_input(
                        "PRO-LAB Determination",
                        value=determination,
                        disabled=True,
                        key=f"surface_det_{row['id']}",
                    )
                    lab_fungi = sample.get("lab_fungi", {})
                    if lab_fungi:
                        st.caption(
                            "Lab organisms: "
                            + ", ".join(
                                f"{name}: {value}"
                                for name, value in lab_fungi.items()
                            )
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
            "Overall Report Outcome *",
            outcome_options,
            index=outcome_options.index(current_outcome),
            key="review_outcome",
        )

        # Always regenerate the review draft from the current widget values so
        # the DOCX cannot lag behind the selected conclusion or observations.
        current_draft = build_report_bytes()

        st.markdown("### Draft / Final Report")
        c1, c2 = st.columns(2)
        safe_name = (job.get("client_name") or "Client").replace(" ", "_")

        with c1:
            st.download_button(
                "Download Current Draft",
                data=current_draft,
                file_name=f"{safe_name}_Mold_Assessment_DRAFT.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )

        issues = final_review_issues()
        with c2:
            if issues:
                st.warning("Before finalizing: " + ", ".join(dict.fromkeys(issues)))

            reviewed = st.checkbox(
                "I reviewed the lab data, sample-to-area assignments, inspection findings, and professional conclusion.",
                value=False,
                key="final_review_checkbox",
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
        "The property photo is placed on page 1. Area photos are placed in their assigned inspection-area sections."
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

    if st.session_state.get("parsed_lab"):
        st.success(
            "Photos are included automatically the next time you download the Current Draft or generate the Final Report."
        )

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
                            {"Fungal Type": fungus, "Result": count}
                            for fungus, count in lab_sample["fungi"].items()
                        ],
                        hide_index=True,
                        use_container_width=True,
                    )
                if lab_sample.get("total_spores") is not None:
                    st.write(f"**Total Spores:** {lab_sample['total_spores']} spores/m³")

with st.sidebar:
    st.markdown("## MTAR V2")
    st.write("Current branch work: **RG-2 review fixes**")
    st.markdown(
        """
**Workflow**
1. Upload PRO-LAB PDF
2. Create inspection areas
3. Assign samples to areas
4. Enter required RH and findings
5. Add photos
6. Review current draft
7. Approve final DOCX
"""
    )
    if st.button("Start New Report", use_container_width=True):
        reset_job()
