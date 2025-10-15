import json
import io
import os
import re
from typing import Dict, List, Any, Tuple
import streamlit as st
import pandas as pd

from timetable import (
    generate_multiple_timetables,
    save_schedule_csv,
    save_schedule_json,
)


def _read_table_file(uploaded_file) -> pd.DataFrame:
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            return pd.read_csv(uploaded_file)
        elif uploaded_file.name.lower().endswith((".xlsx", ".xls")):
            return pd.read_excel(uploaded_file)
        else:
            st.warning("Unsupported file type. Please upload CSV or Excel.")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Failed to read file: {e}")
        return pd.DataFrame()


def _parse_faculty_divisions(cell: Any) -> List[Tuple[str, List[str]]]:
    """Parses a cell like 'Mr. X [A] Ms. Y [B]' -> [("Mr. X", ["A"]), ("Ms. Y", ["B"])].
    Works robustly with multiple tags like [A3 B3] by extracting the letter tag.
    """
    if cell is None:
        return []
    text = str(cell)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    # Split by common separators while keeping names grouped
    chunks = re.split(r"\s{2,}|,|;|\n|\r", text)
    results: List[Tuple[str, List[str]]] = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        # Extract all bracket groups and the base name before first bracket
        name = re.split(r"\[", chunk, maxsplit=1)[0].strip()
        tags = re.findall(r"\[([^\]]+)\]", chunk)
        divisions: List[str] = []
        for t in tags:
            # pick letters A/B (ignore batch numbers)
            letters = re.findall(r"[A-Za-z]", t)
            for L in letters:
                U = L.upper()
                if U in ("A", "B", "C", "D") and U not in divisions:
                    divisions.append(U)
        if name:
            results.append((name, divisions or ["A"]))
    return results


def schedule_to_dataframe(schedule: List[Dict[str, Any]], config: Dict[str, Any] = None) -> pd.DataFrame:
    # Convert flat schedule to a grid: first column = time range, columns = days (Mon..Sun)
    df = pd.DataFrame(schedule)
    if df.empty:
        return df
    # Ensure expected columns
    for col in ["day", "start_time", "end_time", "subject_name", "room"]:
        if col not in df.columns:
            df[col] = ""

    # Get working days from config if available, otherwise use data
    if config and "selected_days" in config:
        working_days = config["selected_days"]
    else:
        working_days = df["day"].unique().tolist()
    
    # Normalize day order starting Monday
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    # Create ordered categories with working days first, then any others
    ordered_categories = []
    for day in day_order:
        if day in working_days:
            ordered_categories.append(day)
    # Add any remaining days not in standard order
    for day in working_days:
        if day not in ordered_categories:
            ordered_categories.append(day)
    
    df["day"] = pd.Categorical(df["day"], categories=ordered_categories, ordered=True)

    # Build time label and create a sortable key that puts AM before PM
    df["Time"] = df["start_time"].fillna("") + " - " + df["end_time"].fillna("")
    def _time_sort_key(s: str) -> tuple:
        s = (s or "").strip().lower()
        # Expect formats like '9:00 am', '10:30 pm'
        try:
            import datetime as _dt
            dt = _dt.datetime.strptime(s, "%I:%M %p")
            ampm_order = 0 if "am" in s else 1
            return (ampm_order, dt.hour % 12, dt.minute)
        except Exception:
            # Fallback: push unknowns to end
            return (2, 99, 99)
    df["_sort_key"] = df["start_time"].apply(_time_sort_key)
    df = df.sort_values(by=["_sort_key", "day"]).drop(columns=["_sort_key"]).reset_index(drop=True)

    # Cell content: Subject (Room)
    df["cell"] = df["subject_name"].fillna("") + df.apply(lambda r: f" ({r['room']})" if r.get("room") else "", axis=1)

    # Pivot
    pivot = df.pivot_table(index="Time", columns="day", values="cell", aggfunc=lambda x: ", ".join([v for v in x if v]))
    # Ensure ALL working days are shown as columns, even if empty
    pivot = pivot.reindex(columns=ordered_categories)
    # Fill NaN with empty strings
    pivot = pivot.fillna("")
    
    # Sort the pivot by time using the same logic
    def _pivot_time_sort_key(index):
        # Handle pandas Index - convert to list of sort keys
        sort_keys = []
        for time_str in index:
            time_str = str(time_str).strip().lower()
            # Extract start time from "start - end" format
            start_time = time_str.split(" - ")[0] if " - " in time_str else time_str
            try:
                import datetime as _dt
                dt = _dt.datetime.strptime(start_time, "%I:%M %p")
                ampm_order = 0 if "am" in start_time else 1
                sort_keys.append((ampm_order, dt.hour % 12, dt.minute))
            except Exception:
                sort_keys.append((2, 99, 99))
        return sort_keys
    
    # Sort the pivot index by time
    pivot = pivot.sort_index(key=_pivot_time_sort_key)
    pivot = pivot.reset_index()
    return pivot


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def schedule_to_json_bytes(schedule: List[Dict[str, Any]]) -> bytes:
    return json.dumps(schedule, indent=2).encode("utf-8")


