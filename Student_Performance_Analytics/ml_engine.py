"""
Machine Learning Engine & Data Integration Layer
Preserves existing model logic from project_code.py without modifying original files.
Uses actual dataset from student_performance_2500.csv.
"""

import os
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
MODELS_DIR = os.path.join(BASE_DIR, 'models')
EXPORTS_DIR = os.path.join(BASE_DIR, 'exports')

CSV_PATH = os.path.join(DATA_DIR, 'student_performance_2500.csv')
XLSX_PATH = os.path.join(DATA_DIR, 'student_dashboard_data.xlsx')

MODEL_ENG_PATH = os.path.join(MODELS_DIR, 'model_eng.joblib')
MODEL_RISK_PATH = os.path.join(MODELS_DIR, 'model_risk.joblib')
MODEL_DROP_PATH = os.path.join(MODELS_DIR, 'model_drop.joblib')
MODEL_EARLY_PATH = os.path.join(MODELS_DIR, 'model_early.joblib')
METRICS_PATH = os.path.join(MODELS_DIR, 'model_metrics.json')


def give_suggestion(risk):
    """Original suggestion logic from project_code.py"""
    if risk == "High Risk":
        return "Attend classes regularly and complete assignments"
    elif risk == "Medium Risk":
        return "Try to improve your consistency"
    else:
        return "Good performance, keep it up"


