// API Base URL (Assumed same host since FastAPI serves static files, or loaded from localStorage for separate deployment)
let API_BASE = localStorage.getItem('backend_url') || window.location.origin;
if (API_BASE.endsWith('/')) {
    API_BASE = API_BASE.slice(0, -1);
}

// State management
let appState = {
    apiKeyConfigured: false,
    selectedFile: null,
    uploadedDocId: null,
    currentTab: 'studio',
    documents: [],
    analysisResult: null
};

// DOM Elements
const navItems = document.querySelectorAll('.nav-item');
const tabContents = document.querySelectorAll('.tab-content');
const apiWarningBanner = document.getElementById('api-warning-banner');
const apiStatusIndicator = document.getElementById('api-status-indicator');

// Initialize the application
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    checkApiKeyConfig();
    initUploadZone();
    initSubTabs();
    initSettingsForm();
    initSearch();
    initVault();
    initPlaybook();
});

// ==========================================
// Navigation & Tab Switching
// ==========================================
function initNavigation() {
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const tabId = item.getAttribute('data-tab');
            switchTab(tabId);
        });
    });
}

function switchTab(tabId) {
    appState.currentTab = tabId;
    
    // Update active nav link
    navItems.forEach(item => {
        if (item.getAttribute('data-tab') === tabId) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });

    // Update active tab content
    tabContents.forEach(content => {
        if (content.id === `tab-${tabId}`) {
            content.classList.remove('hidden');
        } else {
            content.classList.add('hidden');
        }
    });

    // Load tab-specific data
    if (tabId === 'vault') {
        loadVaultDocuments();
    } else if (tabId === 'playbook') {
        loadPlaybookData();
    } else if (tabId === 'settings') {
        checkApiKeyConfig(true);
    }
}

// ==========================================
// API Key & Configurations
// ==========================================
async function checkApiKeyConfig(fillSettings = false) {
    try {
        const response = await fetch(`${API_BASE}/api/config`);
        const data = await response.json();
        appState.apiKeyConfigured = data.openai_key_configured;
        
        const dot = apiStatusIndicator.querySelector('.status-dot');
        const text = apiStatusIndicator.querySelector('.status-text');
        const warning = document.getElementById('openai-status-badge');

        if (appState.apiKeyConfigured) {
            dot.className = 'status-dot online';
            text.textContent = 'API Connected';
            apiWarningBanner.classList.add('hidden');
            if (warning) {
                warning.className = 'status-badge success';
                warning.textContent = 'Connected';
            }
        } else {
            dot.className = 'status-dot offline';
            text.textContent = 'API Key Required';
            apiWarningBanner.classList.remove('hidden');
            if (warning) {
                warning.className = 'status-badge danger';
                warning.textContent = 'Not Configured';
            }
        }

        // Enable or disable analysis trigger button
        const btnAnalyze = document.getElementById('btn-analyze');
        if (btnAnalyze) {
            btnAnalyze.disabled = !appState.selectedFile;
        }
    } catch (error) {
        console.error('Failed to fetch config:', error);
    }
}

function initSettingsForm() {
    const settingsForm = document.getElementById('settings-form');
    const apiKeyInput = document.getElementById('openai-api-key-input');
    const backendUrlInput = document.getElementById('backend-url-input');
    const toggleBtn = document.getElementById('btn-toggle-key-visibility');

    // Load saved settings
    if (backendUrlInput) {
        backendUrlInput.value = localStorage.getItem('backend_url') || '';
    }

    toggleBtn.addEventListener('click', () => {
        const isPassword = apiKeyInput.type === 'password';
        apiKeyInput.type = isPassword ? 'text' : 'password';
        toggleBtn.innerHTML = isPassword ? '<i class="fa-solid fa-eye-slash"></i>' : '<i class="fa-solid fa-eye"></i>';
    });

    settingsForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const key = apiKeyInput.value.trim();
        const backendUrl = backendUrlInput ? backendUrlInput.value.trim() : '';

        // Validate key if provided
        if (key && !(key.startsWith('sk-') || key.startsWith('gsk_'))) {
            alert('Invalid API Key. It must start with "sk-" (OpenAI) or "gsk_" (Groq).');
            return;
        }

        const btnSave = document.getElementById('btn-save-settings');
        const originalText = btnSave.innerHTML;
        btnSave.disabled = true;
        btnSave.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Saving...';

        try {
            // Save backend URL locally
            if (backendUrl) {
                localStorage.setItem('backend_url', backendUrl);
                API_BASE = backendUrl;
                if (API_BASE.endsWith('/')) {
                    API_BASE = API_BASE.slice(0, -1);
                }
            } else {
                localStorage.removeItem('backend_url');
                API_BASE = window.location.origin;
            }

            // Save key to backend if provided
            if (key) {
                const response = await fetch(`${API_BASE}/api/config`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ openai_api_key: key })
                });

                if (response.ok) {
                    alert('Settings updated and credentials saved!');
                    apiKeyInput.value = '';
                } else {
                    const err = await response.json();
                    alert(`Error saving credentials: ${err.detail || 'Unknown error'}`);
                }
            } else {
                alert('Settings updated successfully!');
            }
            
            checkApiKeyConfig();
        } catch (error) {
            console.error('Settings update failed:', error);
            alert('Failed to connect to the backend server.');
        } finally {
            btnSave.disabled = false;
            btnSave.innerHTML = originalText;
        }
    });
}

