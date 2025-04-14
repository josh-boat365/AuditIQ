document.addEventListener('DOMContentLoaded', function () {
    // DOM Elements
    const analyzeBtn = document.getElementById('analyzeBtn');
    const generateReportBtn = document.getElementById('generateReportBtn');
    const resultsSection = document.getElementById('resultsSection');
    const auditDataTextarea = document.getElementById('auditData');
    const executiveSummaryDiv = document.getElementById('executiveSummary');
    const detailedFindingsDiv = document.getElementById('detailedFindings');
    const severityChartCanvas = document.getElementById('severityChart');
    const branchChartCanvas = document.getElementById('branchChart');

    // Chart instances
    let severityChart = null;
    let branchChart = null;

    // Store analysis results
    let currentAnalysis = null;

    // Analyze Button Handler
    // In your analyze button click handler:
    analyzeBtn.addEventListener('click', async function () {
        const auditDataText = auditDataTextarea.value.trim();

        
        try {

            const auditData = JSON.parse(auditDataText);

            // Validate the nested structure
            if (!auditData.audit_report ?.exceptions) {
                showAlert('JSON must contain audit_report with exceptions array', 'danger');
                return;
            }
            // Validate JSON first
            try {
                JSON.parse(auditDataText);
            } catch (e) {
                showAlert('Invalid JSON format: ' + e.message, 'danger');
                return;
            }

            setLoadingState(analyzeBtn, true, 'Analyzing...');

            const response = await fetch('/analyze', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: auditDataText
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Analysis failed');
            }

            currentAnalysis = data;
            displayResults(data);
            resultsSection.classList.remove('d-none');

        } catch (error) {
            console.error('Analysis error:', error);
            showAlert(`Analysis failed: ${error.message}`, 'danger');

            // Show detailed error in console for debugging
            if (error.response) {
                console.error('Server response:', await error.response.json());
            }
        } finally {
            setLoadingState(analyzeBtn, false, 'Analyze Data');
        }
    });

    // Generate Report Button Handler
    generateReportBtn.addEventListener('click', async function () {
        if (!currentAnalysis) {
            showAlert('No analysis results available', 'warning');
            return;
        }

        try {
            setLoadingState(generateReportBtn, true, 'Generating...');

            const response = await fetch('/generate-report', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(currentAnalysis)
            });

            if (!response.ok) {
                throw new Error('Report generation failed');
            }

            // Download the report
            const blob = await response.blob();
            downloadFile(blob, 'audit_report.docx');

        } catch (error) {
            console.error('Report generation error:', error);
            showAlert(`Report generation failed: ${error.message}`, 'danger');
        } finally {
            setLoadingState(generateReportBtn, false, 'Generate Word Report');
        }
    });

    // Display Results Function
    function displayResults(data) {
        // Clear previous charts if they exist
        if (severityChart) severityChart.destroy();
        if (branchChart) branchChart.destroy();

        // Executive Summary
        executiveSummaryDiv.innerHTML = `
            <div class="card border-primary mb-4">
                <div class="card-header bg-primary text-white">
                    <h4 class="mb-0">Executive Summary</h4>
                </div>
                <div class="card-body">
                    <p class="card-text">${data.analysis.summary || 'No summary available'}</p>
                </div>
            </div>
        `;

        // Detailed Findings
        let findingsHTML = `
            <div class="card border-secondary mb-4">
                <div class="card-header bg-secondary text-white">
                    <h4 class="mb-0">Detailed Findings</h4>
                </div>
                <div class="card-body">
        `;

        if (data.analysis.findings && data.analysis.findings.length > 0) {
            data.analysis.findings.forEach((finding, index) => {
                findingsHTML += `
                    <div class="mb-4 p-3 border rounded">
                        <h5><span class="badge bg-${getSeverityBadgeClass(finding.severity)} me-2">${index + 1}</span>
                        ${finding.title || 'Untitled Finding'}</h5>
                        <p class="text-muted">${finding.description || 'No description provided'}</p>
                        ${finding.recommendation ? `
                        <div class="alert alert-info p-2 mb-0">
                            <strong>Recommendation:</strong> ${finding.recommendation}
                        </div>` : ''}
                    </div>
                `;
            });
        } else {
            findingsHTML += '<p class="text-muted">No findings available</p>';
        }

        findingsHTML += `</div></div>`;
        detailedFindingsDiv.innerHTML = findingsHTML;

        // Generate Charts with Actual Data
        generateCharts(data);
    }

    // Generate Charts Function
    function generateCharts(data) {
        // Process data for charts
        const severityData = processSeverityData(data);
        const branchData = processBranchData(data);

        // Severity Chart
        severityChart = new Chart(severityChartCanvas, {
            type: 'bar',
            data: {
                labels: severityData.labels,
                datasets: [{
                    label: 'Exception Count',
                    data: severityData.values,
                    backgroundColor: severityData.colors,
                    borderColor: severityData.borderColors,
                    borderWidth: 1
                }]
            },
            options: getChartOptions('Exception Severity Distribution')
        });

        // Branch Chart
        branchChart = new Chart(branchChartCanvas, {
            type: 'pie',
            data: {
                labels: branchData.labels,
                datasets: [{
                    label: 'Exception Count',
                    data: branchData.values,
                    backgroundColor: branchData.colors,
                    borderWidth: 1
                }]
            },
            options: getChartOptions('Exceptions by Branch')
        });
    }

    // Helper Functions
    function processSeverityData(data) {
        // Extract severity data from analysis
        const severityCounts = {
            high: 0,
            medium: 0,
            low: 0,
            unspecified: 0
        };

        if (data.analysis.findings) {
            data.analysis.findings.forEach(finding => {
                const severity = (finding.severity || 'unspecified').toLowerCase();
                severityCounts[severity] = (severityCounts[severity] || 0) + 1;
            });
        }

        return {
            labels: ['High', 'Medium', 'Low', 'Unspecified'],
            values: [
                severityCounts.high,
                severityCounts.medium,
                severityCounts.low,
                severityCounts.unspecified
            ],
            colors: [
                'rgba(220, 53, 69, 0.7)',
                'rgba(255, 193, 7, 0.7)',
                'rgba(25, 135, 84, 0.7)',
                'rgba(108, 117, 125, 0.7)'
            ],
            borderColors: [
                'rgba(220, 53, 69, 1)',
                'rgba(255, 193, 7, 1)',
                'rgba(25, 135, 84, 1)',
                'rgba(108, 117, 125, 1)'
            ]
        };
    }

    function processBranchData(data) {
        // Extract branch data from analysis
        const branchCounts = {};

        if (data.analysis.participants) {
            data.analysis.participants.forEach(participant => {
                const branch = participant.branch || 'Unspecified';
                branchCounts[branch] = (branchCounts[branch] || 0) + 1;
            });
        }

        const labels = Object.keys(branchCounts);
        return {
            labels: labels,
            values: labels.map(label => branchCounts[label]),
            colors: labels.map((_, i) => {
                const hue = (i * 137.508) % 360; // Golden angle for distinct colors
                return `hsla(${hue}, 70%, 60%, 0.7)`;
            })
        };
    }

    function getChartOptions(title) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: title,
                    font: {
                        size: 16
                    }
                },
                legend: {
                    position: 'bottom'
                }
            }
        };
    }

    function getSeverityBadgeClass(severity) {
        const sev = (severity || '').toLowerCase();
        if (sev.includes('high')) return 'danger';
        if (sev.includes('medium')) return 'warning';
        if (sev.includes('low')) return 'success';
        return 'secondary';
    }

    function setLoadingState(button, isLoading, text) {
        button.disabled = isLoading;
        button.innerHTML = isLoading ?
            `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> ${text}` :
            text;
    }

    function showAlert(message, type) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.role = 'alert';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;

        // Add alert to the top of the results section
        resultsSection.prepend(alertDiv);

        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            alertDiv.classList.remove('show');
            setTimeout(() => alertDiv.remove(), 150);
        }, 5000);
    }

    function downloadFile(blob, filename) {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();
    }
});