/**
 * Interactive Machine Learning Prediction Controller
 * Connects prediction form to Flask ML inference adapter
 */

document.addEventListener('DOMContentLoaded', function () {
    setupInputSync('inputLogins', 'rangeLogins', 'loginsValLabel', ' logins');
    setupInputSync('inputContentReads', 'rangeContentReads', 'readsValLabel', ' reads');
    setupInputSync('inputForumPosts', 'rangeForumPosts', 'postsValLabel', ' posts');
    setupInputSync('inputQuizReviews', 'rangeQuizReviews', 'quizzesValLabel', ' reviews');
    setupInputSync('inputRiskScore', 'rangeRiskScore', 'riskScoreValLabel', '');

    const form = document.getElementById('predictionForm');
    form.addEventListener('submit', handlePredictionSubmit);
});

function setupInputSync(inputId, rangeId, labelId, suffix) {
    const input = document.getElementById(inputId);
    const range = document.getElementById(rangeId);
    const label = document.getElementById(labelId);

    if (!input || !range) return;

    range.addEventListener('input', function () {
        input.value = this.value;
        if (label) label.innerText = this.value + suffix;
    });

    input.addEventListener('input', function () {
        range.value = this.value;
        if (label) label.innerText = this.value + suffix;
    });
}

function fillPreset(type) {
    if (type === 'high_risk') {
        updateField('inputLogins', 'rangeLogins', 'loginsValLabel', 25, ' logins');
        updateField('inputContentReads', 'rangeContentReads', 'readsValLabel', 85, ' reads');
        updateField('inputForumPosts', 'rangeForumPosts', 'postsValLabel', 2, ' posts');
        updateField('inputQuizReviews', 'rangeQuizReviews', 'quizzesValLabel', 1, ' reviews');
        updateField('inputRiskScore', 'rangeRiskScore', 'riskScoreValLabel', 88.5, '');
    } else if (type === 'average') {
        updateField('inputLogins', 'rangeLogins', 'loginsValLabel', 145, ' logins');
        updateField('inputContentReads', 'rangeContentReads', 'readsValLabel', 400, ' reads');
        updateField('inputForumPosts', 'rangeForumPosts', 'postsValLabel', 22, ' posts');
        updateField('inputQuizReviews', 'rangeQuizReviews', 'quizzesValLabel', 4, ' reviews');
        updateField('inputRiskScore', 'rangeRiskScore', 'riskScoreValLabel', 53.5, '');
    } else if (type === 'top_performer') {
        updateField('inputLogins', 'rangeLogins', 'loginsValLabel', 270, ' logins');
        updateField('inputContentReads', 'rangeContentReads', 'readsValLabel', 720, ' reads');
        updateField('inputForumPosts', 'rangeForumPosts', 'postsValLabel', 42, ' posts');
        updateField('inputQuizReviews', 'rangeQuizReviews', 'quizzesValLabel', 8, ' reviews');
        updateField('inputRiskScore', 'rangeRiskScore', 'riskScoreValLabel', 22.0, '');
    }

    // Trigger auto predict on preset click
    handlePredictionSubmit(new Event('submit'));
}

function updateField(inputId, rangeId, labelId, val, suffix) {
    const input = document.getElementById(inputId);
    const range = document.getElementById(rangeId);
    const label = document.getElementById(labelId);

    if (input) input.value = val;
    if (range) range.value = val;
    if (label) label.innerText = val + suffix;
}

async function handlePredictionSubmit(e) {
    if (e && e.preventDefault) e.preventDefault();

    const btn = document.getElementById('predictBtn');
    const originalText = btn.innerHTML;
    btn.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Predicting...`;
    btn.disabled = true;

    const payload = {
        logins: parseFloat(document.getElementById('inputLogins').value),
        content_reads: parseFloat(document.getElementById('inputContentReads').value),
        forum_posts: parseFloat(document.getElementById('inputForumPosts').value),
        quiz_reviews: parseFloat(document.getElementById('inputQuizReviews').value),
        risk_score: parseFloat(document.getElementById('inputRiskScore').value)
    };

    try {
        const response = await fetch('/api/predict', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (result.status === 'success') {
            displayPredictionResults(result.data);
        } else {
            alert('Prediction error: ' + result.message);
        }
    } catch (error) {
        console.error('Inference error:', error);
        alert('Network error connecting to prediction API.');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

function displayPredictionResults(data) {
    // Hide placeholder and show content
    document.getElementById('resultPlaceholder').style.display = 'none';
    const content = document.getElementById('resultContent');
    content.style.display = 'block';

    // Status Badge
    document.getElementById('inferenceStatusBadge').innerHTML = `<i class="bi bi-cpu-fill"></i> Inference Completed`;

    // 1. Predicted Risk Level
    const elRisk = document.getElementById('resPredictedRisk');
    elRisk.innerText = data.predicted_risk;
    if (data.predicted_risk === 'High Risk') {
        elRisk.className = 'prediction-value-big text-danger';
    } else if (data.predicted_risk === 'Medium Risk') {
        elRisk.className = 'prediction-value-big text-warning';
    } else {
        elRisk.className = 'prediction-value-big text-success';
    }

    // 2. Predicted Engagement
    const elEng = document.getElementById('resPredictedEngagement');
    elEng.innerText = data.predicted_engagement;
    elEng.className = data.predicted_engagement === 'High' ? 'prediction-value-big text-primary' : 'prediction-value-big text-secondary';

    // 3. Predicted Dropout
    const elDrop = document.getElementById('resPredictedDropout');
    elDrop.innerText = data.predicted_dropout === 'Yes' ? 'Dropout Expected' : 'Retained (No)';
    elDrop.className = data.predicted_dropout === 'Yes' ? 'prediction-value-big text-danger' : 'prediction-value-big text-success';

    // 4. Predicted Early Risk
    const elEarly = document.getElementById('resPredictedEarlyRisk');
    elEarly.innerText = data.predicted_early_risk;
    if (data.predicted_early_risk === 'High Risk') elEarly.className = 'prediction-value-big text-danger';
    else if (data.predicted_early_risk === 'Medium Risk') elEarly.className = 'prediction-value-big text-warning';
    else elEarly.className = 'prediction-value-big text-success';

    // Suggestion
    document.getElementById('resSuggestion').innerText = data.suggestion;

    // Confidence Probabilities
    const probs = data.risk_probabilities || {};
    const pHigh = probs['High Risk'] || 0;
    const pMed = probs['Medium Risk'] || 0;
    const pLow = probs['Low Risk'] || 0;

    document.getElementById('probHighRisk').innerText = pHigh + '%';
    document.getElementById('barHighRisk').style.width = pHigh + '%';

    document.getElementById('probMediumRisk').innerText = pMed + '%';
    document.getElementById('barMediumRisk').style.width = pMed + '%';

    document.getElementById('probLowRisk').innerText = pLow + '%';
    document.getElementById('barLowRisk').style.width = pLow + '%';
}
