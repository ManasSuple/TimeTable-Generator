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