def build_config_via_upload() -> Dict[str, Any]:
    st.subheader("Upload Semester Table")
    up = st.file_uploader("Upload CSV/Excel of your semester table", type=["csv", "xlsx", "xls"], key="sheet_uploader")
    if up is None:
        return {}

    df = _read_table_file(up)
    if df.empty:
        return {}

    with st.expander("Preview uploaded data", expanded=False):
        st.dataframe(df.head(30), use_container_width=True)

    with st.form("upload_builder_form"):
        st.subheader("Generate from Uploaded Data")
        num_timetables = st.number_input("Number of timetables", min_value=1, value=2, step=1, key="up_num_tt")
        timetable_names_raw = st.text_input("Timetable names (comma-separated, optional)", value="A, B", key="up_tt_names").strip()

        st.write("Select working days:")
        col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
        with col1:
            monday = st.checkbox("Monday", value=True, key="up_mon")
        with col2:
            tuesday = st.checkbox("Tuesday", value=True, key="up_tue")
        with col3:
            wednesday = st.checkbox("Wednesday", value=True, key="up_wed")
        with col4:
            thursday = st.checkbox("Thursday", value=True, key="up_thu")
        with col5:
            friday = st.checkbox("Friday", value=True, key="up_fri")
        with col6:
            saturday = st.checkbox("Saturday", value=False, key="up_sat")
        with col7:
            sunday = st.checkbox("Sunday", value=False, key="up_sun")
        working_days = sum([monday, tuesday, wednesday, thursday, friday, saturday, sunday])

        st.write("Day start time:")
        col_start_hour, col_start_ampm = st.columns([1, 1])
        with col_start_hour:
            start_hour = st.selectbox("Hour", options=list(range(1, 13)), index=8, key="up_start_hr")
        with col_start_ampm:
            start_ampm = st.selectbox("AM/PM", options=["am", "pm"], index=0, key="up_start_ampm")

        st.write("Day end time:")
        col_end_hour, col_end_ampm = st.columns([1, 1])
        with col_end_hour:
            end_hour = st.selectbox("Hour", options=list(range(1, 13)), index=4, key="up_end_hr")
        with col_end_ampm:
            end_ampm = st.selectbox("AM/PM", options=["am", "pm"], index=1, key="up_end_ampm")

        st.markdown("---")
        st.subheader("Slots & Divisions")
        theory_slot = st.number_input("Theory slot length (minutes)", min_value=10, value=50, step=5, key="up_theory_slot")
        practical_slot = st.number_input("Practical slot length (minutes)", min_value=10, value=100, step=5, key="up_prac_slot")
        theory_sessions_per_week = st.number_input("Default theory sessions per subject (per week)", min_value=1, value=3, step=1, key="up_theory_sess")
        practical_sessions_per_week = st.number_input("Default practical sessions per subject (per week)", min_value=1, value=1, step=1, key="up_prac_sess")
        divisions = st.multiselect("Divisions/classes present", options=["A", "B", "C", "D"], default=["A", "B"], key="up_divs")

        st.markdown("---")
        st.subheader("Rooms (optional)")
        theory_rooms_text = st.text_area("Theory rooms (one per line)", value="Classroom A\nClassroom B", height=80, key="up_rooms_th")
        practical_rooms_text = st.text_area("Practical rooms/labs (one per line)", value="Lab 1\nLab 2", height=80, key="up_rooms_pr")

        submitted = st.form_submit_button("Build configuration from sheet")
        if not submitted:
            return {}

    # Utilities
    from datetime import datetime as _dt
    def _to_24h(hour: int, ampm: str) -> str:
        try:
            dt = _dt.strptime(f"{hour}:00 {ampm.upper()}", "%I:%M %p")
            return dt.strftime("%H:%M")
        except Exception:
            return "09:00"

    # Identify likely columns
    col_map = {
        "code": None,
        "name": None,          # fallback generic name
        "subj_short": None,    # Subject Short Form
        "subj_full": None,     # Subject Full Form
        "faculty": None,
        "type": None,
    }
    for c in df.columns:
        lc = str(c).strip().lower()
        if col_map["code"] is None and ("subject code" in lc or lc == "code"):
            col_map["code"] = c
        if col_map["subj_short"] is None and ("subject short" in lc or lc == "short" or lc == "subject short form"):
            col_map["subj_short"] = c
        if col_map["subj_full"] is None and ("subject full" in lc or lc == "full" or lc == "subject full form"):
            col_map["subj_full"] = c
        if col_map["name"] is None and lc in ("subject", "name"):
            col_map["name"] = c
        if col_map["faculty"] is None and ("faculty coordinator" in lc or "faculty" in lc):
            col_map["faculty"] = c
        if col_map["type"] is None and ("subject type" in lc or "type" in lc):
            col_map["type"] = c

    missing_cols = [k for k, v in col_map.items() if v is None]
    if missing_cols:
        st.error(f"Could not detect required columns from the sheet: {', '.join(missing_cols)}")
        return {}

    # Build faculties and subjects
    faculties_set = set()
    subjects: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        # Prefer Subject Short Form, then generic name, then full form
        subj_name_candidates = [
            col_map.get("subj_short"),
            col_map.get("name"),
            col_map.get("subj_full"),
        ]
        subj_name_val = ""
        for cand in subj_name_candidates:
            if cand is not None and pd.notna(row[cand]) and str(row[cand]).strip():
                subj_name_val = str(row[cand]).strip()
                break
        subj_name = subj_name_val
        subj_code = str(row[col_map["code"]]).strip() if pd.notna(row[col_map["code"]]) else subj_name
        subj_type_raw = str(row[col_map["type"]]).strip().lower() if pd.notna(row[col_map["type"]]) else "theory"
        is_practical = "prac" in subj_type_raw
        faculty_info = _parse_faculty_divisions(row[col_map["faculty"]])

        # Map division -> faculty name using tags, fallback to first listed name
        division_to_faculty: Dict[str, str] = {}
        for fname, divs in faculty_info:
            faculties_set.add(fname.strip())
            for d in divs:
                division_to_faculty[d] = fname.strip()
        fallback_faculty = faculty_info[0][0].strip() if faculty_info else "TBD Faculty"
        if not faculty_info:
            faculties_set.add(fallback_faculty)

        for d in divisions:
            fac = division_to_faculty.get(d, fallback_faculty)
            subjects.append({
                "name": f"{subj_name} ({d})",
                "code": f"{subj_code}-{d}",
                "faculty": fac,
                "sessions_per_week": int(practical_sessions_per_week if is_practical else theory_sessions_per_week),
                "duration_minutes": int(practical_slot if is_practical else theory_slot),
                "preferred_room": None,
            })

    # Assemble config
    selected_days = []
    for day, is_sel in zip(["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"], [monday, tuesday, wednesday, thursday, friday, saturday, sunday]):
        if is_sel:
            selected_days.append(day)

    cfg: Dict[str, Any] = {
        "num_timetables": int(num_timetables),
        "timetable_names": [n.strip() for n in timetable_names_raw.split(",") if n.strip()],
        "working_days": int(working_days),
        "selected_days": selected_days,
        "day_start": _to_24h(start_hour, start_ampm),
        "day_end": _to_24h(end_hour, end_ampm),
        "lecture_slot_length_minutes": int(min(theory_slot, practical_slot)),
        # rooms
        "rooms": ([{"name": r.strip()} for r in theory_rooms_text.splitlines() if r.strip()] +
                   [{"name": r.strip()} for r in practical_rooms_text.splitlines() if r.strip()]),
        "faculties": [{"name": f} for f in sorted(faculties_set)],
        "subjects": subjects,
        "attempts_per_timetable": 200,
        "max_overall_attempts": 1000,
    }
    return cfg