// ==========================================
// Ingest & Agent Analysis (Studio)
// ==========================================
function initUploadZone() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('contract-file');
    const removeFileBtn = document.getElementById('btn-remove-file');
    const selectedFileInfo = document.getElementById('selected-file-info');
    const selectedFileName = document.getElementById('selected-file-name');
    const selectedFileSize = document.getElementById('selected-file-size');
    const fileIconPreview = document.getElementById('file-icon-preview');
    const btnAnalyze = document.getElementById('btn-analyze');
    const uploadForm = document.getElementById('upload-form');

    // Click dropzone to trigger input
    dropZone.addEventListener('click', () => fileInput.click());

    // Drag-and-drop actions
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });

    removeFileBtn.addEventListener('click', () => {
        appState.selectedFile = null;
        fileInput.value = '';
        selectedFileInfo.classList.add('hidden');
        dropZone.classList.remove('hidden');
        btnAnalyze.disabled = true;
    });

    function handleFileSelect(file) {
        appState.selectedFile = file;
        selectedFileName.textContent = file.name;
        selectedFileSize.textContent = formatBytes(file.size);
        
        // Update file icon preview based on extension
        const ext = file.name.split('.').pop().toLowerCase();
        if (ext === 'pdf') {
            fileIconPreview.className = 'fa-regular fa-file-pdf file-icon text-danger';
        } else if (ext === 'docx') {
            fileIconPreview.className = 'fa-regular fa-file-word file-icon text-primary';
        } else {
            fileIconPreview.className = 'fa-regular fa-file-lines file-icon';
        }

        dropZone.classList.add('hidden');
        selectedFileInfo.classList.remove('hidden');
        
        // Enable analyze button if key is configured (or let them press it and trigger key validation warning)
        btnAnalyze.disabled = false;
    }

    // Submit form: Ingest and Analyze
    uploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!appState.selectedFile) return;

        // Show warning if API key isn't set
        if (!appState.apiKeyConfigured) {
            alert('OpenAI API Key is required for analysis. Please configure it in Settings first.');
            switchTab('settings');
            return;
        }

        const contractType = document.getElementById('contract-type-select').value;
        
        // Reset States
        const resultsEmpty = document.getElementById('results-empty');
        const resultsRunning = document.getElementById('results-running');
        const resultsComplete = document.getElementById('results-complete');
        
        resultsEmpty.classList.add('hidden');
        resultsComplete.classList.add('hidden');
        resultsRunning.classList.remove('hidden');
        
        resetPipelineNodes();
        
        try {
            // Step 1: Upload and Index
            updateNodeState('extractor', 'active', 'Uploading Document...');
            
            const formData = new FormData();
            formData.append('file', appState.selectedFile);
            formData.append('contract_type', contractType);
            
            const uploadResponse = await fetch(`${API_BASE}/api/upload`, {
                method: 'POST',
                body: formData
            });

            if (!uploadResponse.ok) {
                const err = await uploadResponse.json();
                throw new Error(err.detail || 'Upload and indexing failed.');
            }

            const uploadData = await uploadResponse.json();
            const documentId = uploadData.document_id;
            
            // Step 2: Trigger Agent Pipeline and Simulate Workflow Steps
            updateNodeState('extractor', 'active', 'Extracting clauses...');
            
            // Start simulated progress for UI aesthetics (real backend is processing, but we illuminate nodes step by step)
            let stage = 0;
            const nodeTimer = setInterval(() => {
                stage++;
                if (stage === 1) {
                    updateNodeState('extractor', 'completed', 'Completed');
                    updateNodeState('analyzer', 'active', 'Auditing legal risk...');
                    document.getElementById('conn-1').classList.add('active');
                } else if (stage === 2) {
                    updateNodeState('analyzer', 'completed', 'Completed');
                    updateNodeState('comparator', 'active', 'Comparing with playbook...');
                    document.getElementById('conn-2').classList.add('active');
                }
            }, 4500);

            const analyzeResponse = await fetch(`${API_BASE}/api/analyze`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    document_id: documentId,
                    contract_type: contractType
                })
            });

            clearInterval(nodeTimer);

            if (!analyzeResponse.ok) {
                const err = await analyzeResponse.json();
                throw new Error(err.detail || 'Multi-agent analysis failed.');
            }

            const resultData = await analyzeResponse.json();
            appState.analysisResult = resultData;
            
            // Complete visual nodes
            updateNodeState('extractor', 'completed', 'Completed');
            updateNodeState('analyzer', 'completed', 'Completed');
            updateNodeState('comparator', 'completed', 'Completed');
            document.getElementById('conn-1').className = 'pipeline-connector completed';
            document.getElementById('conn-2').className = 'pipeline-connector completed';
            
            // Wait brief moment and show results
            setTimeout(() => {
                resultsRunning.classList.add('hidden');
                resultsComplete.classList.remove('hidden');
                renderAnalysisResults(resultData);
            }, 600);

        } catch (error) {
            console.error('Analysis failed:', error);
            alert(`Analysis failed: ${error.message}`);
            resultsRunning.classList.add('hidden');
            resultsEmpty.classList.remove('hidden');
        }
    });
}

