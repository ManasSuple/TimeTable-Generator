import json
import io
import os
from typing import Dict, List, Any
import streamlit as st
import pandas as pd

from timetable import (
    generate_multiple_timetables,
    save_schedule_csv,
    save_schedule_json,
)


def schedule_to_dataframe(schedule: List[Dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(schedule)
    if not df.empty:
        df = df.sort_values(by=["day", "start_time", "room", "subject_name"]).reset_index(drop=True)
    ordered_cols = ["day", "start_time", "end_time", "room", "subject_code", "subject_name", "faculty"]
    existing_cols = [c for c in ordered_cols if c in df.columns]
    return df[existing_cols]


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def schedule_to_json_bytes(schedule: List[Dict[str, Any]]) -> bytes:
    return json.dumps(schedule, indent=2).encode("utf-8")


def build_config_via_form() -> Dict[str, Any]:
    with st.form("config_form"):
        st.subheader("Basic Settings")
        num_timetables = st.number_input("Number of timetables", min_value=1, value=2, step=1)
        timetable_names_raw = st.text_input(
            "Timetable names (comma-separated, optional)", value="A, B"
        ).strip()
        st.write("Select working days:")
        col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
        with col1:
            monday = st.checkbox("Monday", value=True)
        with col2:
            tuesday = st.checkbox("Tueday", value=True)
        with col3:
            wednesday = st.checkbox("Wednesday", value=True)
        with col4:
            thursday = thursday = st.checkbox("Thursday", value=True)
        with col5:
            friday = st.checkbox("Friday", value=True)
        with col6:
            saturday = st.checkbox("Saturday", value=False)
        with col7:
            sunday = st.checkbox("Sunday", value=False)
        
        # Calculate working days count
        working_days = sum([monday, tuesday, wednesday, thursday, friday, saturday, sunday])
        day_start_input = st.text_input("Day start (12-hour, e.g., 9:00 am)", value="9:00 am")
        day_end_input = st.text_input("Day end (12-hour, e.g., 5:00 pm)", value="5:00 pm")
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
        subj_count = st.number_input("Number of subjects", min_value=1, value=3, step=1)
        subjects: List[Dict[str, Any]] = []
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
                            "faculty": faculty,
                            "sessions_per_week": int(sessions),
                            "duration_minutes": int(duration),
                            "preferred_room": (pref_room or None),
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
    
    # Convert 12-hour inputs to 24-hour strings for internal use
    from datetime import datetime
    def _to_24h(s: str) -> str:
        s = (s or "").strip()
        for fmt in ["%I:%M %p", "%I %p", "%H:%M"]:
            try:
                return datetime.strptime(s, fmt).strftime("%H:%M")
            except Exception:
                pass
        return s  # fallback as-is

    day_start_24 = _to_24h(day_start_input)
    day_end_24 = _to_24h(day_end_input)

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
    st.caption("Upload a config JSON or build one below, then generate conflict-free timetables.")

    with st.sidebar:
        st.header("Configuration")
        uploaded = st.file_uploader("Upload config JSON", type=["json"]) 
        st.markdown("Or build config via the form on the main page.")
        output_to_disk = st.checkbox("Also save outputs to ./outputs", value=True)
        output_dir = st.text_input("Output directory", value="./outputs")

    # Start with any config saved in session
    config: Dict[str, Any] = st.session_state.get("config", {})
    if uploaded is not None:
        try:
            config = json.load(uploaded)
            st.success("Loaded configuration from uploaded JSON.")
            st.session_state["config"] = config
        except Exception as e:
            st.error(f"Failed to load uploaded JSON: {e}")

    st.markdown("### Build a configuration (optional)")
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
        df = schedule_to_dataframe(schedule)
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