def build_config_via_form() -> Dict[str, Any]:
    # Subject count outside form for immediate updates
    st.subheader("Basic Settings")
    subj_count = st.number_input("Number of subjects", min_value=1, value=3, step=1, key="subject_count")
    
    with st.form("config_form"):
        st.subheader("Configuration Details")
        num_timetables = st.number_input("Number of timetables", min_value=1, value=2, step=1)
        timetable_names_raw = st.text_input(
            "Timetable names (comma-separated, optional)", value="A, B"
        ).strip()
        st.write("Select working days:")
        col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
        with col1:
            monday = st.checkbox("Monday", value=True)
        with col2:
            tuesday = st.checkbox("Tuesday", value=True)
        with col3:
            wednesday = st.checkbox("Wednesday", value=True)
        with col4:
            thursday = st.checkbox("Thursday", value=True)
        with col5:
            friday = st.checkbox("Friday", value=True)
        with col6:
            saturday = st.checkbox("Saturday", value=False)
        with col7:
            sunday = st.checkbox("Sunday", value=False)
        
        # Calculate working days count
        working_days = sum([monday, tuesday, wednesday, thursday, friday, saturday, sunday])
        st.write("Day start time:")
        col_start_hour, col_start_ampm = st.columns([1, 1])
        with col_start_hour:
            start_hour = st.selectbox("Hour", options=list(range(1, 13)), index=8)  # 9am
        with col_start_ampm:
            start_ampm = st.selectbox("AM/PM", options=["am", "pm"], index=0)

        st.write("Day end time:")
        col_end_hour, col_end_ampm = st.columns([1, 1])
        with col_end_hour:
            end_hour = st.selectbox("Hour", options=list(range(1, 13)), index=4, key="end_hour")  # 5pm
        with col_end_ampm:
            end_ampm = st.selectbox("AM/PM", options=["am", "pm"], index=1, key="end_ampm")
        slot_len = st.number_input("Lecture slot length (minutes)", min_value=10, value=50, step=5)
        st.caption("Recess is auto-placed near mid-day only if the day is ≥ 4 hours.")

        st.markdown("---")
        st.subheader("Rooms & Faculties")
        rooms_multiline = st.text_area(
            "Rooms (one per line)",
            value="Room 101\nRoom 102",
            height=100,
        )
        faculties_multiline = st.text_area(
            "Faculties (one per line)",
            value="Prof. A\nProf. B",
            height=100,
        )

        st.markdown("---")
        st.subheader("Subjects")
        
        subjects: List[Dict[str, Any]] = []
        # Use the subject count from outside the form
        for i in range(int(subj_count)):
            with st.expander(f"Subject {i+1}", expanded=(i == 0)):
                name = st.text_input(f"Name #{i+1}", key=f"subj_name_{i}")
                code = st.text_input(f"Code #{i+1} (optional)", key=f"subj_code_{i}")
                faculty = st.text_input(f"Faculty #{i+1} (must match)", key=f"subj_fac_{i}")
                sessions = st.number_input(
                    f"Sessions/week #{i+1}", min_value=1, value=2, step=1, key=f"subj_sess_{i}"
                )
                duration = st.number_input(
                    f"Duration minutes per session #{i+1}", min_value=slot_len, value=slot_len, step=slot_len, key=f"subj_dur_{i}"
                )
                pref_room = st.text_input(f"Preferred room #{i+1} (optional)", key=f"subj_room_{i}")
                if name and faculty:
                    subjects.append(
                        {
                            "name": name,
                            "code": code or name,
                            "faculty": faculty.strip(),  # Trim whitespace
                            "sessions_per_week": int(sessions),
                            "duration_minutes": int(duration),
                            "preferred_room": (pref_room.strip() if pref_room else None),
                        }
                    )

        submitted = st.form_submit_button("Build configuration")
        if not submitted:
            return {}

    # Create list of selected day names
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    selected_days = []
    day_checks = [monday, tuesday, wednesday, thursday, friday, saturday, sunday]
    for i, is_selected in enumerate(day_checks):
        if is_selected:
            selected_days.append(day_names[i])
    
    # Convert dropdown selections to 24-hour strings for internal use
    from datetime import datetime
    def _to_24h(hour: int, ampm: str) -> str:
        try:
            dt = datetime.strptime(f"{hour}:00 {ampm.upper()}", "%I:%M %p")
            return dt.strftime("%H:%M")
        except Exception:
            return "09:00"  # fallback

    day_start_24 = _to_24h(start_hour, start_ampm)
    day_end_24 = _to_24h(end_hour, end_ampm)

    cfg: Dict[str, Any] = {
        "num_timetables": int(num_timetables),
        "timetable_names": [n.strip() for n in timetable_names_raw.split(",") if n.strip()],
        "working_days": int(working_days),
        "selected_days": selected_days,
        "day_start": day_start_24,
        "day_end": day_end_24,
        "lecture_slot_length_minutes": int(slot_len),
        # Recess auto-placement; no explicit config needed
        "rooms": [{"name": r.strip()} for r in rooms_multiline.splitlines() if r.strip()],
        "faculties": [{"name": f.strip()} for f in faculties_multiline.splitlines() if f.strip()],
        "subjects": subjects,
        "attempts_per_timetable": 200,
        "max_overall_attempts": 1000,
    }
    return cfg