function resetPipelineNodes() {
    const nodes = ['extractor', 'analyzer', 'comparator'];
    nodes.forEach(n => {
        const el = document.getElementById(`node-${n}`);
        el.className = 'pipeline-node';
        el.querySelector('.node-status').textContent = 'Waiting';
    });
    document.getElementById('conn-1').className = 'pipeline-connector';
    document.getElementById('conn-2').className = 'pipeline-connector';
}

function updateNodeState(node, state, label) {
    const nodeEl = document.getElementById(`node-${node}`);
    if (!nodeEl) return;
    
    nodeEl.className = `pipeline-node ${state}`;
    nodeEl.querySelector('.node-status').textContent = label;
}

function renderAnalysisResults(data) {
    // Basic Details
    document.getElementById('completed-doc-title').textContent = data.filename;
    document.getElementById('completed-doc-meta').textContent = `${data.contract_type.replace('_', ' ')} • Analyzed on ${new Date().toLocaleDateString()}`;
    
    // Overall Risk Badge
    const riskBadge = document.getElementById('overall-risk-badge');
    const risk = data.overall_risk_score.toLowerCase();
    riskBadge.className = `risk-badge-large ${risk}`;
    riskBadge.textContent = `${data.overall_risk_score} Risk`;
    
    // Executive Summary
    document.getElementById('analysis-summary-text').textContent = data.summary;

    // Subtab 1: Extracted Clauses
    const clausesContainer = document.getElementById('extracted-clauses-container');
    clausesContainer.innerHTML = '';
    if (data.extracted_clauses && data.extracted_clauses.length > 0) {
        data.extracted_clauses.forEach(c => {
            const card = document.createElement('div');
            card.className = 'clause-card';
            card.innerHTML = `
                <div class="clause-card-header">
                    <span class="clause-title">${c.clause_type}</span>
                    <span class="clause-badge">Confidence: ${Math.round(c.confidence_score * 100)}%</span>
                </div>
                <div class="clause-text-content">${escapeHTML(c.clause_text)}</div>
            `;
            clausesContainer.appendChild(card);
        });
    } else {
        clausesContainer.innerHTML = '<div class="text-center py-4 text-muted">No specific clauses extracted.</div>';
    }

    // Subtab 2: Risk Analysis
    const riskContainer = document.getElementById('risk-analysis-container');
    riskContainer.innerHTML = '';
    if (data.risk_analysis && data.risk_analysis.length > 0) {
        data.risk_analysis.forEach(r => {
            const level = r.risk_level.toLowerCase();
            const card = document.createElement('div');
            card.className = `risk-card ${level}`;
            card.innerHTML = `
                <div class="risk-card-header">
                    <span class="risk-title">${r.clause_type}</span>
                    <span class="risk-level-badge ${level}">${r.risk_level} Risk</span>
                </div>
                <p class="risk-desc">${escapeHTML(r.risk_description)}</p>
                <div class="risk-mitigation">
                    <strong>Mitigation Suggestion:</strong>
                    <span>${escapeHTML(r.mitigation_suggestion)}</span>
                </div>
            `;
            riskContainer.appendChild(card);
        });
    } else {
        riskContainer.innerHTML = '<div class="text-center py-4 text-muted">No key risks identified. Clause conforms to standards.</div>';
    }

    // Subtab 3: Playbook Comparison
    const comparisonContainer = document.getElementById('comparison-container');
    comparisonContainer.innerHTML = '';
    if (data.comparison_results && data.comparison_results.length > 0) {
        data.comparison_results.forEach(comp => {
            const statusClass = comp.compliance_status.toLowerCase().replace(' ', '-');
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${comp.clause_type}</td>
                <td>${escapeHTML(comp.extracted_text)}</td>
                <td>${escapeHTML(comp.standard_guideline)}</td>
                <td><span class="compliance-badge ${statusClass}">${comp.compliance_status}</span></td>
                <td>
                    <div class="action-plan-text">
                        <strong>Deviation:</strong>
                        <span>${escapeHTML(comp.deviation_details)}</span>
                        <strong class="mt-2" style="display:block;">Strategy:</strong>
                        <span style="color:#6EE7B7;">${escapeHTML(comp.renegotiation_strategy)}</span>
                    </div>
                </td>
            `;
            comparisonContainer.appendChild(row);
        });
    } else {
        comparisonContainer.innerHTML = '<tr><td colspan="5" class="text-center py-4 text-muted">No comparison items. Set appropriate contract type or define playbook rules.</td></tr>';
    }
}

function initSubTabs() {
    const subTabButtons = document.querySelectorAll('.tab-sub-btn');
    subTabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            // Remove active from all sub tabs
            subTabButtons.forEach(b => b.classList.remove('active'));
            // Add active to clicked
            btn.classList.add('active');

            const subTabId = btn.getAttribute('data-subtab');
            const subTabContents = document.querySelectorAll('.sub-tab-content');
            
            subTabContents.forEach(content => {
                if (content.id === `subtab-${subTabId}`) {
                    content.classList.remove('hidden');
                } else {
                    content.classList.add('hidden');
                }
            });
        });
    });
}

// ==========================================
// Semantic Search
// ==========================================
function initSearch() {
    const searchBtn = document.getElementById('btn-run-search');
    const searchInput = document.getElementById('search-query');
    const filterChips = document.querySelectorAll('.chip');
    let selectedFilter = 'All';

    // Filters selection
    filterChips.forEach(chip => {
        chip.addEventListener('click', () => {
            filterChips.forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            selectedFilter = chip.getAttribute('data-filter');
            // Re-run search if there is a query already
            if (searchInput.value.trim()) {
                runSearch(searchInput.value.trim(), selectedFilter);
            }
        });
    });

    searchBtn.addEventListener('click', () => {
        const query = searchInput.value.trim();
        if (query) runSearch(query, selectedFilter);
    });

    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            const query = searchInput.value.trim();
            if (query) runSearch(query, selectedFilter);
        }
    });
}

async function runSearch(query, filter) {
    const loading = document.getElementById('search-loading');
    const container = document.getElementById('search-results-container');
    
    container.innerHTML = '';
    loading.classList.remove('hidden');

    try {
        const response = await fetch(`${API_BASE}/api/search?query=${encodeURIComponent(query)}&contract_type=${filter}&limit=6`);
        loading.classList.add('hidden');

        if (!response.ok) throw new Error('Search request failed.');
        
        const data = await response.json();
        
        if (data.results && data.results.length > 0) {
            data.results.forEach(res => {
                const card = document.createElement('div');
                card.className = 'result-card';
                card.innerHTML = `
                    <div class="result-card-header">
                        <div class="result-doc-info">
                            <span class="result-doc-name">${res.filename}</span>
                            <span class="result-doc-type">${res.clause_type.replace('_', ' ')}</span>
                        </div>
                        <span class="result-score">${Math.round(res.score * 100)}% Match</span>
                    </div>
                    <p class="result-text">${escapeHTML(res.text)}</p>
                `;
                container.appendChild(card);
            });
        } else {
            container.innerHTML = `
                <div class="state-empty">
                    <i class="fa-solid fa-folder-minus empty-icon"></i>
                    <h3>No results found</h3>
                    <p>No contract clauses matched the terms of your search query. Try rephrasing or checking spelling.</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('Search error:', error);
        loading.classList.add('hidden');
        container.innerHTML = `
            <div class="state-empty">
                <i class="fa-solid fa-triangle-exclamation empty-icon text-danger"></i>
                <h3>Search Failed</h3>
                <p>Failed to retrieve search results from the database index. Make sure you have uploaded files.</p>
            </div>
        `;
    }
}

// ==========================================
// Document Vault
// ==========================================
function initVault() {
    document.getElementById('btn-refresh-vault').addEventListener('click', () => {
        loadVaultDocuments();
    });
}

async function loadVaultDocuments() {
    const listContainer = document.getElementById('vault-documents-list');
    listContainer.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-muted"><i class="fa-solid fa-circle-notch fa-spin"></i> Fetching records...</td></tr>';
    
    try {
        const response = await fetch(`${API_BASE}/api/documents`);
        if (!response.ok) throw new Error('Failed to retrieve contracts.');
        
        const docs = await response.json();
        appState.documents = docs;
        
        // Update stats
        document.getElementById('vault-stat-count').textContent = docs.length;
        // Simulated chunk multiplier (avg 8 chunks per document for presentation)
        const chunkEstimate = docs.reduce((acc, d) => acc + (d.chunks_indexed || 8), 0);
        document.getElementById('vault-stat-chunks').textContent = chunkEstimate;

        listContainer.innerHTML = '';
        if (docs.length > 0) {
            docs.forEach(doc => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${doc.filename}</strong></td>
                    <td><span class="result-doc-type">${doc.contract_type.replace('_', ' ')}</span></td>
                    <td>${doc.upload_time || 'N/A'}</td>
                    <td>${formatBytes(doc.size_bytes)}</td>
                    <td><span class="status-badge success">Indexed</span></td>
                    <td>
                        <button class="btn-delete" data-id="${doc.document_id}" title="Delete document from index">
                            <i class="fa-regular fa-trash-can"></i>
                        </button>
                    </td>
                `;
                
                // Add delete listener
                tr.querySelector('.btn-delete').addEventListener('click', async (e) => {
                    e.stopPropagation();
                    const docId = e.currentTarget.getAttribute('data-id');
                    if (confirm(`Are you sure you want to remove this contract and its vector index?`)) {
                        await deleteDocumentFromVault(docId);
                    }
                });
                
                listContainer.appendChild(tr);
            });
        } else {
            listContainer.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-muted">No contracts in vault. Go to Analysis Studio to upload.</td></tr>';
        }
    } catch (error) {
        console.error('Vault fetch error:', error);
        listContainer.innerHTML = '<tr><td colspan="6" class="text-center py-4 text-danger">Failed to connect to the database.</td></tr>';
    }
}

async function deleteDocumentFromVault(docId) {
    try {
        const response = await fetch(`${API_BASE}/api/documents/${docId}`, {
            method: 'DELETE'
        });

        if (response.ok) {
            loadVaultDocuments();
        } else {
            alert('Failed to delete document.');
        }
    } catch (error) {
        console.error('Delete error:', error);
    }
}

// ==========================================
// Playbook Editor
// ==========================================
function initPlaybook() {
    const saveBtn = document.getElementById('btn-save-playbook');
    saveBtn.addEventListener('click', () => {
        savePlaybookData();
    });
}

async function loadPlaybookData() {
    const textarea = document.getElementById('playbook-json-textarea');
    textarea.value = '// Loading playbook from server...';
    
    try {
        const response = await fetch(`${API_BASE}/api/playbook`);
        if (!response.ok) throw new Error('Failed to load playbook.');
        const data = await response.json();
        
        textarea.value = JSON.stringify(data, null, 2);
    } catch (error) {
        console.error('Playbook loading failed:', error);
        textarea.value = '// Error loading playbook.';
    }
}

async function savePlaybookData() {
    const textarea = document.getElementById('playbook-json-textarea');
    const saveBtn = document.getElementById('btn-save-playbook');
    const originalText = saveBtn.innerHTML;

    let payload;
    try {
        payload = JSON.parse(textarea.value);
    } catch (e) {
        alert('Invalid JSON structure. Please fix compilation issues before saving.');
        return;
    }

    saveBtn.disabled = true;
    saveBtn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Saving...';

    try {
        const response = await fetch(`${API_BASE}/api/playbook`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            alert('Playbook configuration updated successfully!');
        } else {
            alert('Server rejected playbook update.');
        }
    } catch (error) {
        console.error('Playbook saving failed:', error);
        alert('Failed to connect to backend.');
    } finally {
        saveBtn.disabled = false;
        saveBtn.innerHTML = originalText;
    }
}

// ==========================================
// Formatting & Escaping Helpers
// ==========================================
function formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

function escapeHTML(str) {
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
