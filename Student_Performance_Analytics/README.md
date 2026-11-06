# Predictive Analysis of Student Performance in Online Learning

A comprehensive, executive-grade Student Performance Analytics web application built using Python Flask, Scikit-Learn, and modern interactive frontend dashboards (Bootstrap 5, Chart.js).

This web platform integrates existing machine learning algorithms (`project_code.py`) and historical educational datasets (`student_performance_2500.csv` and `student_dashboard_data.xlsx`) without altering original model logic or generating synthetic data.

---

## 🌟 Key Application Features

1. **Executive Dashboard (`/` or `/dashboard`)**
   - 6 KPI summary cards: Total Students (2,500), High Risk, Medium Risk, Low Risk, Average Logins, Average Content Reads.
   - 6 Interactive Chart.js charts:
     - Student Risk Distribution (Doughnut)
     - Engagement Level Distribution (Doughnut)
     - Dropout Analysis (Pie)
     - Course-wise Student Distribution (Bar)
     - Learning Activity by Risk Tier (Grouped Bar)
     - Scikit-Learn Model Accuracy (Horizontal Bar)

2. **Student Records Directory (`/students`)**
   - Real-time search by Student ID (e.g. `STU1000`).
   - Dynamic filters: Risk Level (High, Medium, Low), Engagement Level, Course (CSE, ECE, EEE, IT).
   - Server-side windowed pagination (15, 25, 50, 100 records per page).
   - Interactive Student Deep Profile modal with full activity metrics, assignment timeliness breakdown, and tailored suggestions.

3. **Performance Analytics & Feature Insights (`/analytics`)**
   - Feature Importance analysis (SHAP & Random Forest weight breakdown).
   - Assignment lateness across Assignments 1, 2, and 3 by risk tier.
   - Cross-course risk matrix.
   - Average assignment completion times.

4. **Machine Learning Prediction Lab (`/prediction`)**
   - Real-time prediction form for 5 parameters:
     - `Logins`
     - `Content Reads`
     - `Forum Posts`
     - `Quiz Reviews`
     - `Risk Score`
   - Instant multi-target Random Forest inferences:
     - Predicted Engagement Level
     - Predicted Risk Level
     - Predicted Dropout Status
     - Predicted Early Risk Alert
     - Prescriptive Student Improvement Suggestion
     - Percentage confidence breakdown across risk tiers.
   - Interactive Quick-Test Presets: *High Risk Sample*, *Average Student*, *High Achiever*.

5. **At-Risk Student Intervention Portal (`/at-risk`)**
   - Dedicated prioritization page sorted by urgency and Risk Score.
   - Quick filter tabs: All Tiers, High Risk Only, Medium Risk Only, Low Risk Only.
   - Batch export for academic counselors.

6. **Academic Reports & Data Export Center (`/reports`)**
   - 4 specialized CSV reports with instant download:
     - Student Performance Report
     - Risk Analysis Report
     - Engagement Report
     - Dropout Report
   - Full Master CSV Export (all 22 attributes).

7. **System Settings & Model Inspection (`/settings`)**
   - Model parameters, accuracy logs, data pipeline status.
   - One-click model retraining trigger with instant feedback.

---

## 📁 Project Folder Structure

```
Student_Performance_Analytics/
│
├── app.py                      # Flask Application Server & API endpoints
├── ml_engine.py                # Machine Learning Engine & Data Integration Layer
├── requirements.txt            # Python dependencies
├── README.md                   # Complete documentation & run instructions
│
├── original_code/
│   └── project_code.py         # Original unmodified Python ML code
│
├── data/
│   ├── student_performance_2500.csv    # Master dataset (2,500 real records)
│   └── student_dashboard_data.xlsx    # Dashboard Excel dataset (22 columns)
│
├── powerbi/
│   └── original_dashboard.pbix # Original Power BI dashboard file
│
├── models/
│   ├── model_eng.joblib        # Trained Engagement Random Forest Model
│   ├── model_risk.joblib       # Trained Risk Level Random Forest Model
│   ├── model_drop.joblib       # Trained Dropout Random Forest Model
│   ├── model_early.joblib      # Trained Early Risk Random Forest Model
│   └── model_metrics.json      # Test set accuracy scores & feature weights
│
├── templates/
│   ├── base.html               # Base layout, left sidebar, and topbar
│   ├── dashboard.html          # Executive KPI cards & Chart.js charts
│   ├── students.html           # Searchable & filterable student directory
│   ├── analytics.html          # SHAP feature importance & analytics
│   ├── prediction.html         # Interactive ML prediction lab
│   ├── at_risk.html            # Dedicated at-risk student intervention portal
│   ├── reports.html            # 4 specialized reports & CSV downloads
│   └── settings.html           # Model configuration & pipeline status
│
├── static/
│   ├── css/
│   │   └── style.css           # Premium White & Blue design system
│   │
│   ├── js/
│   │   ├── dashboard.js        # Dashboard Chart.js controllers
│   │   ├── students.js         # Student table AJAX pagination & modal
│   │   ├── analytics.js        # Analytics charts & comparisons
│   │   └── prediction.js       # Prediction sliders & real-time inference
│   │
│   └── images/
│
└── exports/                    # Generated CSV report downloads
```

---

## 🚀 How to Run the Application in VS Code

### Step 1: Open Terminal in VS Code
Open your VS Code terminal (`Ctrl + ~` or `Terminal -> New Terminal`).

### Step 2: Navigate to Project Directory
```powershell
cd "c:\Users\jyoth\Downloads\STUDENT PERFORAMANES\Student_Performance_Analytics"
```

### Step 3: Install Required Dependencies
```powershell
python -m pip install -r requirements.txt
```

### Step 4: Start the Flask Web Application
```powershell
python app.py
```

### Step 5: Open in Your Browser
Open your browser and navigate to:
```
http://127.0.0.1:5000
```
or
```
http://localhost:5000
```

---

## 🔒 Data & Code Integrity Notice
- `project_code.py` remains 100% untouched and preserved in its original location as well as in `original_code/project_code.py`.
- No mock or synthetic records were created; all 2,500 records are loaded directly from the actual CSV dataset.
- All machine learning algorithms (Random Forest Classifier, train-test split, feature subsets, accuracy scoring) strictly follow the original specifications.
