/**
 * Performance Analytics & Feature Insights Controller
 */

let analyticsCharts = {};

document.addEventListener('DOMContentLoaded', function () {
    fetchAnalyticsData();
});

async function fetchAnalyticsData() {
    try {
        const response = await fetch('/api/analytics');
        const result = await response.json();

        if (result.status === 'success') {
            const data = result.data;
            renderFeatureImportance(data.feature_importance);
            renderAssignmentLateness(data.late_by_risk);
            renderCourseRiskMatrix(data.course_risk);
            renderAssignmentTime(data.avg_time_by_risk);
        } else {
            console.error('Failed to load analytics:', result.message);
        }
    } catch (e) {
        console.error('Error fetching analytics:', e);
    }
}

// 1. Feature Importance (SHAP / Tree-based)
function renderFeatureImportance(importanceObj) {
    const ctx = document.getElementById('featureImportanceChart').getContext('2d');
    if (analyticsCharts.fi) analyticsCharts.fi.destroy();

    const labels = Object.keys(importanceObj);
    const values = Object.values(importanceObj);

    analyticsCharts.fi = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Importance Weight (%)',
                data: values,
                backgroundColor: ['#2563EB', '#3B82F6', '#F59E0B', '#8B5CF6'],
                borderRadius: 8
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    beginAtZero: true,
                    grid: { color: '#F1F5F9' },
                    ticks: { callback: v => v + '%' }
                },
                y: {
                    grid: { display: false },
                    ticks: { font: { family: 'Plus Jakarta Sans', weight: '600' } }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: { label: ctx => ` Importance: ${ctx.raw}%` }
                }
            }
        }
    });
}

// 2. Assignment Lateness by Risk Level
function renderAssignmentLateness(lateData) {
    const ctx = document.getElementById('assignmentLatenessChart').getContext('2d');
    if (analyticsCharts.late) analyticsCharts.late.destroy();

    const tiers = ['High Risk', 'Medium Risk', 'Low Risk'];
    const a1 = tiers.map(t => lateData[t] ? (lateData[t].Assignment1_Late * 100).toFixed(1) : 0);
    const a2 = tiers.map(t => lateData[t] ? (lateData[t].Assignment2_Late * 100).toFixed(1) : 0);
    const a3 = tiers.map(t => lateData[t] ? (lateData[t].Assignment3_Late * 100).toFixed(1) : 0);

    analyticsCharts.late = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: tiers,
            datasets: [
                {
                    label: 'Assignment 1 Late %',
                    data: a1,
                    backgroundColor: '#EF4444',
                    borderRadius: 6
                },
                {
                    label: 'Assignment 2 Late %',
                    data: a2,
                    backgroundColor: '#F59E0B',
                    borderRadius: 6
                },
                {
                    label: 'Assignment 3 Late %',
                    data: a3,
                    backgroundColor: '#3B82F6',
                    borderRadius: 6
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    grid: { color: '#F1F5F9' },
                    ticks: { callback: v => v + '%' }
                },
                x: {
                    grid: { display: false },
                    ticks: { font: { family: 'Plus Jakarta Sans', weight: '600' } }
                }
            },
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { boxWidth: 12, font: { family: 'Plus Jakarta Sans' } }
                }
            }
        }
    });
}

// 3. Course Risk Profile Matrix
function renderCourseRiskMatrix(courseRisk) {
    const ctx = document.getElementById('courseRiskMatrixChart').getContext('2d');
    if (analyticsCharts.courseRisk) analyticsCharts.courseRisk.destroy();

    const courses = Object.keys(courseRisk);
    const highRisk = courses.map(c => courseRisk[c]['High Risk'] || 0);
    const medRisk = courses.map(c => courseRisk[c]['Medium Risk'] || 0);
    const lowRisk = courses.map(c => courseRisk[c]['Low Risk'] || 0);

    analyticsCharts.courseRisk = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: courses,
            datasets: [
                {
                    label: 'High Risk',
                    data: highRisk,
                    backgroundColor: '#EF4444',
                    borderRadius: 4
                },
                {
                    label: 'Medium Risk',
                    data: medRisk,
                    backgroundColor: '#F59E0B',
                    borderRadius: 4
                },
                {
                    label: 'Low Risk',
                    data: lowRisk,
                    backgroundColor: '#10B981',
                    borderRadius: 4
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    stacked: true,
                    grid: { display: false },
                    ticks: { font: { family: 'Plus Jakarta Sans', weight: '600' } }
                },
                y: {
                    stacked: true,
                    grid: { color: '#F1F5F9' }
                }
            },
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { boxWidth: 12, font: { family: 'Plus Jakarta Sans' } }
                }
            }
        }
    });
}

// 4. Average Assignment Time by Risk Level
function renderAssignmentTime(timeData) {
    const ctx = document.getElementById('assignmentTimeChart').getContext('2d');
    if (analyticsCharts.time) analyticsCharts.time.destroy();

    const tiers = ['High Risk', 'Medium Risk', 'Low Risk'];
    const values = tiers.map(t => timeData[t] || 0);

    analyticsCharts.time = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: tiers,
            datasets: [{
                label: 'Avg Completion Time (Hours)',
                data: values,
                backgroundColor: ['#DC2626', '#D97706', '#059669'],
                borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: '#F1F5F9' },
                    ticks: { callback: v => v + ' hrs' }
                },
                x: {
                    grid: { display: false },
                    ticks: { font: { family: 'Plus Jakarta Sans', weight: '600' } }
                }
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: { label: ctx => ` Time: ${ctx.raw} hours` }
                }
            }
        }
    });
}