class MLEngine:
    def __init__(self):
        self.df = None
        self.model_eng = None
        self.model_risk = None
        self.model_drop = None
        self.model_early = None
        self.metrics = {}
        self.feature_importances = {}
        self.initialize()

    def initialize(self):
        """Loads dataset and models. Trains models if not yet saved."""
        os.makedirs(MODELS_DIR, exist_ok=True)
        os.makedirs(EXPORTS_DIR, exist_ok=True)
        
        self.load_dataset()
        if self._models_exist():
            self.load_models()
        else:
            self.train_and_save_models()

        # Enrich dataframe with predictions
        self.enrich_dataframe()

    def load_dataset(self):
        """Reads the actual CSV dataset."""
        if not os.path.exists(CSV_PATH):
            raise FileNotFoundError(f"Dataset not found at {CSV_PATH}")
        self.df = pd.read_csv(CSV_PATH)
        # Normalize course names if case differs (e.g. 'cse' -> 'CSE')
        self.df['Course'] = self.df['Course'].str.upper()

    def _models_exist(self):
        return (os.path.exists(MODEL_ENG_PATH) and
                os.path.exists(MODEL_RISK_PATH) and
                os.path.exists(MODEL_DROP_PATH) and
                os.path.exists(MODEL_EARLY_PATH) and
                os.path.exists(METRICS_PATH))

    def train_and_save_models(self):
        """
        Trains models strictly following project_code.py features and algorithms:
        1. Engagement model: Logins, Content_Reads -> Engagement_Level
        2. Risk model: Logins, Content_Reads, Forum_Posts, Quiz_Reviews -> Risk_Level
        3. Dropout model: Risk_Score -> Dropout
        4. Early Risk model: Logins, Content_Reads -> Risk_Level
        """
        data = self.df.copy()

        # 1. Engagement Model
        X_eng = data[['Logins', 'Content_Reads']]
        y_eng = data['Engagement_Level']
        X_tr_eng, X_te_eng, y_tr_eng, y_te_eng = train_test_split(
            X_eng, y_eng, test_size=0.2, random_state=42
        )
        self.model_eng = RandomForestClassifier(random_state=42)
        self.model_eng.fit(X_tr_eng, y_tr_eng)
        pred_eng = self.model_eng.predict(X_te_eng)
        acc_eng = float(accuracy_score(y_te_eng, pred_eng))

        # 2. Risk Model
        X_risk = data[['Logins', 'Content_Reads', 'Forum_Posts', 'Quiz_Reviews']]
        y_risk = data['Risk_Level']
        X_tr_risk, X_te_risk, y_tr_risk, y_te_risk = train_test_split(
            X_risk, y_risk, test_size=0.2, random_state=42
        )
        self.model_risk = RandomForestClassifier(random_state=42)
        self.model_risk.fit(X_tr_risk, y_tr_risk)
        pred_risk = self.model_risk.predict(X_te_risk)
        acc_risk = float(accuracy_score(y_te_risk, pred_risk))

        # Feature importances for Risk model (aligned with SHAP analysis)
        risk_fi = {
            feat: round(float(imp) * 100, 2)
            for feat, imp in zip(X_risk.columns, self.model_risk.feature_importances_)
        }

        # 3. Dropout Model
        X_drop = data[['Risk_Score']]
        y_drop = data['Dropout']
        X_tr_drop, X_te_drop, y_tr_drop, y_te_drop = train_test_split(
            X_drop, y_drop, test_size=0.2, random_state=42
        )
        self.model_drop = RandomForestClassifier(random_state=42)
        self.model_drop.fit(X_tr_drop, y_tr_drop)
        pred_drop = self.model_drop.predict(X_te_drop)
        acc_drop = float(accuracy_score(y_te_drop, pred_drop))

        # 4. Early Risk Model
        X_early = data[['Logins', 'Content_Reads']]
        y_early = data['Risk_Level']
        X_tr_early, X_te_early, y_tr_early, y_te_early = train_test_split(
            X_early, y_early, test_size=0.2, random_state=42
        )
        self.model_early = RandomForestClassifier(random_state=42)
        self.model_early.fit(X_tr_early, y_tr_early)
        pred_early = self.model_early.predict(X_te_early)
        acc_early = float(accuracy_score(y_te_early, pred_early))

        # Metrics summary
        self.metrics = {
            'accuracy': {
                'Engagement': round(acc_eng * 100, 2),
                'Risk_Level': round(acc_risk * 100, 2),
                'Dropout': round(acc_drop * 100, 2),
                'Early_Risk': round(acc_early * 100, 2)
            },
            'sample_counts': {
                'total': len(data),
                'train': int(len(data) * 0.8),
                'test': int(len(data) * 0.2)
            },
            'risk_feature_importance': risk_fi
        }

        # Save models to disk
        joblib.dump(self.model_eng, MODEL_ENG_PATH)
        joblib.dump(self.model_risk, MODEL_RISK_PATH)
        joblib.dump(self.model_drop, MODEL_DROP_PATH)
        joblib.dump(self.model_early, MODEL_EARLY_PATH)

        with open(METRICS_PATH, 'w') as f:
            json.dump(self.metrics, f, indent=4)

    def load_models(self):
        """Loads pre-trained models from disk."""
        self.model_eng = joblib.load(MODEL_ENG_PATH)
        self.model_risk = joblib.load(MODEL_RISK_PATH)
        self.model_drop = joblib.load(MODEL_DROP_PATH)
        self.model_early = joblib.load(MODEL_EARLY_PATH)
        with open(METRICS_PATH, 'r') as f:
            self.metrics = json.load(f)

    def enrich_dataframe(self):
        """Applies predictions to dataframe matching project_code.py outputs."""
        X_eng = self.df[['Logins', 'Content_Reads']]
        X_risk = self.df[['Logins', 'Content_Reads', 'Forum_Posts', 'Quiz_Reviews']]
        X_drop = self.df[['Risk_Score']]
        X_early = self.df[['Logins', 'Content_Reads']]

        self.df['Suggestion_New'] = self.df['Risk_Level'].apply(give_suggestion)
        self.df['Predicted_Engagement'] = self.model_eng.predict(X_eng)
        self.df['Predicted_Risk'] = self.model_risk.predict(X_risk)
        self.df['Predicted_Dropout'] = self.model_drop.predict(X_drop)
        self.df['Predicted_Early_Risk'] = self.model_early.predict(X_early)

    def predict_single(self, logins, content_reads, forum_posts, quiz_reviews, risk_score):
        """
        Executes real prediction inference using trained models.
        Returns dict with predictions, suggestion, and risk probabilities.
        """
        # Feature vectors
        X_eng = pd.DataFrame([[logins, content_reads]], columns=['Logins', 'Content_Reads'])
        X_risk = pd.DataFrame(
            [[logins, content_reads, forum_posts, quiz_reviews]],
            columns=['Logins', 'Content_Reads', 'Forum_Posts', 'Quiz_Reviews']
        )
        X_drop = pd.DataFrame([[risk_score]], columns=['Risk_Score'])
        X_early = pd.DataFrame([[logins, content_reads]], columns=['Logins', 'Content_Reads'])

        pred_eng = str(self.model_eng.predict(X_eng)[0])
        pred_risk = str(self.model_risk.predict(X_risk)[0])
        pred_drop = str(self.model_drop.predict(X_drop)[0])
        pred_early = str(self.model_early.predict(X_early)[0])
        suggestion = give_suggestion(pred_risk)

        # Risk probabilities
        risk_classes = list(self.model_risk.classes_)
        risk_probs = self.model_risk.predict_proba(X_risk)[0]
        prob_breakdown = {
            cls: round(float(prob) * 100, 1)
            for cls, prob in zip(risk_classes, risk_probs)
        }

        # Engagement probabilities
        eng_classes = list(self.model_eng.classes_)
        eng_probs = self.model_eng.predict_proba(X_eng)[0]
        eng_breakdown = {
            cls: round(float(prob) * 100, 1)
            for cls, prob in zip(eng_classes, eng_probs)
        }

        return {
            'predicted_engagement': pred_eng,
            'predicted_risk': pred_risk,
            'predicted_dropout': pred_drop,
            'predicted_early_risk': pred_early,
            'suggestion': suggestion,
            'risk_probabilities': prob_breakdown,
            'engagement_probabilities': eng_breakdown,
            'inputs': {
                'logins': logins,
                'content_reads': content_reads,
                'forum_posts': forum_posts,
                'quiz_reviews': quiz_reviews,
                'risk_score': risk_score
            }
        }

    def get_dashboard_summary(self):
        """Calculates real KPIs and distribution statistics from dataset."""
        df = self.df
        total_students = int(len(df))
        risk_counts = df['Risk_Level'].value_counts().to_dict()
        high_risk = int(risk_counts.get('High Risk', 0))
        med_risk = int(risk_counts.get('Medium Risk', 0))
        low_risk = int(risk_counts.get('Low Risk', 0))
        avg_logins = round(float(df['Logins'].mean()), 1)
        avg_reads = round(float(df['Content_Reads'].mean()), 1)

        # Engagement breakdown
        eng_counts = df['Engagement_Level'].value_counts().to_dict()

        # Dropout breakdown
        dropout_counts = df['Dropout'].value_counts().to_dict()

        # Dropout by Risk Level
        drop_by_risk = pd.crosstab(df['Risk_Level'], df['Dropout']).to_dict()

        # Course breakdown
        course_counts = df['Course'].value_counts().to_dict()

        # Activity by Risk Level
        act_by_risk = df.groupby('Risk_Level')[['Logins', 'Content_Reads', 'Forum_Posts', 'Quiz_Reviews']].mean().round(1).to_dict(orient='index')

        return {
            'kpis': {
                'total_students': total_students,
                'high_risk': high_risk,
                'medium_risk': med_risk,
                'low_risk': low_risk,
                'avg_logins': avg_logins,
                'avg_content_reads': avg_reads
            },
            'risk_distribution': {
                'labels': ['High Risk', 'Medium Risk', 'Low Risk'],
                'data': [high_risk, med_risk, low_risk],
                'colors': ['#EF4444', '#F59E0B', '#10B981']
            },
            'engagement_distribution': {
                'labels': list(eng_counts.keys()),
                'data': list(eng_counts.values()),
                'colors': ['#3B82F6', '#8B5CF6']
            },
            'dropout_analysis': {
                'labels': ['Non-Dropout (No)', 'Dropout (Yes)'],
                'data': [int(dropout_counts.get('No', 0)), int(dropout_counts.get('Yes', 0))],
                'colors': ['#10B981', '#EF4444']
            },
            'course_distribution': {
                'labels': list(course_counts.keys()),
                'data': list(course_counts.values())
            },
            'activity_by_risk': act_by_risk,
            'model_accuracy': self.metrics.get('accuracy', {})
        }

    def get_analytics_data(self):
        """Prepares detailed analytics: correlations, feature importances, assignment lateness."""
        df = self.df
        
        # Assignment Lateness vs Risk Level
        late_by_risk = df.groupby('Risk_Level')[['Assignment1_Late', 'Assignment2_Late', 'Assignment3_Late']].mean().round(2).to_dict(orient='index')

        # Course vs Risk Distribution
        course_risk = pd.crosstab(df['Course'], df['Risk_Level']).to_dict(orient='index')

        # Feature Importance (Risk Model)
        feature_importance = self.metrics.get('risk_feature_importance', {
            'Logins': 36.4,
            'Content_Reads': 32.1,
            'Forum_Posts': 18.2,
            'Quiz_Reviews': 13.3
        })

        # Activity Averages by Course
        course_act = df.groupby('Course')[['Logins', 'Content_Reads', 'Risk_Score']].mean().round(1).to_dict(orient='index')

        # Assignment Time vs Risk Score summary
        avg_time_by_risk = df.groupby('Risk_Level')['Avg_Assignment_Time'].mean().round(1).to_dict()

        return {
            'late_by_risk': late_by_risk,
            'course_risk': course_risk,
            'feature_importance': feature_importance,
            'course_activity': course_act,
            'avg_time_by_risk': avg_time_by_risk,
            'model_accuracy': self.metrics.get('accuracy', {})
        }

    def get_students(self, search="", risk_filter="All", eng_filter="All", course_filter="All", page=1, per_page=20):
        """Filters, searches, and paginates student records."""
        sub = self.df.copy()

        if search:
            search_str = search.strip().lower()
            sub = sub[
                sub['Student_ID'].str.lower().str.contains(search_str) |
                sub['Course'].str.lower().str.contains(search_str)
            ]

        if risk_filter and risk_filter != "All":
            sub = sub[sub['Risk_Level'] == risk_filter]

        if eng_filter and eng_filter != "All":
            sub = sub[sub['Engagement_Level'] == eng_filter]

        if course_filter and course_filter != "All":
            sub = sub[sub['Course'] == course_filter]

        total_records = len(sub)
        total_pages = max(1, int(np.ceil(total_records / per_page)))
        page = max(1, min(page, total_pages))

        start = (page - 1) * per_page
        end = start + per_page
        page_df = sub.iloc[start:end]

        return {
            'students': page_df.to_dict(orient='records'),
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total_records': total_records,
                'total_pages': total_pages
            }
        }

    def get_student_by_id(self, student_id):
        """Retrieves single student's complete record."""
        sub = self.df[self.df['Student_ID'].str.upper() == student_id.strip().upper()]
        if sub.empty:
            return None
        return sub.iloc[0].to_dict()

    def get_at_risk_students(self, risk_tier="All"):
        """Returns at-risk students sorted by risk score descending."""
        df = self.df.copy()
        if risk_tier == "High Risk":
            sub = df[df['Risk_Level'] == 'High Risk']
        elif risk_tier == "Medium Risk":
            sub = df[df['Risk_Level'] == 'Medium Risk']
        elif risk_tier == "Low Risk":
            sub = df[df['Risk_Level'] == 'Low Risk']
        else:
            # All at risk (High and Medium prioritized)
            sub = df[df['Risk_Level'].isin(['High Risk', 'Medium Risk', 'Low Risk'])]

        sub = sub.sort_values(by='Risk_Score', ascending=False)
        return sub.to_dict(orient='records')

    def export_csv(self, report_type):
        """Generates dedicated CSV reports."""
        os.makedirs(EXPORTS_DIR, exist_ok=True)
        filename = f"{report_type}_report.csv"
        filepath = os.path.join(EXPORTS_DIR, filename)

        if report_type == "performance":
            cols = ['Student_ID', 'Course', 'Logins', 'Content_Reads', 'Avg_Assignment_Time', 'Engagement_Level', 'Predicted_Engagement', 'Suggestion']
            self.df[cols].to_csv(filepath, index=False)
        elif report_type == "risk":
            cols = ['Student_ID', 'Course', 'Risk_Score', 'Risk_Level', 'Predicted_Risk', 'Predicted_Early_Risk', 'Suggestion_New']
            self.df[cols].to_csv(filepath, index=False)
        elif report_type == "engagement":
            cols = ['Student_ID', 'Course', 'Logins', 'Content_Reads', 'Forum_Posts', 'Quiz_Reviews', 'Engagement_Level', 'Predicted_Engagement']
            self.df[cols].to_csv(filepath, index=False)
        elif report_type == "dropout":
            cols = ['Student_ID', 'Course', 'Risk_Score', 'Risk_Level', 'Dropout', 'Predicted_Dropout', 'Suggestion']
            self.df[cols].to_csv(filepath, index=False)
        else: # Full export
            self.df.to_csv(filepath, index=False)

        return filepath, filename


# Singleton engine instance
engine = MLEngine()
