# TimeTable Generator

A Streamlit-based AI timetable generator.  
Generate multiple conflict-free class schedules automatically, preview them interactively in a browser, and export them as CSV / JSON.

---

## 🧩 Features

- Create multiple timetables in one go  
- Web UI using Streamlit  
- Downloadable schedules in CSV & JSON formats  
- Save outputs locally (optional)  
- Customizable configuration:
  - Working days, time range, slot lengths  
  - Rooms, faculties, subjects with session counts  
  - Preferred rooms, durations  
  - Recess settings  
- Backend scheduling logic (your `timetable.py`) to enforce constraints

---

## 📂 Repository Structure

```

TimeTable-Generator/
├── .venv/                     # (ignored in version control) Python virtual environment
├── outputs/                   # Saved outputs (CSV/JSON)
├── streamlit_app.py           # Main Streamlit UI application
├── timetable.py               # Scheduling logic / algorithm
├── requirements.txt
└── README.md                  # This file

````

---

## 🚀 Quick Start / Installation

> These steps assume you're using **Windows + PowerShell**. For macOS/Linux, replace activation commands accordingly.

1. **Clone the repo**  
   ```bash
   git clone https://github.com/ManasSuple/TimeTable-Generator.git
   cd TimeTable-Generator

````

2. **Remove any broken virtual env (if exists)**

   ```powershell
   Remove-Item -Recurse -Force .venv
   ```

3. **Create a new virtual environment**

   ```powershell
   python -m venv .venv
   ```

4. **Allow PowerShell script execution (once per session)**

   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   ```

5. **Activate the virtual environment**

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

   After this, your prompt should start with `(.venv)`.

6. **Install dependencies**

   ```powershell
   pip install -r requirements.txt
   ```

   *If `requirements.txt` is missing or incomplete, run:*

   ```powershell
   pip install streamlit pandas tabulate openpyxl
   ```

7. **Run the app**

   ```powershell
   streamlit run streamlit_app.py
   ```

   The app should open in your browser at `http://localhost:8501`.

---

## 🛠 Usage

1. Build or upload a configuration (rooms, faculties, subjects, etc.)
2. Press **Generate Timetables**
3. View the generated schedules in a table
4. Download as CSV or JSON
5. Optionally, check the `outputs/` folder for saved files

---

## 🧠 Customization & Tips

* The scheduling logic is in `timetable.py` — you can tweak the heuristics or constraints there
* If you add new dependencies (e.g. visualization libraries), update `requirements.txt`
* Consider caching heavy parts using `@st.cache_data` or `@st.cache_resource`
* Add sample config JSON files in a folder (like `examples/`) to help users get started

---

## 🎯 Example Screenshot / Preview

*(Replace this section with actual screenshots later)*

| Feature             | Preview                            |
| ------------------- | ---------------------------------- |
| Config form         | ![config-form](path/to/image1.png) |
| Generated timetable | ![timetable](path/to/image2.png)   |

---

## 🤝 Contributing

1. Fork the repository
2. Create a new branch (`git checkout -b feature/your-feature`)
3. Make changes, test thoroughly
4. Commit and push changes
5. Submit a pull request describing your modifications

Please follow PEP 8, write docstrings, and test edge cases.

---

## ℹ️ License & Acknowledgments

* You may include a license (MIT, Apache, etc.) — add `LICENSE` file
* Credit algorithm ideas or inspiration sources
* Thanks for using / contributing!

---

## ✅ To Do / Roadmap

* Add timetable **visual grid view** (e.g. days × times)
* Support **drag & drop editing** in UI
* Conflict warnings (e.g. teacher overlap)
* Export in more formats (Excel, PDF)
* Add user authentication / save sessions

---
