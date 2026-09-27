from __future__ import annotations

import copy
from pathlib import Path

import streamlit as st

from models import (
    new_air_lab_row,
    new_area,
    new_job_state,
    new_sample,
    new_surface_lab_row,
    sample_location,
    validate_job,
)
from report_builder import MOLD_DESCRIPTIONS, create_report
from prolab_parser import apply_prolab_results, parse_prolab_pdf, suggested_mapping

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
    .rg1-note {background: #f5f7f8; border-left: 4px solid #184058; padding: 0.8rem 1rem; border-radius: 4px; margin-bottom: 1rem;}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown('<h1 class="main-header">MTAR V2 — Mold Assessment Report</h1>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Sprint RG-2: structured PRO-LAB import with consultant review</p>', unsafe_allow_html=True)

if "job" not in st.session_state:
    st.session_state.job = new_job_state()

job = st.session_state.job


def reset_job():
    st.session_state.job = new_job_state()
    for key in list(st.session_state.keys()):
        if key.startswith("photo_") or key.startswith("prolab_") or key == "lab_pdf":
            del st.session_state[key]
    st.rerun()


def area_label(area_id: str | None) -> str:
    if not area_id:
        return "No linked area"
    for area in job["areas"]:
        if area["id"] == area_id:
            return area["name"] or "Unnamed Area"
    return "Unknown Area"


def sample_label(sample: dict) -> str:
    loc = sample_location(sample, job["areas"])
    if sample.get("outdoor_control"):
        return f"Outdoor Control — {sample['type']}"
    return f"{loc} — {sample['type']}"


def sample_options(sample_type: str | None = None) -> dict[str, str]:
    result = {}
    for sample in job["samples"]:
        if sample_type and sample["type"] != sample_type:
            continue
        result[f"{sample_label(sample)} [{sample['id'][-6:]}]"] = sample["id"]
    return result


def sync_orphaned_rows():
    valid_sample_ids = {s["id"] for s in job["samples"]}
    job["air_lab_rows"] = [r for r in job["air_lab_rows"] if r.get("sample_id") in valid_sample_ids]
    job["surface_lab_rows"] = [r for r in job["surface_lab_rows"] if r.get("sample_id") in valid_sample_ids]


sync_orphaned_rows()

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "1. Client & Inspection",
        "2. Areas & Samples",
        "3. Photos",
        "4. Lab Data",
        "5. Review & Generate",
    ]
)