def main():
    st.set_page_config(page_title="AI Timetable Generator", layout="wide")
    st.title("AI Timetable Generator (Streamlit UI)")
    st.caption("Upload a semester sheet or config JSON, or use the manual form.")

    with st.sidebar:
        st.header("Configuration")
        mode = st.radio("Build configuration via", options=["Upload Sheet", "Manual Form", "JSON"], index=0)
        uploaded_json = st.file_uploader("Upload config JSON", type=["json"], key="json_uploader") if mode == "JSON" else None
        output_to_disk = st.checkbox("Also save outputs to ./outputs", value=True)
        output_dir = st.text_input("Output directory", value="./outputs")

    # Start with any config saved in session
    config: Dict[str, Any] = st.session_state.get("config", {})
    if mode == "JSON" and uploaded_json is not None:
        try:
            config = json.load(uploaded_json)
            st.success("Loaded configuration from uploaded JSON.")
            st.session_state["config"] = config
        except Exception as e:
            st.error(f"Failed to load uploaded JSON: {e}")
    elif mode == "Upload Sheet":
        built_cfg = build_config_via_upload()
        if built_cfg:
            config = built_cfg
            st.success("Configuration built from uploaded sheet.")
            st.session_state["config"] = config
    else:
        built_cfg = build_config_via_form()
        if built_cfg:
            config = built_cfg
            st.success("Configuration built from form.")
            st.session_state["config"] = config

    if not config:
        st.info("Upload a JSON or build a config to proceed.")
        return

    # Basic validation
    missing = []
    if not config.get("rooms"):
        missing.append("rooms")
    if not config.get("faculties"):
        missing.append("faculties")
    if not config.get("subjects"):
        missing.append("subjects")

    col1, col2 = st.columns([1, 1])
    with col1:
        disabled = len(missing) > 0
        if disabled:
            st.warning(f"Missing required sections: {', '.join(missing)}")
        if st.button("Generate Timetables", type="primary", disabled=disabled):
            with st.spinner("Generating timetables..."):
                results = generate_multiple_timetables(config)
            if not results:
                st.error("Failed to generate any valid timetable. Try relaxing constraints or increasing attempts.")
                return
            st.session_state["results"] = results
            st.success("Generated timetables.")
    with col2:
        if st.button("Clear Config and Results"):
            st.session_state.pop("config", None)
            st.session_state.pop("results", None)
            st.rerun()

    if "results" not in st.session_state:
        return

    results = st.session_state["results"]

    for name, schedule in results.items():
        st.markdown(f"### Timetable: {name}")
        df = schedule_to_dataframe(schedule, config)
        st.dataframe(df, use_container_width=True)

        csv_bytes = dataframe_to_csv_bytes(df)
        json_bytes = schedule_to_json_bytes(schedule)

        c1, c2, c3 = st.columns([1, 1, 6])
        with c1:
            st.download_button(
                label="Download CSV",
                file_name=f"timetable_{name}.csv",
                data=csv_bytes,
                mime="text/csv",
            )
        with c2:
            st.download_button(
                label="Download JSON",
                file_name=f"timetable_{name}.json",
                data=json_bytes,
                mime="application/json",
            )

        if output_to_disk:
            try:
                os.makedirs(output_dir, exist_ok=True)
                csv_path = os.path.join(output_dir, f"timetable_{name}.csv")
                json_path = os.path.join(output_dir, f"timetable_{name}.json")
                # Save using existing helpers for consistent schema
                save_schedule_csv(schedule, csv_path)
                save_schedule_json(schedule, json_path)
                st.caption(f"Saved to {csv_path} and {json_path}")
            except Exception as e:
                st.warning(f"Could not save to disk: {e}")


if __name__ == "__main__":
    main()


