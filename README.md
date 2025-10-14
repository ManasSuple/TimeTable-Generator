🧠 AI-Powered TimeTable Generator

---
🚀 Overview

The AI TimeTable Generator is a smart scheduling system that automatically generates optimized class timetables for educational institutions.
It eliminates the hassle of manual timetable creation by using logical constraints and automation to ensure no clashes, balanced subject distribution, and efficient faculty utilization.

---

🎯 Objective

This project was built to solve a real administrative challenge — the time-consuming and error-prone process of manually preparing college timetables.
The system intelligently maps subjects, classrooms, teachers, and time slots while ensuring smooth scheduling and minimal conflicts.

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

## ⚙️ Tech Stack

-**Backend**: Python (Flask / Core Logic with AI Automation)
-**Frontend**: Streamlit / Web-based Interface (if applicable — confirm if you used Streamlit or pure HTML/Flask UI)
-**Database**: SQLite3
-**Libraries**: NumPy, Pandas, Random, CSV, OS, Datetime
-**Environment**: Virtualenv (.venv)

---

## 🧩 Core Features

✅ Automated timetable generation based on subject–faculty mapping
✅ Conflict-free scheduling (no overlapping slots)
✅ Teacher-wise and class-wise timetable outputs
✅ Dynamic CSV input/output support for easy data handling
✅ Fast generation time compared to manual scheduling
✅ Scalable logic — can adapt to multiple departments or batch structures

---

## 🧠 How It Works

-Input Files:
  -Teacher and subject mapping (teachers.csv)
  -Class and slot details (class_details.csv)
-Algorithm Logic:
  -Reads data → applies constraints → runs AI-based logic → produces balanced schedules.
-Output:
  -Final timetable in .csv or .xlsx format.

---

## 📈 Key Highlights

-Designed, structured, and coded entire scheduling logic from scratch.
-Focused on algorithmic thinking, data structure handling, and constraint optimization.
-Built with scalability and reusability in mind — can easily integrate with a web dashboard or database.
-Demonstrates problem-solving skills, backend logic design, and clean Python coding practices.

##🧠 Future Improvements

-Integration with a React or Next.js dashboard for visual timetable management.
-Adding user authentication and role-based access for admins/teachers.
-Incorporating machine learning for pattern-based scheduling optimization.

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

## ✅ To Do / Roadmap

* Add timetable **visual grid view** (e.g. days × times)
* Support **drag & drop editing** in UI
* Conflict warnings (e.g. teacher overlap)
* Export in more formats (Excel, PDF)
* Add user authentication / save sessions

---