with tab1:
    st.markdown('<div class="rg1-note"><b>RG-1 rule:</b> enter each fact once. Later screens reuse the same job record.</div>', unsafe_allow_html=True)
    st.markdown('<p class="section-header">Client & Property</p>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        job["client_name"] = st.text_input("Client Name *", value=job["client_name"], key="client_name")
        job["address"] = st.text_input("Property Address *", value=job["address"], key="address")
        job["city"] = st.text_input("City *", value=job["city"], key="city")
    with c2:
        job["phone"] = st.text_input("Phone", value=job["phone"], key="phone")
        job["email"] = st.text_input("Email", value=job["email"], key="email")
        states = ["TX", "OK", "AR", "LA", "NM"]
        current_state = job["state"] if job["state"] in states else "TX"
        job["state"] = st.selectbox("State", states, index=states.index(current_state), key="state")
        job["zip"] = st.text_input("ZIP Code *", value=job["zip"], key="zip")

    st.markdown('<p class="section-header">Inspection Details</p>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        job["inspection_date"] = st.date_input("Assessment Date *", value=job["inspection_date"], key="inspection_date")
    with c2:
        job["report_date"] = st.date_input("Report Date *", value=job["report_date"], key="report_date")
    with c3:
        job["humidity"] = st.number_input("Indoor RH (%)", min_value=0, max_value=100, value=int(job["humidity"]), key="humidity")
    with c4:
        temp_default = 0.0 if job["temperature"] is None else float(job["temperature"])
        temp_value = st.number_input("Indoor Temperature (°F)", min_value=0.0, max_value=150.0, value=temp_default, key="temperature")
        job["temperature"] = None if temp_value == 0 else temp_value

    job["general_observations"] = st.text_area(
        "General Inspection Notes",
        value=job["general_observations"],
        height=110,
        placeholder="Optional overall notes for this assessment.",
        key="general_observations",
    )

with tab2:
    st.markdown('<p class="section-header">Inspection Areas</p>', unsafe_allow_html=True)
    st.caption("Each area gets a stable internal ID so samples, photos, lab rows, and report sections can all point to the same area.")

    for index, area in enumerate(list(job["areas"])):
        title = area["name"] or f"Area {index + 1}"
        with st.expander(title, expanded=True):
            c1, c2 = st.columns([2, 1])
            with c1:
                area["name"] = st.text_input("Area Name *", value=area["name"], key=f"area_name_{area['id']}")
            with c2:
                findings = [
                    "Active mold growth confirmed",
                    "Elevated spore counts",
                    "Visual mold present",
                    "No mold detected",
                ]
                current = area["finding"] if area["finding"] in findings else findings[0]
                area["finding"] = st.selectbox("Finding", findings, index=findings.index(current), key=f"area_find_{area['id']}")

            area["description"] = st.text_area(
                "Visual Observations",
                value=area["description"],
                height=90,
                key=f"area_desc_{area['id']}",
                placeholder="Describe visible conditions, damage, suspect growth, staining, access limitations, etc.",
            )
            area["moisture_notes"] = st.text_area(
                "Moisture Assessment",
                value=area["moisture_notes"],
                height=90,
                key=f"area_moist_{area['id']}",
                placeholder="Example: Left wall base measured 21% moisture; surrounding materials were below 15%.",
            )

            if len(job["areas"]) > 1 and st.button("Remove Area", key=f"remove_area_{area['id']}"):
                job["areas"] = [a for a in job["areas"] if a["id"] != area["id"]]
                for sample in job["samples"]:
                    if sample.get("area_id") == area["id"]:
                        sample["area_id"] = None
                st.rerun()

    if st.button("+ Add Inspection Area", type="secondary"):
        job["areas"].append(new_area())
        st.rerun()

    st.markdown('<p class="section-header">Samples</p>', unsafe_allow_html=True)
    st.info("Outdoor control is fixed. Indoor air and swab samples can be linked to an inspection area so the location is reused everywhere else.")

    area_choices = {f"{a['name'] or 'Unnamed Area'} [{a['id'][-6:]}]": a["id"] for a in job["areas"]}
    area_labels = list(area_choices.keys())
    area_ids = list(area_choices.values())

    for sample in list(job["samples"]):
        with st.container(border=True):
            if sample.get("outdoor_control"):
                c1, c2, c3 = st.columns(3)
                c1.text_input("Sample Type", value="Air Sample", disabled=True, key=f"out_type_{sample['id']}")
                c2.text_input("Location", value="Outdoor Control", disabled=True, key=f"out_loc_{sample['id']}")
                c3.text_input("Role", value="Baseline / Control", disabled=True, key=f"out_role_{sample['id']}")
                continue

            c1, c2, c3, c4 = st.columns([1.2, 1.5, 1.7, 0.6])
            with c1:
                types = ["Air Sample", "Swab"]
                current_type = sample["type"] if sample["type"] in types else "Air Sample"
                sample["type"] = st.selectbox("Type", types, index=types.index(current_type), key=f"sample_type_{sample['id']}")
            with c2:
                current_area_id = sample.get("area_id")
                current_index = area_ids.index(current_area_id) if current_area_id in area_ids else 0
                selected_area = st.selectbox("Linked Area", area_labels, index=current_index, key=f"sample_area_{sample['id']}")
                sample["area_id"] = area_choices[selected_area]
            with c3:
                default_loc = sample["location"]
                sample["location"] = st.text_input(
                    "Specific Collection Location",
                    value=default_loc,
                    key=f"sample_loc_{sample['id']}",
                    placeholder="Leave blank to use linked area name",
                )
            with c4:
                st.write("")
                st.write("")
                if st.button("✕", key=f"remove_sample_{sample['id']}", help="Remove sample"):
                    job["samples"] = [s for s in job["samples"] if s["id"] != sample["id"]]
                    sync_orphaned_rows()
                    st.rerun()

    c1, c2 = st.columns(2)
    with c1:
        if st.button("+ Add Indoor Air Sample"):
            area_id = job["areas"][0]["id"] if job["areas"] else None
            job["samples"].append(new_sample("Air Sample", area_id=area_id))
            st.rerun()
    with c2:
        if st.button("+ Add Swab Sample"):
            area_id = job["areas"][0]["id"] if job["areas"] else None
            job["samples"].append(new_sample("Swab", area_id=area_id))
            st.rerun()

with tab3:
    st.markdown('<p class="section-header">Property & Area Photos</p>', unsafe_allow_html=True)
    st.caption("RG-1 keeps the current one-photo-per-area behavior but fixes the linking bug. Multi-photo grids are Sprint RG-3.")

    st.file_uploader("Property Exterior Photo", type=["jpg", "jpeg", "png"], key="photo_property")

    for area in job["areas"]:
        if not area["name"]:
            continue
        st.file_uploader(
            f"{area['name']} — Primary Photo",
            type=["jpg", "jpeg", "png"],
            key=f"photo_{area['id']}",
        )

with tab4:
    st.markdown('<p class="section-header">PRO-LAB PDF</p>', unsafe_allow_html=True)
    lab_pdf = st.file_uploader("PRO-LAB Certificate of Mold Analysis (PDF) *", type=["pdf"], key="lab_pdf")
    st.caption(
        "RG-2 reads the actual PRO-LAB result table only. Narrative definitions and mold reference pages are ignored."
    )

    if lab_pdf is not None:
        if st.button("Analyze PRO-LAB Report", type="primary", key="analyze_prolab"):
            parsed = parse_prolab_pdf(lab_pdf.getvalue())
            st.session_state.prolab_parsed = parsed
            st.session_state.prolab_mapping = suggested_mapping(parsed, job)

        parsed = st.session_state.get("prolab_parsed")
        if parsed:
            metadata = parsed.get("metadata", {})
            c1, c2, c3 = st.columns(3)
            c1.metric("PRO-LAB Report #", metadata.get("report_number") or "—")
            c2.metric("Project", metadata.get("project_name") or "—")
            c3.metric("Samples Parsed", len(parsed.get("samples", [])))
            if metadata.get("test_location"):
                st.caption(f"Lab test location: {metadata['test_location']}")

            for warning in parsed.get("warnings", []):
                st.warning(warning)

            if parsed.get("samples"):
                st.markdown("#### Review Parsed Samples")
                st.info(
                    "Confirm each PRO-LAB sample is mapped to the correct job sample before importing. "
                    "The parser does not decide whether remediation is required."
                )

                job_sample_labels = {sample_label(s): s["id"] for s in job["samples"]}
                label_by_id = {v: k for k, v in job_sample_labels.items()}
                mapping = st.session_state.setdefault(
                    "prolab_mapping", suggested_mapping(parsed, job)
                )

                for lab_sample in parsed["samples"]:
                    with st.container(border=True):
                        c1, c2 = st.columns([2.1, 1.5])
                        with c1:
                            st.markdown(
                                f"**{lab_sample.get('location') or 'Unnamed lab sample'}**  "
                                f"— COC {lab_sample.get('coc_line') or '—'}"
                            )
                            st.write(
                                f"Serial: {lab_sample.get('serial_number') or '—'} | "
                                f"Type: {lab_sample.get('sample_type') or '—'} | "
                                f"Volume: {lab_sample.get('volume') or '—'}"
                            )
                            st.write(
                                f"PRO-LAB determination: **{lab_sample.get('determination') or '—'}**"
                            )
                            if lab_sample.get("fungi"):
                                st.dataframe(
                                    [
                                        {"Fungal Type": fungus, "Spores/m³": count}
                                        for fungus, count in lab_sample["fungi"].items()
                                    ],
                                    use_container_width=True,
                                    hide_index=True,
                                )
                            if lab_sample.get("total_spores") is not None:
                                st.caption(f"Total spores: {lab_sample['total_spores']} spores/m³")

                        with c2:
                            option_labels = ["Do not import"] + list(job_sample_labels.keys())
                            current_id = mapping.get(lab_sample["key"], "")
                            current_label = label_by_id.get(current_id, "Do not import")
                            selected_label = st.selectbox(
                                "Map to job sample",
                                option_labels,
                                index=option_labels.index(current_label)
                                if current_label in option_labels
                                else 0,
                                key=f"prolab_map_{lab_sample['key']}",
                            )
                            if selected_label == "Do not import":
                                mapping.pop(lab_sample["key"], None)
                            else:
                                mapping[lab_sample["key"]] = job_sample_labels[selected_label]

                if st.button("Accept & Import Reviewed Lab Results", key="apply_prolab"):
                    apply_prolab_results(
                        job,
                        parsed,
                        mapping,
                        supported_molds=MOLD_DESCRIPTIONS.keys(),
                    )
                    st.session_state["mold_types"] = list(job.get("mold_types", []))
                    st.success(
                        "Reviewed PRO-LAB results imported. You can still edit any result row below."
                    )
                    st.rerun()

    st.markdown('<p class="section-header">Air Sample Result Rows</p>', unsafe_allow_html=True)
    air_samples = [s for s in job["samples"] if s["type"] == "Air Sample"]
    air_option_map = {sample_label(s): s["id"] for s in air_samples}
    air_labels = list(air_option_map.keys())

    for row in list(job["air_lab_rows"]):
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([1.8, 1.5, 1, 1.2, 0.45])
            current_id = row.get("sample_id")
            if current_id not in air_option_map.values() and air_samples:
                current_id = air_samples[0]["id"]
                row["sample_id"] = current_id
            with c1:
                current_label = next((k for k, v in air_option_map.items() if v == current_id), air_labels[0] if air_labels else "")
                selected = st.selectbox("Sample", air_labels, index=air_labels.index(current_label) if current_label in air_labels else 0, key=f"air_sample_{row['id']}") if air_labels else None
                if selected:
                    row["sample_id"] = air_option_map[selected]
            with c2:
                molds = list(MOLD_DESCRIPTIONS.keys())
                current_mold = row["fungal_type"] if row["fungal_type"] in molds else "Penicillium/Aspergillus"
                row["fungal_type"] = st.selectbox("Fungal Type", molds, index=molds.index(current_mold), key=f"air_mold_{row['id']}")
            with c3:
                row["spore_count"] = st.number_input("Spores/m³", min_value=0, value=int(row["spore_count"]), step=1, key=f"air_count_{row['id']}")
            with c4:
                options = ["Baseline (Reference)", "ELEVATED", "Not Elevated"]
                current_int = row["interpretation"] if row["interpretation"] in options else "Not Elevated"
                row["interpretation"] = st.selectbox("Interpretation", options, index=options.index(current_int), key=f"air_int_{row['id']}")
            with c5:
                st.write("")
                st.write("")
                if st.button("✕", key=f"remove_airrow_{row['id']}"):
                    job["air_lab_rows"] = [r for r in job["air_lab_rows"] if r["id"] != row["id"]]
                    st.rerun()

    if st.button("+ Add Air Result Row"):
        default_sample = air_samples[0]["id"] if air_samples else ""
        job["air_lab_rows"].append(new_air_lab_row(default_sample))
        st.rerun()

    st.markdown('<p class="section-header">Surface / Swab Results</p>', unsafe_allow_html=True)
    swab_samples = [s for s in job["samples"] if s["type"] == "Swab"]
    swab_option_map = {sample_label(s): s["id"] for s in swab_samples}
    swab_labels = list(swab_option_map.keys())

    if not swab_samples:
        st.info("No swab samples are currently linked to this job.")
    else:
        for row in list(job["surface_lab_rows"]):
            with st.container(border=True):
                c1, c2, c3 = st.columns([2.2, 2.2, 0.45])
                current_id = row.get("sample_id")
                if current_id not in swab_option_map.values():
                    current_id = swab_samples[0]["id"]
                    row["sample_id"] = current_id
                with c1:
                    current_label = next((k for k, v in swab_option_map.items() if v == current_id), swab_labels[0])
                    selected = st.selectbox("Sample", swab_labels, index=swab_labels.index(current_label), key=f"surf_sample_{row['id']}")
                    row["sample_id"] = swab_option_map[selected]
                with c2:
                    surface_options = ["UNUSUAL / Mold Present", "UNUSUAL / Mold Present (Stachybotrys)", "Normal"]
                    current_result = row["result"] if row["result"] in surface_options else "Normal"
                    row["result"] = st.selectbox("Result", surface_options, index=surface_options.index(current_result), key=f"surf_result_{row['id']}")
                with c3:
                    st.write("")
                    st.write("")
                    if st.button("✕", key=f"remove_surfrow_{row['id']}"):
                        job["surface_lab_rows"] = [r for r in job["surface_lab_rows"] if r["id"] != row["id"]]
                        st.rerun()

        if st.button("+ Add Swab Result Row"):
            job["surface_lab_rows"].append(new_surface_lab_row(swab_samples[0]["id"]))
            st.rerun()

    st.markdown('<p class="section-header">Mold Types Identified</p>', unsafe_allow_html=True)
    job["mold_types"] = st.multiselect(
        "Mold types to describe in the report",
        options=list(MOLD_DESCRIPTIONS.keys()),
        default=job["mold_types"],
        key="mold_types",
    )

with tab5:
    st.markdown('<p class="section-header">Consultant Review</p>', unsafe_allow_html=True)
    outcome_options = ["Mold remediation required", "No significant mold contamination identified"]
    current_outcome = job["report_outcome"] if job["report_outcome"] in outcome_options else outcome_options[0]
    job["report_outcome"] = st.selectbox(
        "Overall report outcome",
        outcome_options,
        index=outcome_options.index(current_outcome),
        help="This remains a consultant decision. The app does not make this determination automatically in RG-1.",
        key="report_outcome",
    )

    lab_pdf = st.session_state.get("lab_pdf")
    missing = validate_job(job, lab_pdf_present=lab_pdf is not None)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Client / Property")
        st.write(job["client_name"] or "—")
        st.write(f"{job['address'] or '—'}, {job['city'] or '—'}, {job['state']} {job['zip'] or '—'}")
        st.write(f"Assessment date: {job['inspection_date']}")
        st.write(f"Indoor RH: {job['humidity']}%")
    with c2:
        st.markdown("#### Job Structure")
        st.write(f"Inspection areas: {len([a for a in job['areas'] if a['name']])}")
        st.write(f"Samples: {len(job['samples'])}")
        st.write(f"Air result rows: {len(job['air_lab_rows'])}")
        st.write(f"Swab result rows: {len(job['surface_lab_rows'])}")
        st.write(f"Lab PDF: {'Uploaded' if lab_pdf else 'Missing'}")

    st.markdown("#### Areas")
    for area in job["areas"]:
        if not area["name"]:
            continue
        st.markdown(f"**{area['name']}** — {area['finding']}")
        if area["description"]:
            st.write(area["description"])
        if area["moisture_notes"]:
            st.caption(f"Moisture: {area['moisture_notes']}")

    if missing:
        st.warning("Complete before generating: " + ", ".join(missing))

    review_confirmed = st.checkbox(
        "I reviewed the job information and report outcome above.",
        value=False,
        key="review_confirmed",
    )

    if st.button(
        "Generate Draft Mold Assessment Report",
        type="primary",
        disabled=bool(missing) or not review_confirmed,
    ):
        photos = {}
        property_photo = st.session_state.get("photo_property")
        if property_photo:
            photos["property"] = property_photo
        for area in job["areas"]:
            upload = st.session_state.get(f"photo_{area['id']}")
            if upload:
                photos[area["id"]] = upload

        lab_bytes = None
        if lab_pdf:
            lab_bytes = lab_pdf.getvalue()

        report_job = copy.deepcopy(job)
        try:
            docx = create_report(report_job, photos, lab_bytes)
            st.success("Draft report generated from the structured V2 job record.")
            safe_name = (job["client_name"] or "Client").replace(" ", "_")
            st.download_button(
                "Download Draft DOCX",
                data=docx.getvalue(),
                file_name=f"{safe_name}_Mold_Assessment_Report_V2.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        except Exception as exc:
            st.error(f"Could not generate report: {exc}")
            st.exception(exc)

with st.sidebar:
    st.markdown("## MTAR V2")
    st.write("Current sprint: **RG-1 — structured job foundation**")
    st.markdown(
        """
**Included now**
- One reusable job record
- Areas linked to samples
- Lab rows linked to samples
- Area photos linked by stable IDs
- Existing DOCX report format preserved
- Manual consultant outcome review

**Next sprint — RG-2**
- Parse PRO-LAB sample tables
- Match COC/serial/sample rows
- Populate lab result rows automatically
"""
    )
    st.divider()
    if st.button("Reset V2 Job", type="secondary"):
        reset_job()
