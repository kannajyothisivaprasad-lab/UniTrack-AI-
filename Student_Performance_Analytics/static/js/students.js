/**
 * Student Records Management & Pagination Controller
 */

let currentPage = 1;
let currentPerPage = 25;
let searchDebounceTimer = null;
let studentDetailModalInstance = null;

document.addEventListener('DOMContentLoaded', function () {
    const modalEl = document.getElementById('studentDetailModal');
    if (modalEl) {
        studentDetailModalInstance = new bootstrap.Modal(modalEl);
    }

    loadStudents();

    // Event Listeners
    document.getElementById('studentSearchInput').addEventListener('input', function () {
        clearTimeout(searchDebounceTimer);
        searchDebounceTimer = setTimeout(() => {
            currentPage = 1;
            loadStudents();
        }, 300);
    });

    document.getElementById('riskFilter').addEventListener('change', () => { currentPage = 1; loadStudents(); });
    document.getElementById('engagementFilter').addEventListener('change', () => { currentPage = 1; loadStudents(); });
    document.getElementById('courseFilter').addEventListener('change', () => { currentPage = 1; loadStudents(); });
    document.getElementById('perPageSelect').addEventListener('change', (e) => {
        currentPerPage = parseInt(e.target.value);
        currentPage = 1;
        loadStudents();
    });

    document.getElementById('resetFiltersBtn').addEventListener('click', function () {
        document.getElementById('studentSearchInput').value = '';
        document.getElementById('riskFilter').value = 'All';
        document.getElementById('engagementFilter').value = 'All';
        document.getElementById('courseFilter').value = 'All';
        currentPage = 1;
        loadStudents();
    });
});

async function loadStudents() {
    const search = document.getElementById('studentSearchInput').value;
    const risk = document.getElementById('riskFilter').value;
    const engagement = document.getElementById('engagementFilter').value;
    const course = document.getElementById('courseFilter').value;

    const params = new URLSearchParams({
        search: search,
        risk: risk,
        engagement: engagement,
        course: course,
        page: currentPage,
        per_page: currentPerPage
    });

    const tbody = document.getElementById('studentTableBody');
    tbody.innerHTML = `
        <tr>
            <td colspan="11" class="text-center py-5">
                <div class="loading-spinner"></div>
                <p class="text-muted small mt-2">Loading student records...</p>
            </td>
        </tr>
    `;

    try {
        const response = await fetch(`/api/students?${params.toString()}`);
        const result = await response.json();

        if (result.status === 'success') {
            renderStudentTable(result.students);
            renderPagination(result.pagination);
        } else {
            tbody.innerHTML = `<tr><td colspan="11" class="text-center text-danger py-4">${result.message}</td></tr>`;
        }
    } catch (error) {
        console.error('Error fetching students:', error);
        tbody.innerHTML = `<tr><td colspan="11" class="text-center text-danger py-4">Failed to load student records.</td></tr>`;
    }
}

