/**
 * Interactive Dashboard Charts using Chart.js
 * Provides real-time visualizations for compliance, violations, training progress, etc.
 */

// Color palette
const colors = {
    primary: '#003366',
    accent: '#4bc0c0',
    success: '#10b981',
    warning: '#f59e0b',
    danger: '#ef4444',
    info: '#3b82f6',
    gray: '#6b7280',
};

/**
 * Create a violations trend chart
 */
function createViolationsTrendChart(canvasId, data) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.labels,
            datasets: [{
                label: 'Total Violations',
                data: data.values,
                borderColor: colors.danger,
                backgroundColor: colors.danger + '20',
                fill: true,
                tension: 0.4,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        precision: 0
                    }
                }
            }
        }
    });
}

/**
 * Create a violations by severity pie chart
 */
function createViolationsBySeverityChart(canvasId, data) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    
    return new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Critical', 'High', 'Medium', 'Low'],
            datasets: [{
                data: [
                    data.critical || 0,
                    data.high || 0,
                    data.medium || 0,
                    data.low || 0
                ],
                backgroundColor: [
                    '#dc2626',
                    '#ea580c',
                    '#f59e0b',
                    '#6b7280',
                ],
                borderWidth: 2,
                borderColor: '#fff',
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.parsed || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = total > 0 ? ((value / total) * 100).toFixed(1) : 0;
                            return `${label}: ${value} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
}

/**
 * Create a training completion rate bar chart
 */
function createTrainingCompletionChart(canvasId, data) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    
    return new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.labels,
            datasets: [{
                label: 'Completion Rate (%)',
                data: data.values,
                backgroundColor: colors.success,
                borderColor: colors.success,
                borderWidth: 1,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false,
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `Completion: ${context.parsed.y.toFixed(1)}%`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    ticks: {
                        callback: function(value) {
                            return value + '%';
                        }
                    }
                }
            }
        }
    });
}

/**
 * Create a policy compliance heatmap
 */
function createComplianceHeatmap(canvasId, data) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    
    return new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.labels,
            datasets: [
                {
                    label: 'Compliant',
                    data: data.compliant,
                    backgroundColor: colors.success,
                    stack: 'stack0',
                },
                {
                    label: 'Violations',
                    data: data.violations,
                    backgroundColor: colors.danger,
                    stack: 'stack0',
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                },
                tooltip: {
                    mode: 'index',
                }
            },
            scales: {
                x: {
                    stacked: true,
                },
                y: {
                    stacked: true,
                    beginAtZero: true,
                }
            }
        }
    });
}

/**
 * Create a user activity timeline
 */
function createActivityTimelineChart(canvasId, data) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.labels,
            datasets: [
                {
                    label: 'Logins',
                    data: data.logins,
                    borderColor: colors.info,
                    backgroundColor: colors.info + '20',
                    fill: false,
                    tension: 0.4,
                },
                {
                    label: 'Training Activities',
                    data: data.training,
                    borderColor: colors.success,
                    backgroundColor: colors.success + '20',
                    fill: false,
                    tension: 0.4,
                },
                {
                    label: 'Quiz Attempts',
                    data: data.quizzes,
                    borderColor: colors.warning,
                    backgroundColor: colors.warning + '20',
                    fill: false,
                    tension: 0.4,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        precision: 0
                    }
                }
            }
        }
    });
}

/**
 * Create ML model performance chart
 */
function createMLPerformanceChart(canvasId, data) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    
    return new Chart(ctx, {
        type: 'radar',
        data: {
            labels: ['Precision', 'Recall', 'F1-Score', 'Accuracy', 'ROC-AUC'],
            datasets: [{
                label: 'Model Performance',
                data: [
                    data.precision * 100,
                    data.recall * 100,
                    data.f1_score * 100,
                    data.accuracy * 100,
                    data.roc_auc * 100
                ],
                backgroundColor: colors.accent + '40',
                borderColor: colors.accent,
                borderWidth: 2,
                pointBackgroundColor: colors.accent,
                pointBorderColor: '#fff',
                pointHoverBackgroundColor: '#fff',
                pointHoverBorderColor: colors.accent,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                r: {
                    beginAtZero: true,
                    max: 100,
                    ticks: {
                        stepSize: 20,
                        callback: function(value) {
                            return value + '%';
                        }
                    }
                }
            },
            plugins: {
                legend: {
                    position: 'top',
                }
            }
        }
    });
}

/**
 * Fetch and render dashboard charts
 */
async function initializeDashboard() {
    try {
        // Fetch dashboard data from API
        const response = await fetch('/api/v1/violations/statistics/', {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
            }
        });
        
        if (!response.ok) {
            throw new Error('Failed to fetch dashboard data');
        }
        
        const data = await response.json();
        
        // Initialize charts if elements exist
        if (document.getElementById('violationsBySeverityChart')) {
            createViolationsBySeverityChart('violationsBySeverityChart', data.by_severity);
        }
        
        // Add more chart initializations as needed
        
    } catch (error) {
        console.error('Error initializing dashboard:', error);
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    if (document.querySelector('[data-dashboard="true"]')) {
        initializeDashboard();
    }
});
