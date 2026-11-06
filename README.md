# 🎓 UniTrack AI – Multi-University Management & Student Performance Analytics System

UniTrack AI is an enterprise-grade, modern, responsive multi-university management and student performance analytics platform. Engineered with a secure multi-tenant architecture, role-based access control (RBAC), supervised machine learning benchmarking, and explainable student risk prediction.

---

## 🏛️ 1. Multi-University Architecture & Access Hierarchy

UniTrack AI enforces strict multi-tenant data separation. Every university-owned record contains a `university_id`, derived strictly from authenticated server-side sessions—client-supplied tenant IDs are never trusted.

```
                              ┌────────────────────────────────────────┐
                              │         PLATFORM SUPER ADMIN           │
                              │  - Fleet Governance & Approvals       │
                              │  - Platform KPIs & Global Audit Trail  │
                              └──────────────────┬─────────────────────┘
                                                 │
                   ┌─────────────────────────────┴─────────────────────────────┐
                   ▼                                                           ▼
    ┌─────────────────────────────┐                             ┌─────────────────────────────┐
    │     UNIVERSITY ADMIN A      │                             │     UNIVERSITY ADMIN B      │
    │  Apex Institute (UNI-APEX)  │                             │  Pacific State (UNI-PACIFIC)│
    │  - Depts, Sections, Staff   │                             │  - Strict Data Isolation    │
    │  - Students, Fees, Marks    │                             │  - Isolated Dashboards      │
    └──────────────┬──────────────┘                             └──────────────┬──────────────┘
                   ▼                                                           ▼
    ┌─────────────────────────────┐                             ┌─────────────────────────────┐
    │      UNIVERSITY STAFF A     │                             │      UNIVERSITY STAFF B     │
    │  - Daily Attendance         │                             │  - Marks & Exams            │
    │  - Coursework Grading       │                             │  - Student Dossiers         │
    └─────────────────────────────┘                             └─────────────────────────────┘
```

### Access Levels:
1. **Platform Super Admin**:
   - Manage all registered universities across the platform.
   - Review, approve, or reject new institutional registrations.
   - Activate, suspend, or deactivate institutional access.
   - Inspect global platform statistics and the centralized security audit trail.
2. **University Admin**:
   - Bound to a unique institutional identifier (e.g., `UNI-APEX`).
   - Manage departments, sections, faculty staff, and enrolled learners.
   - Provision staff accounts with granular module-level permissions.
   - Oversee institutional fee collection and performance reports.
3. **University Staff**:
   - Access only modules granted by the university admin (`students`, `attendance`, `marks`, `assignments`, `fees`, `achievements`, `analytics`).
   - Input daily attendance, grade examinations, and post assignments.
   - Review explainable AI risk assessments for assigned students.

---

## 🚀 2. Pre-Configured Demo Credentials

The database is pre-seeded with realistic institutional demo datasets ready for immediate evaluation:

| Role | Institution | Email Address | Password | Capabilities |
| :--- | :--- | :--- | :--- | :--- |
| **Platform Super Admin** | Central Platform HQ | `admin@unitrack.ai` | `Admin@123` | Fleet governance, institutional approvals, platform audit logs |
| **University Admin** | Apex Institute of Tech (`UNI-APEX`) | `admin@apex.edu` | `ApexAdmin@123` | Full institution management, staff provisioning, fee operations |
| **University Staff** | Apex Institute of Tech (`UNI-APEX`) | `prof.sharma@apex.edu` | `Staff@123` | Attendance entry, student grading, assignments, achievements |
| **University Admin** | Pacific State Univ (`UNI-PACIFIC`) | `admin@pacific.edu` | `PacificAdmin@123` | Independent isolated institution, isolated students & fees |
| **Pending University** | Nova Global Univ (`UNI-NOVA`) | `admin@novaglobal.edu` | `NovaAdmin@123` | Pending approval; login blocked until Super Admin approves |

---

## 💻 3. Windows Installation & Quick Start

### Prerequisites
- Python 3.10, 3.11, or 3.12 installed on Windows.
- Standard Command Prompt or Windows PowerShell.

### Step 1: Open Terminal in Project Directory
```powershell
cd "c:\Users\jyoth\Downloads\STUDENT PERFORAMANES"
```

### Step 2: (Optional) Create & Activate Virtual Environment
```powershell
python -m venv venv
venv\Scripts\activate
```

### Step 3: Install Required Dependencies
```powershell
pip install -r requirements.txt
```

### Step 4: Run the Application
```powershell
python run_app.py
```

Open your browser and navigate to:
```
http://127.0.0.1:5000
```
*(Use the Quick Demo Credentials on the login screen for one-click access!)*

---

## 🧪 4. Automated Test Suite Execution

A comprehensive automated test suite is included in `tests/`. It proves:
- University A cannot access University B students (direct URL manipulation returns `403 Forbidden`).
- University A cannot view University B fees or attendance.
- University A data exports are strictly tenant-isolated.
- Staff accounts are blocked from accessing admin-only pages.
- Suspended and pending universities cannot log in.
- Automatic fee math (`Pending = Total - Paid`) and marks calculation (`Total`, `%`, `Pass/Fail`).
- Super Admin approval lifecycle enables pending universities.
- Spreadsheet formula injection sanitization (CWE-1236).