function renderStudentTable(students) {
    const tbody = document.getElementById('studentTableBody');
    if (!students || students.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="11" class="text-center py-5 text-muted">
                    <i class="bi bi-search fs-2 d-block mb-2"></i>
                    No matching student records found.
                </td>
            </tr>
        `;
        return;
    }

    let rowsHtml = '';
    students.forEach(s => {
        // Risk badge class
        let riskClass = 'risk-low';
        if (s.Risk_Level === 'High Risk') riskClass = 'risk-high';
        else if (s.Risk_Level === 'Medium Risk') riskClass = 'risk-med';

        // Predicted Risk badge class
        let predRiskClass = 'risk-low';
        if (s.Predicted_Risk === 'High Risk') predRiskClass = 'risk-high';
        else if (s.Predicted_Risk === 'Medium Risk') predRiskClass = 'risk-med';

        // Dropout class
        const dropClass = s.Dropout === 'Yes' ? 'dropout-yes' : 'dropout-no';

        rowsHtml += `
            <tr>
                <td><strong>${s.Student_ID}</strong></td>
                <td><span class="badge bg-light text-dark border">${s.Course}</span></td>
                <td><span class="fw-semibold">${s.Logins}</span></td>
                <td>${s.Content_Reads}</td>
                <td>${s.Forum_Posts}</td>
                <td>${s.Quiz_Reviews}</td>
                <td><span class="fw-bold">${Number(s.Risk_Score).toFixed(2)}</span></td>
                <td><span class="risk-badge ${riskClass}">${s.Risk_Level}</span></td>
                <td><span class="risk-badge ${predRiskClass}"><i class="bi bi-cpu me-1"></i>${s.Predicted_Risk}</span></td>
                <td><span class="${dropClass}">${s.Dropout}</span></td>
                <td class="text-end">
                    <button class="btn btn-outline-custom btn-sm py-1 px-2" onclick="viewStudentDetail('${s.Student_ID}')" title="View Student Deep Profile">
                        <i class="bi bi-eye"></i> Details
                    </button>
                </td>
            </tr>
        `;
    });

    tbody.innerHTML = rowsHtml;
}

function renderPagination(pagination) {
    const { page, total_pages, total_records, per_page } = pagination;
    currentPage = page;

    const start = total_records === 0 ? 0 : (page - 1) * per_page + 1;
    const end = Math.min(page * per_page, total_records);

    document.getElementById('recordsCountBadge').innerText = `${total_records.toLocaleString()} Students`;
    document.getElementById('paginationInfo').innerText = `Showing ${start} - ${end} of ${total_records.toLocaleString()} students`;

    const controls = document.getElementById('paginationControls');
    let html = '';

    // Previous Button
    html += `
        <li class="page-item ${page <= 1 ? 'disabled' : ''}">
            <button class="page-link" onclick="changePage(${page - 1})"><i class="bi bi-chevron-left"></i></button>
        </li>
    `;

    // Windowed Page Numbers
    const delta = 2;
    let range = [];
    for (let i = Math.max(2, page - delta); i <= Math.min(total_pages - 1, page + delta); i++) {
        range.push(i);
    }

    if (page - delta > 2) {
        range.unshift('...');
    }
    if (page + delta < total_pages - 1) {
        range.push('...');
    }

    range.unshift(1);
    if (total_pages > 1) {
        range.push(total_pages);
    }

    range.forEach(p => {
        if (p === '...') {
            html += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        } else {
            html += `
                <li class="page-item ${p === page ? 'active' : ''}">
                    <button class="page-link" onclick="changePage(${p})">${p}</button>
                </li>
            `;
        }
    });

    // Next Button
    html += `
        <li class="page-item ${page >= total_pages ? 'disabled' : ''}">
            <button class="page-link" onclick="changePage(${page + 1})"><i class="bi bi-chevron-right"></i></button>
        </li>
    `;

    controls.innerHTML = html;
}

function changePage(p) {
    currentPage = p;
    loadStudents();
}

async function viewStudentDetail(studentId) {
    if (!studentDetailModalInstance) return;
    studentDetailModalInstance.show();

    const body = document.getElementById('modalStudentBody');
    body.innerHTML = `
        <div class="text-center py-5">
            <div class="loading-spinner"></div>
            <p class="text-muted small mt-2">Loading profile for ${studentId}...</p>
        </div>
    `;

    try {
        const response = await fetch(`/api/students/${studentId}`);
        const result = await response.json();

        if (result.status === 'success') {
            const s = result.student;
            document.getElementById('studentDetailModalLabel').innerText = `Student ${s.Student_ID}`;
            document.getElementById('modalStudentSub').innerText = `${s.Course} Department | Age: ${s.Age} | Gender: ${s.Gender}`;

            let riskBadge = s.Risk_Level === 'High Risk' ? 'risk-high' : (s.Risk_Level === 'Medium Risk' ? 'risk-med' : 'risk-low');
            let predRiskBadge = s.Predicted_Risk === 'High Risk' ? 'risk-high' : (s.Predicted_Risk === 'Medium Risk' ? 'risk-med' : 'risk-low');

            body.innerHTML = `
                <!-- Top Status Banner -->
                <div class="row g-3 mb-4">
                    <div class="col-md-3 col-6">
                        <div class="p-3 bg-light rounded-3 text-center border">
                            <span class="d-block small text-muted">Risk Score</span>
                            <span class="fs-4 fw-bold text-dark-blue">${Number(s.Risk_Score).toFixed(2)}</span>
                        </div>
                    </div>
                    <div class="col-md-3 col-6">
                        <div class="p-3 bg-light rounded-3 text-center border">
                            <span class="d-block small text-muted">Actual Risk</span>
                            <span class="risk-badge ${riskBadge} mt-1">${s.Risk_Level}</span>
                        </div>
                    </div>
                    <div class="col-md-3 col-6">
                        <div class="p-3 bg-light rounded-3 text-center border">
                            <span class="d-block small text-muted">Predicted Risk</span>
                            <span class="risk-badge ${predRiskBadge} mt-1">${s.Predicted_Risk}</span>
                        </div>
                    </div>
                    <div class="col-md-3 col-6">
                        <div class="p-3 bg-light rounded-3 text-center border">
                            <span class="d-block small text-muted">Dropout Probability</span>
                            <span class="${s.Dropout === 'Yes' ? 'dropout-yes' : 'dropout-no'} d-inline-block mt-1">${s.Dropout}</span>
                        </div>
                    </div>
                </div>

                <!-- Learning Activity Metrics -->
                <h6 class="fw-bold text-dark-blue mb-3"><i class="bi bi-activity text-primary me-2"></i>Learning Activity Metrics</h6>
                <div class="row g-3 mb-4">
                    <div class="col-md-3 col-6">
                        <div class="p-2 px-3 border rounded-3 bg-white">
                            <span class="small text-muted d-block">Logins</span>
                            <span class="fw-bold fs-5 text-primary">${s.Logins}</span>
                        </div>
                    </div>
                    <div class="col-md-3 col-6">
                        <div class="p-2 px-3 border rounded-3 bg-white">
                            <span class="small text-muted d-block">Content Reads</span>
                            <span class="fw-bold fs-5 text-success">${s.Content_Reads}</span>
                        </div>
                    </div>
                    <div class="col-md-3 col-6">
                        <div class="p-2 px-3 border rounded-3 bg-white">
                            <span class="small text-muted d-block">Forum Posts</span>
                            <span class="fw-bold fs-5 text-warning">${s.Forum_Posts}</span>
                        </div>
                    </div>
                    <div class="col-md-3 col-6">
                        <div class="p-2 px-3 border rounded-3 bg-white">
                            <span class="small text-muted d-block">Quiz Reviews</span>
                            <span class="fw-bold fs-5 text-purple">${s.Quiz_Reviews}</span>
                        </div>
                    </div>
                </div>

                <!-- Assignment Timeliness -->
                <h6 class="fw-bold text-dark-blue mb-3"><i class="bi bi-clock-history text-primary me-2"></i>Assignment Submissions & Lateness</h6>
                <div class="row g-3 mb-4">
                    <div class="col-sm-3 col-6">
                        <div class="p-2 border rounded-3 text-center ${s.Assignment1_Late ? 'bg-danger-subtle text-danger' : 'bg-success-subtle text-success'}">
                            <span class="small d-block">Assignment 1</span>
                            <strong>${s.Assignment1_Late ? 'Late' : 'On-Time'}</strong>
                        </div>
                    </div>
                    <div class="col-sm-3 col-6">
                        <div class="p-2 border rounded-3 text-center ${s.Assignment2_Late ? 'bg-danger-subtle text-danger' : 'bg-success-subtle text-success'}">
                            <span class="small d-block">Assignment 2</span>
                            <strong>${s.Assignment2_Late ? 'Late' : 'On-Time'}</strong>
                        </div>
                    </div>
                    <div class="col-sm-3 col-6">
                        <div class="p-2 border rounded-3 text-center ${s.Assignment3_Late ? 'bg-danger-subtle text-danger' : 'bg-success-subtle text-success'}">
                            <span class="small d-block">Assignment 3</span>
                            <strong>${s.Assignment3_Late ? 'Late' : 'On-Time'}</strong>
                        </div>
                    </div>
                    <div class="col-sm-3 col-6">
                        <div class="p-2 border rounded-3 text-center bg-light">
                            <span class="small d-block">Avg Time</span>
                            <strong>${s.Avg_Assignment_Time} hrs</strong>
                        </div>
                    </div>
                </div>

                <!-- Model Predictions & Prescriptive Suggestion -->
                <h6 class="fw-bold text-dark-blue mb-2"><i class="bi bi-lightbulb-fill text-warning me-2"></i>Prescriptive Recommendation</h6>
                <div class="alert alert-primary d-flex align-items-center gap-3 mb-0 border-primary-subtle">
                    <i class="bi bi-chat-quote-fill fs-3 text-primary"></i>
                    <div>
                        <div class="fw-bold mb-1">Tailored Suggestion:</div>
                        <div class="text-dark">${s.Suggestion_New || s.Suggestion}</div>
                    </div>
                </div>
            `;
        } else {
            body.innerHTML = `<div class="alert alert-danger">${result.message}</div>`;
        }
    } catch (e) {
        body.innerHTML = `<div class="alert alert-danger">Error retrieving student profile.</div>`;
    }
}
