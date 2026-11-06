import pandas as pd
import numpy as np

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
data = pd.read_csv("student_performance_2500.csv")

print(data.head())
print(data.info())
print(data.describe())
# selecting simple features
X_eng = data[['Logins', 'Content_Reads']]
y_eng = data['Engagement_Level']

# split data
X_train, X_test, y_train, y_test = train_test_split(X_eng, y_eng, test_size=0.2, random_state=1)

# create model
model_eng = RandomForestClassifier()

# train
model_eng.fit(X_train, y_train)

# predict
pred_eng = model_eng.predict(X_test)

# accuracy
print("Engagement Accuracy:", accuracy_score(y_test, pred_eng))
# features for risk
X_risk = data[['Logins', 'Content_Reads', 'Forum_Posts', 'Quiz_Reviews']]
y_risk = data['Risk_Level']

# split
X_train, X_test, y_train, y_test = train_test_split(X_risk, y_risk, test_size=0.2)

# model
model_risk = RandomForestClassifier()

# train
model_risk.fit(X_train, y_train)

# predict
pred_risk = model_risk.predict(X_test)

print("Risk Accuracy:", accuracy_score(y_test, pred_risk))
# simple logic: using risk score
X_drop = data[['Risk_Score']]
y_drop = data['Dropout']

X_train, X_test, y_train, y_test = train_test_split(X_drop, y_drop, test_size=0.2)

model_drop = RandomForestClassifier()
model_drop.fit(X_train, y_train)

pred_drop = model_drop.predict(X_test)

print("Dropout Accuracy:", accuracy_score(y_test, pred_drop))
def give_suggestion(risk):
    if risk == "High Risk":
        return "Attend classes regularly and complete assignments"
    elif risk == "Medium Risk":
        return "Try to improve your consistency"
    else:
        return "Good performance, keep it up"

data['Suggestion_New'] = data['Risk_Level'].apply(give_suggestion)

print(data[['Student_ID', 'Risk_Level', 'Suggestion_New']].head())
# using only few features (early stage)
X_early = data[['Logins', 'Content_Reads']]
y_early = data['Risk_Level']

X_train, X_test, y_train, y_test = train_test_split(X_early, y_early, test_size=0.2)

model_early = RandomForestClassifier()
model_early.fit(X_train, y_train)

pred_early = model_early.predict(X_test)

print("Early Prediction Accuracy:", accuracy_score(y_test, pred_early))
import shap

# train small model
model = RandomForestClassifier()
model.fit(X_risk, y_risk)

explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_risk)

shap.summary_plot(shap_values, X_risk)
data['Predicted_Engagement'] = model_eng.predict(X_eng)
data['Predicted_Risk'] = model_risk.predict(X_risk)
data['Predicted_Dropout'] = model_drop.predict(X_drop)
data['Predicted_Early_Risk'] = model_early.predict(X_early)

data.to_excel("student_dashboard_data.xlsx", index=False)