### Run Tests:
```powershell
python -m unittest discover tests
```
*Expected Output: `Ran 13 tests in ~1.5s - OK`*

---

## 📦 5. Core System Modules & Functional Highlights

### 1. Student Management & 360° Comprehensive Dossiers
- Comprehensive fields: Student ID, Full Name, Email, Phone, Department, Section, Academic Year, Semester, Enrollment Status, Gender, Age.
- Search by Student ID or Name, with department, section, and status filters.
- **Student 360° Dossier (`/students/<id>`)**: Displays unified timeline including personal information, academic marks history, attendance ledger, fee payments, coursework assignments, honors/achievements, and explainable AI risk indicators.

### 2. Daily Attendance & Optional Facial Verification
- Batch daily attendance sheet by department and section.
- Automatic attendance percentage calculation and **Low Attendance Alerts Watchlist (<75%)**.
- Attendance correction workflow with mandatory change reason and audit ledger.
- **Optional Facial Verification Module**: Disabled by default. Features informed consent opt-in, anti-spoofing/liveness verification, AES-256 encrypted in-memory embeddings, a 30-day telemetry retention policy, and an unpenalized manual fallback.

### 3. Academic Performance (Marks & Examinations)
- Entry form for Midterms, Finals, Quizzes, Labs, and Internals.
- Automatic real-time calculation: Total Marks, Percentage, Grade (O, A+, A, B+, B, C, F), and Pass/Fail status.
- Dedicated **Honors Top Performers List (≥85%)** and **Remedial Watchlist (<40%)**.

### 4. Curriculum Assignment Management
- Faculty assignment creation with due dates, descriptions, and maximum points.
- Real-time submission tracking: Completed, Pending, Missing, Late.
- Student-level scoring and qualitative feedback.

### 5. Tuition Fee Management & Formula Verification
- Automatically computes: `Pending Fee = Total Fee - Paid Amount`.
- Cohort segmentation: Fully Paid, Partially Paid, and Pending Fee accounts.
- Department-level revenue recovery rate breakdown.
- **Security Compliance**: Strictly zero storage of sensitive credit card numbers or banking passwords. All payments tracked via verified receipt reference numbers.

### 6. Institutional Achievements & Honors
- Track student triumphs across Hackathons, Technical Competitions, Certifications, Sports, Academic Awards, and Workshops.
- Automatically highlighted on individual student dossiers.

### 7. CSV & Excel Data Management Hub
- Batch onboarding for student rosters, attendance, marks, and fee records.
- Preview spreadsheet data with automated duplicate removal, missing value detection, and column header verification.
- Protected against **CSV / Excel Formula Injection (CWE-1236)**.
- Secure exports strictly bounded to the active tenant.

### 8. AI Student Risk Prediction & Model Benchmarking
- Multi-factor risk engine analyzing attendance deficits, academic failures, assignment punctuality, and LMS engagement.
- Categorizes students into **Low Risk**, **Medium Risk**, and **High Risk** with human-readable reasoning factors.
- **Supervised ML Model Benchmark Report (`/settings`)**: Rigorously evaluates 4 supervised algorithms (**Logistic Regression, Random Forest, Decision Tree, Gradient Boosting**) on 2,500 authentic labeled student records with 80:20 holdout testing, computing real Accuracy, Precision, Recall, F1-Scores, and Confusion Matrices without synthetic numbers.
- Decision-support indicator disclaimer enforced across all reports.

### 9. Interactive Multi-Tenant Executive Dashboard
- 9 Top KPI cards: Total Students, Total Staff, Present Today, Average Attendance %, Pass %, Failed Students, High-Risk Students, Total Fee Collection ($), Pending Fees ($).
- 8 responsive Chart.js visual analyses: Department Student Count, Section Performance, Subject Pass/Fail, Attendance Trajectory, Fee Collection vs Pending, Assignment Completion, Risk Distribution, and Semester Performance.
- Dynamic filtering by Academic Year, Department, Section, and Date.

---

## 🔒 6. Security & Production Architecture

- **Session Security**: Secure, HttpOnly, SameSite=Lax session cookies.
- **CSRF Defense**: Per-session cryptographic tokens validated on all mutating HTTP requests.
- **Rate Limiting & Lockout**: Automatic 15-minute account lockout after 5 consecutive failed login attempts.
- **Audit Logging**: All administrative, authentication, and state-mutating actions recorded in `audit_logs` table with client IP and timestamps.
- **Database Scalability**: Embedded SQLite out-of-the-box (with WAL mode enabled for high concurrency), with seamless zero-code-change migration to PostgreSQL via `DATABASE_URL`.

---

## 📄 License
Academic & Enterprise Multi-Tenant System – Built with Flask, Pandas, Scikit-Learn, and Bootstrap 5.
#   U n i T r a c k - A I -  
 