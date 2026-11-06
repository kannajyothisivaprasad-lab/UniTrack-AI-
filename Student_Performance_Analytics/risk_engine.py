"""
UniTrack AI - Explainable Student Risk Prediction & Model Evaluation Engine
Trains and benchmarks multiple supervised ML algorithms (Logistic Regression,
Random Forest, Decision Tree, Gradient Boosting) on real student datasets.
Provides explainable factor breakdowns and decision-support disclaimers.
"""

import os
import json
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
from sklearn.preprocessing import StandardScaler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, 'data', 'student_performance_2500.csv')
EVAL_REPORT_PATH = os.path.join(BASE_DIR, 'models', 'model_evaluation_report.json')


class StudentRiskEngine:
    def __init__(self):
        self.models = {}
        self.scaler = StandardScaler()
        self.evaluation_report = {}
        self.is_trained = False
        self.train_and_evaluate_all_models()

    def train_and_evaluate_all_models(self):
        """
        Trains and strictly evaluates four supervised algorithms on the real 2,500 labeled student dataset:
        1. Logistic Regression
        2. Random Forest Classifier
        3. Decision Tree Classifier
        4. Gradient Boosting Classifier
        Calculates real Accuracy, Precision, Recall, F1-Score and Confusion Matrix.
        """
        if not os.path.exists(DATA_PATH):
            return

        df = pd.read_csv(DATA_PATH)
        
        # Features for model training
        feature_cols = [
            'Logins', 'Content_Reads', 'Forum_Posts', 'Quiz_Reviews',
            'Assignment1_Late', 'Assignment2_Late', 'Assignment3_Late', 'Avg_Assignment_Time'
        ]
        X = df[feature_cols].copy()
        y = df['Risk_Level'].copy()

        # 80/20 train/test split with fixed seed for reproducibility
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.20, random_state=42, stratify=y
        )

        # Scale features for linear models
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        labels = ['Low Risk', 'Medium Risk', 'High Risk']

        classifiers = {
            'Logistic Regression': (
                LogisticRegression(max_iter=1000, random_state=42),
                X_train_scaled, X_test_scaled
            ),
            'Random Forest': (
                RandomForestClassifier(n_estimators=100, random_state=42),
                X_train, X_test
            ),
            'Decision Tree': (
                DecisionTreeClassifier(max_depth=6, random_state=42),
                X_train, X_test
            ),
            'Gradient Boosting': (
                GradientBoostingClassifier(n_estimators=100, random_state=42),
                X_train, X_test
            )
        }

        report = {
            'dataset_records': len(df),
            'training_records': len(X_train),
            'test_records': len(X_test),
            'features': feature_cols,
            'classes': labels,
            'models': {},
            'best_model': 'Random Forest'
        }

        best_f1 = -1
        best_name = 'Random Forest'

        for name, (clf, xtr, xte) in classifiers.items():
            clf.fit(xtr, y_train)
            preds = clf.predict(xte)
            self.models[name] = clf

            acc = float(accuracy_score(y_test, preds))
            prec = float(precision_score(y_test, preds, average='weighted', zero_division=0))
            rec = float(recall_score(y_test, preds, average='weighted', zero_division=0))
            f1 = float(f1_score(y_test, preds, average='weighted', zero_division=0))
            cm = confusion_matrix(y_test, preds, labels=labels).tolist()

            report['models'][name] = {
                'accuracy': round(acc * 100, 2),
                'precision': round(prec * 100, 2),
                'recall': round(rec * 100, 2),
                'f1_score': round(f1 * 100, 2),
                'confusion_matrix': cm
            }

            if f1 > best_f1:
                best_f1 = f1
                best_name = name

        report['best_model'] = best_name
        self.evaluation_report = report
        self.is_trained = True

        os.makedirs(os.path.dirname(EVAL_REPORT_PATH), exist_ok=True)
        with open(EVAL_REPORT_PATH, 'w') as f:
            json.dump(report, f, indent=2)

    def calculate_explainable_risk(self, attendance_pct, avg_marks, failed_count, missing_assignments, late_assignments, logins=50):
        """
        Calculates explainable risk score (0-100), risk tier, and human-readable reasoning factors.
        Risk score components:
        - Attendance deficit below 75%: up to 35 points
        - Academic failures & mark deficit below 60%: up to 35 points
        - Assignment missing / late rate: up to 20 points
        - Engagement & portal logins deficit: up to 10 points
        """
        reasons = []
        risk_score = 0.0

        # 1. Attendance Evaluation
        if attendance_pct < 60.0:
            deficit = (60.0 - attendance_pct) * 0.8 + 20.0
            risk_score += min(35.0, deficit)
            reasons.append(f"Critical low attendance: {attendance_pct:.1f}% (far below the 75% institutional requirement).")
        elif attendance_pct < 75.0:
            deficit = (75.0 - attendance_pct) * 1.2
            risk_score += min(20.0, deficit)
            reasons.append(f"Attendance warning: {attendance_pct:.1f}% is below the mandatory 75% threshold.")
        else:
            reasons.append(f"Satisfactory attendance record: {attendance_pct:.1f}%.")

        # 2. Academic Performance Evaluation
        if failed_count > 0:
            fail_penalty = failed_count * 15.0
            risk_score += min(35.0, fail_penalty)
            reasons.append(f"Academic deficiency: Failed {failed_count} subject(s) in examination evaluations.")
        elif avg_marks < 50.0:
            risk_score += 22.0
            reasons.append(f"Borderline marks average: {avg_marks:.1f}% is near failing threshold.")
        elif avg_marks < 65.0:
            risk_score += 10.0
            reasons.append(f"Moderate marks average: {avg_marks:.1f}%.")
        else:
            reasons.append(f"Strong academic standing: Average marks {avg_marks:.1f}%.")

        # 3. Assignment Completion Evaluation
        if missing_assignments > 0:
            asgn_penalty = missing_assignments * 8.0 + (late_assignments * 3.0)
            risk_score += min(20.0, asgn_penalty)
            reasons.append(f"Unfinished coursework: {missing_assignments} assignment(s) missing and {late_assignments} submitted late.")
        elif late_assignments > 1:
            risk_score += 6.0
            reasons.append(f"Punctuality concern: {late_assignments} assignments submitted past the deadline.")
        else:
            reasons.append("All assignments submitted timely.")

        # 4. LMS Engagement Evaluation
        if logins < 20:
            risk_score += 10.0
            reasons.append(f"Minimal LMS activity: Only {logins} portal sessions recorded.")
        elif logins < 60:
            risk_score += 5.0

        # Clamp risk score
        risk_score = round(min(100.0, max(0.0, risk_score)), 1)

        # Categorize
        if risk_score >= 65.0 or (failed_count >= 2 and attendance_pct < 70.0):
            risk_level = "High Risk"
            recommendation = "Immediate academic intervention required. Schedule one-on-one counseling, assign remedial tutoring, and notify department advisor."
        elif risk_score >= 35.0:
            risk_level = "Medium Risk"
            recommendation = "Monitored academic support. Recommend peer study groups, attendance recovery plan, and progress review within 14 days."
        else:
            risk_level = "Low Risk"
            recommendation = "Student is in good academic standing. Continue periodic check-ins and encourage advanced honors or competition participation."

        return {
            'risk_level': risk_level,
            'risk_score': risk_score,
            'reasons': reasons,
            'recommended_action': recommendation,
            'disclaimer': "Notice: AI risk scores are decision-support indicators only. Human institutional review and faculty assessment are strictly required before taking any academic or administrative action."
        }


# Global engine instance
risk_engine = StudentRiskEngine()
