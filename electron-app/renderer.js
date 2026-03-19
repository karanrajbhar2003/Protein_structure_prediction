window.addEventListener('DOMContentLoaded', () => {
    // --- State ---
    let currentProject = null;
    let projects = []; // Will be loaded from the API
    let isLogPaused = false;

    // --- Elements ---
    const logContent = document.getElementById('log-content');
    const pauseButton = document.getElementById('log-pause-toggle');
    const copyButton = document.getElementById('log-copy');
    const logPanel = document.querySelector('.log-panel');
    const logExpandToggle = document.getElementById('log-expand-toggle');
    
    // Page-specific elements
    const activeProjectDisplay = document.getElementById('active-project-display');
    const createProjectBtn = document.getElementById('create-project-btn');
    const newProjectNameInput = document.getElementById('new-project-name');
    const projectListDiv = document.getElementById('project-list');
    const detailedProjectListDiv = document.getElementById('detailed-project-list');
    
    const runModelingBtn = document.getElementById('run-modeling-btn');
    const fastaInput = document.getElementById('fasta-input');
    const jobNameInput = document.getElementById('job-name-input');
    const runModellerCheckbox = document.getElementById('run-modeller-checkbox');
    const runRobettaCheckbox = document.getElementById('run-robetta-checkbox');
    const numModelsInput = document.getElementById('num-models-input');
    const sequenceLengthEl = document.getElementById('sequence-length');
    
    const refreshRobettaQueueBtn = document.getElementById('refresh-robetta-queue-btn');
    const robettaQueueContainer = document.getElementById('robetta-queue-container');
    const downloadRobettaJobBtn = document.getElementById('download-robetta-job-btn');
    const robettaJobIdInput = document.getElementById('robetta-job-id-input');
    const robettaDownloadProgress = document.getElementById('robetta-download-progress');
    const robettaDownloadProgressBar = document.getElementById('robetta-download-progress-bar');
    const robettaDownloadProgressText = document.getElementById('robetta-download-progress-text');
    const robettaDownloadStatus = document.getElementById('robetta-download-status');

    const runValidationBtn = document.getElementById('run-validation-btn');
    const pdbSourceSelector = document.getElementById('pdb-source-selector');
    const projectModelSelector = document.getElementById('project-model-selector');
    const uploadModelSelector = document.getElementById('upload-model-selector');
    const pdbModelSelect = document.getElementById('pdb-model-select');
    const pdbFileInput = document.getElementById('pdb-file-input');
    const validatorsGroup = document.getElementById('validators-group');
    
    const saveSettingsBtn = document.getElementById('save-settings-btn');
    const robettaUserInput = document.getElementById('robetta-user-input');
    const robettaPassInput = document.getElementById('robetta-pass-input');
    const qmeanEmailInput = document.getElementById('qmean-email-input');
    const qmeanTokenInput = document.getElementById('qmean-token-input');
    const voromqaPathInput = document.getElementById('voromqa-path-input');
    const dsspPathInput = document.getElementById('dssp-path-input');
    const dsspPathBrowseBtn = document.getElementById('dssp-path-browse-btn');
    const phenixPathInput = document.getElementById('phenix-path-input');
    const phenixPathBrowseBtn = document.getElementById('phenix-path-browse-btn');
    const generatePdfBtn = document.getElementById('generate-pdf-btn');
    const reportsStatus = document.getElementById('reports-status');
    const reportsResults = document.getElementById('reports-results');
    let freesasaPathValue = '';

    // --- Logging ---
    const autoScroll = () => { !isLogPaused && (logContent.scrollTop = logContent.scrollHeight); };
    const addLog = (message, level = 'info') => {
        const logLine = document.createElement('div');
        logLine.classList.add('log-line', `log-${level}`);
        const timestamp = new Date().toLocaleTimeString();
        const textNode = document.createTextNode(message);
        logLine.innerHTML = `<span>[${timestamp}]</span> `;
        logLine.appendChild(textNode);
        logContent.appendChild(logLine);
        autoScroll();
    };

    if (pauseButton) pauseButton.addEventListener('click', () => {
        isLogPaused = !isLogPaused;
        pauseButton.textContent = isLogPaused ? 'Resume' : 'Pause';
    });
    if (copyButton) copyButton.addEventListener('click', () => navigator.clipboard.writeText(logContent.innerText));
    if (logExpandToggle && logPanel) {
        const syncLogToggleLabel = () => {
            logExpandToggle.textContent = logPanel.classList.contains('collapsed') ? 'Show Logs' : 'Hide Logs';
        };
        syncLogToggleLabel();
        logExpandToggle.addEventListener('click', () => {
            logPanel.classList.toggle('collapsed');
            syncLogToggleLabel();
        });
    }

    // --- Navigation ---
    const navItems = document.querySelectorAll('.nav-item');
    const pages = document.querySelectorAll('.page');
    navItems.forEach(item => {
        item.addEventListener('click', async (event) => {
            event.preventDefault();
            const pageId = item.getAttribute('data-page');
            navItems.forEach(nav => nav.classList.remove('active'));
            pages.forEach(page => page.classList.remove('active'));
            item.classList.add('active');
            document.getElementById(pageId).classList.add('active');

            if (pageId === 'about') {
                const aboutPage = document.getElementById('about');
                if (aboutPage.children.length === 0) { // Load content only once
                    console.log('Loading about page content...');
                    const content = await window.api.getContent('about');
                    console.log('Content loaded:', content);
                    aboutPage.innerHTML = content;

                    const aboutNavItems = aboutPage.querySelectorAll('.about-nav-item');
                    const aboutPanes = aboutPage.querySelectorAll('.about-pane');

                    aboutNavItems.forEach(item => {
                        item.addEventListener('click', () => {
                            const contentId = item.getAttribute('data-content');

                            aboutNavItems.forEach(nav => nav.classList.remove('active'));
                            aboutPanes.forEach(pane => pane.classList.remove('active'));

                            item.classList.add('active');
                            aboutPage.querySelector(`#${contentId}`).classList.add('active');
                        });
                    });
                }
            } else if (pageId === 'help') {
                const helpPage = document.getElementById('help');
                if (helpPage.children.length === 0) { // Load content only once
                    console.log('Loading help page content...');
                    const content = await window.api.getContent('help');
                    console.log('Content loaded:', content);
                    helpPage.innerHTML = content;
                }
            } else if (pageId === 'projects') {
                if (currentProject) {
                    try {
                        addLog(`Fetching details for project: ${currentProject}`, 'info');
                        const projectData = await window.api.get(`/api/projects/${currentProject}`);
                        renderProjectDetails(projectData);
                    } catch (err) {
                        addLog(`Failed to load project details: ${err.message}`, 'error');
                        detailedProjectListDiv.innerHTML = `<p class="text-secondary">Error loading project details.</p>`;
                    }
                } else {
                    detailedProjectListDiv.innerHTML = `<div class="card"><p class="text-secondary">Please select a project from the Dashboard to see its details here.</p></div>`;
                }
            }
        });
    });

    // --- Project Management ---
    const renderProjectDetails = (projectData) => {
        detailedProjectListDiv.innerHTML = ''; // Clear previous content

        const createCard = (title, files) => {
            const card = document.createElement('div');
            card.className = 'card';
            
            let fileListHtml = '';
            if (files && files.length > 0) {
                fileListHtml = '<ul>' + files.map(file => `<li>${file.name}</li>`).join('') + '</ul>';
            } else {
                fileListHtml = '<p class="text-secondary">No files found.</p>';
            }

            card.innerHTML = `
                <h3>${title}</h3>
                ${fileListHtml}
            `;
            return card;
        };

        const grid = document.createElement('div');
        grid.className = 'card-grid';

        grid.appendChild(createCard('Modeller Models', projectData.modeller_models));
        grid.appendChild(createCard('Robetta Models', projectData.robetta_models));
        grid.appendChild(createCard('Validation Reports', projectData.validation_reports));
        grid.appendChild(createCard('PDF Reports', projectData.pdf_reports));

        detailedProjectListDiv.appendChild(grid);
    };
    
    const loadProjectModels = (projectName) => {
        window.api.get(`/api/projects/${projectName}/models`)
            .then(models => {
                pdbModelSelect.innerHTML = '';
                if (models.length === 0) {
                    pdbModelSelect.innerHTML = '<option disabled>No models found in this project</option>';
                    return;
                }
                models.forEach(model => {
                    const option = document.createElement('option');
                    option.value = model;
                    option.textContent = model;
                    pdbModelSelect.appendChild(option);
                });
            })
            .catch(err => {
                addLog(`Failed to load models for ${projectName}: ${err.message}`, 'error');
                pdbModelSelect.innerHTML = '<option disabled>Error loading models</option>';
            });
    };

    const setActiveProject = (projectName) => {
        currentProject = projectName;
        activeProjectDisplay.textContent = `${currentProject}`;
        addLog(`Project "${projectName}" selected.`, 'info');
        
        document.querySelector('.nav-item[data-page="modeling"]').classList.remove('disabled');
        document.querySelector('.nav-item[data-page="validation"]').classList.remove('disabled');

        renderProjectList();
        loadProjectModels(projectName);
    };

    const clearActiveProject = () => {
        currentProject = null;
        activeProjectDisplay.textContent = 'No project selected.';
        document.querySelector('.nav-item[data-page="modeling"]').classList.add('disabled');
        document.querySelector('.nav-item[data-page="validation"]').classList.add('disabled');
        pdbModelSelect.innerHTML = '';
        renderProjectList();
    };

    const renderProjectList = () => {
        projectListDiv.innerHTML = '';
        if (projects.length === 0) {
            projectListDiv.innerHTML = '<p>No projects found. Create one to get started!</p>';
            return;
        }
        projects.forEach(p => {
            const row = document.createElement('div');
            row.className = 'project-row';
            if (p === currentProject) row.classList.add('active');

            const name = document.createElement('div');
            name.className = 'project-name';
            name.textContent = p;

            const actions = document.createElement('div');
            actions.className = 'project-actions';

            const selectBtn = document.createElement('button');
            selectBtn.className = 'btn btn-secondary';
            selectBtn.textContent = 'Select';
            selectBtn.addEventListener('click', () => setActiveProject(p));

            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'btn btn-danger';
            deleteBtn.textContent = 'Delete';
            deleteBtn.addEventListener('click', async () => {
                const confirmed = confirm(`Delete project "${p}"? This will remove all its data.`);
                if (!confirmed) return;
                try {
                    addLog(`Deleting project "${p}"...`, 'info');
                    await window.api.delete(`/api/projects/${encodeURIComponent(p)}`);
                    addLog(`Project "${p}" deleted.`, 'success');
                    projects = projects.filter(name => name !== p);
                    if (currentProject === p) {
                        clearActiveProject();
                    } else {
                        renderProjectList();
                    }
                } catch (err) {
                    addLog(`Failed to delete project: ${err.message}`, 'error');
                }
            });

            actions.appendChild(selectBtn);
            actions.appendChild(deleteBtn);

            row.appendChild(name);
            row.appendChild(actions);
            projectListDiv.appendChild(row);
        });
    };

    const loadProjects = () => {
        window.api.get('/api/projects')
            .then(projectList => {
                projects = projectList;
                renderProjectList();
            })
            .catch(err => {
                addLog(`Failed to load projects: ${err.message}`, 'error');
                projectListDiv.innerHTML = '<p style="color: var(--error-red);">Could not load projects.</p>';
            });
    };

    if (createProjectBtn) createProjectBtn.addEventListener('click', () => {
        const newName = newProjectNameInput.value.trim();
        if (newName) {
            addLog(`Creating project "${newName}"...`, 'info');
            window.api.post('/api/projects', { name: newName })
                .then(() => {
                    addLog(`Project "${newName}" created successfully.`, 'success');
                    newProjectNameInput.value = '';
                    loadProjects();
                    setActiveProject(newName);
                })
                .catch(err => addLog(`Failed to create project: ${err.detail || err.message}`, 'error'));
        } else {
            addLog('Project name cannot be empty.', 'error');
        }
    });

    // --- Modeling Page ---
    if (fastaInput) fastaInput.addEventListener('input', () => {
        const sequence = fastaInput.value.split('\n').filter(line => !line.startsWith('>')).join('');
        sequenceLengthEl.textContent = `Length: ${sequence.length}`;
    });

        const modelingProgressBar = document.getElementById('modeling-progress-bar');
    const modelingProgressText = document.getElementById('modeling-progress-text');

    if (runModelingBtn) runModelingBtn.addEventListener('click', async () => {
        if (!currentProject) {
            addLog('Please create or select a project first.', 'error');
            return;
        }
        const requestData = {
            job_name: jobNameInput.value || 'prosutra_job',
            fasta_content: fastaInput.value,
            run_modeller: runModellerCheckbox.checked,
            run_robetta: runRobettaCheckbox.checked,
            modeller_num_models: parseInt(numModelsInput.value, 10),
            project_name: currentProject
        };
        const selectedModelingTools = {
            robetta: !!requestData.run_robetta,
            modeller: !!requestData.run_modeller
        };
        const totalModelingSteps = Object.values(selectedModelingTools).filter(Boolean).length;
        if (totalModelingSteps === 0) {
            addLog('Select at least one modeling method (Robetta or Modeller).', 'error');
            return;
        }
        const toolCompletion = {
            robetta: false,
            modeller: false
        };
        const updateModelingProgress = (toolInProgress = null, toolProgress = null) => {
            const completedCount = Object.entries(toolCompletion).reduce((acc, [tool, done]) => {
                return acc + (selectedModelingTools[tool] && done ? 1 : 0);
            }, 0);

            let percent = Math.round((completedCount / totalModelingSteps) * 100);

            if (
                toolInProgress &&
                toolProgress !== null &&
                selectedModelingTools[toolInProgress] &&
                !toolCompletion[toolInProgress]
            ) {
                const clamped = Math.max(0, Math.min(100, Number(toolProgress) || 0));
                const stepSize = 100 / totalModelingSteps;
                percent = Math.round((completedCount * stepSize) + (clamped / 100) * stepSize);
                percent = Math.min(99, percent);
            }

            modelingProgressBar.style.width = `${percent}%`;
            modelingProgressText.textContent = `${percent}%`;
        };

        addLog(`Starting modeling job for project "${currentProject}"...`, 'info');
        runModelingBtn.disabled = true;
        runModelingBtn.textContent = 'Running...';
        modelingProgressBar.style.width = '0%';
        modelingProgressText.textContent = '0%';

        try {
            const response = await fetch('http://127.0.0.1:8091/api/run-modelling', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestData)
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let modelingBuffer = '';
            
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                modelingBuffer += decoder.decode(value, { stream: true });
                const chunks = modelingBuffer.split('\n\n');
                modelingBuffer = chunks.pop() || '';

                for (const rawLine of chunks) {
                    const line = rawLine.trim();
                    if (line.startsWith('data:')) {
                        try {
                            const data = JSON.parse(line.substring(5));
                            if (data.event === 'progress' && data.tool === 'modeller') {
                                const progress = data.progress || 0;
                                updateModelingProgress('modeller', progress);
                                addLog(`Modeller progress: ${data.log}`, 'info');
                            } else if (data.event === 'finish') {
                                if (Object.prototype.hasOwnProperty.call(toolCompletion, data.tool) && selectedModelingTools[data.tool]) {
                                    toolCompletion[data.tool] = true;
                                }
                                updateModelingProgress();
                                addLog(`Job finished for ${data.tool}. Status: ${data.status}`, 'success');
                            } else if (data.event === 'error') {
                                if (Object.prototype.hasOwnProperty.call(toolCompletion, data.tool) && selectedModelingTools[data.tool]) {
                                    toolCompletion[data.tool] = true;
                                    updateModelingProgress();
                                }
                                addLog(`Error from ${data.tool}: ${data.log || data.detail}`, 'error');
                            }
                        } catch (e) {
                            addLog(`Error parsing modeling stream data: ${e.message}`, 'error');
                        }
                    }
                }
            }
        } catch (err) {
            addLog(`Modeling request failed: ${err.message}`, 'error');
        } finally {
            runModelingBtn.disabled = false;
            runModelingBtn.textContent = 'Run Modeling';
            updateModelingProgress();
            addLog('Modeling stream finished.', 'info');
        }
    });

    // --- Robetta Management ---
    if (refreshRobettaQueueBtn) refreshRobettaQueueBtn.addEventListener('click', () => {
        addLog('Fetching Robetta queue...', 'info');
        robettaQueueContainer.innerHTML = '<p>Loading...</p>';
        window.api.get('/api/robetta/queue')
            .then(queue => {
                robettaQueueContainer.innerHTML = '';
                 if (queue.length === 0) {
                    robettaQueueContainer.innerHTML = '<p>Queue is empty.</p>';
                    return;
                }
                const table = document.createElement('table');
                table.innerHTML = `<thead><tr><th>Job ID</th><th>Status</th><th>Target Name</th></tr></thead><tbody></tbody>`;
                const tbody = table.querySelector('tbody');
                queue.forEach(job => {
                    const row = tbody.insertRow();
                    row.insertCell().textContent = job.job_id;
                    row.insertCell().textContent = job.status;
                    row.insertCell().textContent = job.target_name;
                });
                robettaQueueContainer.appendChild(table);
                addLog('Robetta queue updated.', 'success');
            })
            .catch(err => {
                addLog(`Failed to fetch Robetta queue: ${err.message}`, 'error');
                robettaQueueContainer.innerHTML = '<p style="color: var(--error-red);">Could not load queue.</p>';
            });
    });

    if (downloadRobettaJobBtn) downloadRobettaJobBtn.addEventListener('click', () => {
        const setDownloadStatus = (message, level = 'info') => {
            if (!robettaDownloadStatus) return;
            robettaDownloadStatus.textContent = message;
            robettaDownloadStatus.className = `download-status ${level}`;
        };

        const setDownloadProgress = (value, text, isError = false) => {
            if (!robettaDownloadProgress || !robettaDownloadProgressBar || !robettaDownloadProgressText) return;
            robettaDownloadProgress.style.display = 'block';
            robettaDownloadProgressBar.style.width = `${value}%`;
            robettaDownloadProgressBar.classList.toggle('error', isError);
            robettaDownloadProgressText.textContent = text;
        };

        if (!currentProject) {
            addLog('Please select a project to download the results into.', 'error');
            setDownloadStatus('Please select a project first.', 'error');
            return;
        }
        const jobId = (robettaJobIdInput.value || '').trim();
        if (!jobId) {
            addLog('Please enter a Robetta Job ID to download.', 'error');
            setDownloadStatus('Please enter a Robetta Job ID.', 'error');
            return;
        }

        const oldBtnLabel = downloadRobettaJobBtn.textContent;
        downloadRobettaJobBtn.disabled = true;
        downloadRobettaJobBtn.textContent = 'Downloading...';
        setDownloadStatus(`Downloading job ${jobId}...`, 'info');
        setDownloadProgress(5, '5%');

        let pendingProgress = 5;
        const tick = setInterval(() => {
            pendingProgress = Math.min(pendingProgress + 7, 90);
            setDownloadProgress(pendingProgress, `${pendingProgress}%`);
        }, 700);

        addLog(`Requesting download for Robetta job ${jobId}...`, 'info');
        window.api.post('/api/robetta/download', { job_id: jobId, project_name: currentProject })
            .then(res => {
                clearInterval(tick);
                setDownloadProgress(100, '100%');
                setDownloadStatus(res.message || `Download for job ${jobId} succeeded.`, 'success');
                addLog(`Download for job ${jobId} finished with status: ${res.status}.`, 'success');
            })
            .catch(err => {
                clearInterval(tick);
                const msg = err.detail || err.message || 'Unknown error';
                setDownloadProgress(100, 'Failed', true);
                setDownloadStatus(`Download failed: ${msg}`, 'error');
                addLog(`Download failed: ${msg}`, 'error');
            })
            .finally(() => {
                downloadRobettaJobBtn.disabled = false;
                downloadRobettaJobBtn.textContent = oldBtnLabel;
            });
    });

    // --- Validation Page ---
    if (pdbSourceSelector) {
        pdbSourceSelector.addEventListener('change', (e) => {
            if (e.target.value === 'project') {
                projectModelSelector.style.display = 'block';
                uploadModelSelector.style.display = 'none';
            } else {
                projectModelSelector.style.display = 'none';
                uploadModelSelector.style.display = 'block';
            }
        });
    }

    // --- File Drop Zone UI Logic ---
    const fileDropZone = document.querySelector('.file-drop-zone');
    const fileListDisplay = document.getElementById('file-list-display');

    if (fileDropZone && pdbFileInput && fileListDisplay) {
        // Highlight drop zone when item is dragged over it
        fileDropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            fileDropZone.classList.add('dragover');
        });
        fileDropZone.addEventListener('dragleave', () => fileDropZone.classList.remove('dragover'));
        fileDropZone.addEventListener('drop', () => fileDropZone.classList.remove('dragover'));

        // Update file list display when files are selected
        pdbFileInput.addEventListener('change', () => {
            fileListDisplay.innerHTML = '';
            if (pdbFileInput.files.length > 0) {
                const list = document.createElement('ul');
                Array.from(pdbFileInput.files).forEach(file => {
                    const item = document.createElement('li');
                    item.textContent = file.name;
                    list.appendChild(item);
                });
                fileListDisplay.appendChild(list);
            }
        });
    }


    const reportsPage = document.getElementById('reports');
    let currentModelReports = {}; // Store results for PDF generation

    const setReportsStatus = (message) => {
        if (reportsStatus) {
            reportsStatus.textContent = message;
        }
    };

    const getResultDirsForPdf = () => {
        const dirs = Object.values(currentModelReports)
            .map(report => report && report.results_dir)
            .filter(Boolean);
        return [...new Set(dirs)];
    };

    if (generatePdfBtn) generatePdfBtn.addEventListener('click', async () => {
        const resultDirs = getResultDirsForPdf();
        if (resultDirs.length === 0) {
            setReportsStatus('No completed validation reports found. Run validation first.');
            addLog('Cannot generate PDF: no validation report directories available.', 'error');
            return;
        }

        const previousLabel = generatePdfBtn.textContent;
        generatePdfBtn.disabled = true;
        generatePdfBtn.textContent = 'Generating...';
        setReportsStatus(`Generating consolidated PDF for ${resultDirs.length} model(s)...`);

        try {
            const response = await window.api.post('/api/generate-report', {
                results_dirs: resultDirs,
                project_name: currentProject
            });
            if (!response || response.status !== 'success' || !response.pdf_path) {
                throw new Error('Backend did not return saved PDF path.');
            }
            setReportsStatus(`PDF saved to: ${response.pdf_path}`);
            addLog(`Consolidated PDF saved to ${response.pdf_path}`, 'success');
        } catch (err) {
            setReportsStatus(`PDF generation failed: ${err.message}`);
            addLog(`Failed to generate consolidated PDF: ${err.message}`, 'error');
        } finally {
            generatePdfBtn.disabled = false;
            generatePdfBtn.textContent = previousLabel;
        }
    });

    const createToolCard = (tool, modelName) => {
        const card = document.createElement('div');
        card.className = 'report-card';
        card.id = `report-card-${tool}-${modelName}`;
        
        card.innerHTML = `
            <div class="card-header">
                <h3>${tool}</h3>
                <span class="status-badge pending">Pending</span>
            </div>
            <div class="card-body"></div>
        `;
        return card;
    };

    const updateToolCard = (tool, modelName, data) => {
        const card = document.getElementById(`report-card-${tool}-${modelName}`);
        if (!card) return;

        const statusBadge = card.querySelector('.status-badge');
        statusBadge.textContent = data.status;
        statusBadge.className = `status-badge ${data.status.toLowerCase()}`;

        const cardBody = card.querySelector('.card-body');
        cardBody.innerHTML = ''; // Clear previous content

        if (data.summary && Object.keys(data.summary).length > 0) {
            const summaryPre = document.createElement('pre');
            summaryPre.textContent = JSON.stringify(data.summary, null, 2);
            cardBody.appendChild(summaryPre);
        }

        if (data.images && Object.keys(data.images).length > 0) {
            const imgContainer = document.createElement('div');
            imgContainer.className = 'image-container';
            
            const images = data.images;
            const imageKeys = Object.keys(images);

            const svgKey = imageKeys.find(key => key.endsWith('.svg'));
            const pngKey = imageKeys.find(key => key.endsWith('.png'));

            let imageToShow = null;
            if (svgKey) {
                imageToShow = images[svgKey];
            } else if (pngKey) {
                imageToShow = images[pngKey];
            }
            
            if (imageToShow) {
                const img = document.createElement('img');
                img.src = imageToShow;
                img.alt = svgKey || pngKey;
                imgContainer.appendChild(img);
            }

            cardBody.appendChild(imgContainer);
        }

        if (data.log) {
            const logExpander = document.createElement('details');
            logExpander.innerHTML = `<summary>Show Log</summary><pre>${data.log}</pre>`;
            cardBody.appendChild(logExpander);

            if (data.status === 'error') {
                const errorLogPath = data.log.split('\n').find(line => line.includes('_error.log'));
                if (errorLogPath) {
                    const errorP = document.createElement('p');
                    errorP.innerHTML = `An error occurred. Please check the log file for details: <code>${errorLogPath}</code>`;
                    cardBody.appendChild(errorP);
                }
            }
        }
    };
    
        const validationProgressBar = document.getElementById('validation-progress-bar');
    const validationProgressText = document.getElementById('validation-progress-text');
    
    if (runValidationBtn) runValidationBtn.addEventListener('click', async () => {
        if (!currentProject) {
            addLog('Please create or select a project first.', 'error');
            return;
        }

        const source = document.querySelector('input[name="pdb-source"]:checked').value;
        let pdb_model_names = [];
        let is_external_file = false;

        if (source === 'project') {
            pdb_model_names = Array.from(pdbModelSelect.selectedOptions).map(opt => opt.value);
            if (pdb_model_names.length === 0) {
                addLog('Please select at least one model from the project.', 'error');
                return;
            }
        } else {
            const files = pdbFileInput.files;
            if (files.length === 0) {
                addLog('Please select at least one PDB file to upload.', 'error');
                return;
            }
            pdb_model_names = Array.from(files).map(f => f.path);
            is_external_file = true;
        }
        const selectedValidators = Array.from(validatorsGroup.querySelectorAll('input:checked'));
        const requestData = {
            pdb_model_names,
            is_external_file,
            project_name: currentProject,
            validators: selectedValidators.reduce((acc, el) => ({ ...acc, [el.dataset.validator]: true }), {})
        };

        // Reset UI
        currentModelReports = {};
        if (reportsResults) reportsResults.innerHTML = '';
        setReportsStatus('Validation running... report cards will appear here.');
        validationProgressBar.style.width = '0%';
        validationProgressText.textContent = '0%';
        
        document.querySelector('.nav-item[data-page="reports"]').click();
        
        runValidationBtn.disabled = true;
        runValidationBtn.textContent = 'Running...';
        
        addLog(`Starting validation for ${pdb_model_names.length} model(s)...`, 'info');

        const totalSteps = pdb_model_names.length * selectedValidators.length;
        let completedSteps = 0;

        try {
            const response = await fetch('http://127.0.0.1:8091/api/run-validation', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestData)
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); 

                for (const line of lines) {
                    if (!line.startsWith('data:')) continue;
                    try {
                        const data = JSON.parse(line.substring(5));
                        const modelKey = (data.model_name || '').replace(/[^a-zA-Z0-9]/g, '-');
                        
                        if (data.event === 'start_model') {
                            const modelContainer = document.createElement('div');
                            modelContainer.id = `model-report-${modelKey}`;
                            modelContainer.className = 'model-report-container';
                            modelContainer.innerHTML = `
                                <h2>Report for ${data.model_name}</h2>
                                <div class="report-card-grid"></div>
                            `;
                            (reportsResults || reportsPage).appendChild(modelContainer);
                            currentModelReports[data.model_name] = { results_dir: data.results_dir, tools: {} };
                        } else if (data.event === 'start_tool') {
                            const modelContainer = document.querySelector(`#model-report-${modelKey}`);
                            const grid = modelContainer ? modelContainer.querySelector('.report-card-grid') : null;
                            if(grid) {
                                const card = createToolCard(data.tool, modelKey);
                                grid.appendChild(card);
                            }
                        } else if (data.event === 'finish_tool') {
                            completedSteps++;
                            const progress = totalSteps > 0 ? Math.round((completedSteps / totalSteps) * 100) : 0;
                            validationProgressBar.style.width = `${progress}%`;
                            validationProgressText.textContent = `${progress}%`;

                            updateToolCard(data.tool, modelKey, data);
                            if(currentModelReports[data.model_name]) {
                                currentModelReports[data.model_name].tools[data.tool] = data;
                            }
                        } else if (data.event === 'error') {
                            addLog(`Validation error (${data.tool || 'unknown'}): ${data.log || data.detail || 'Unknown error'}`, 'error');
                        } else if (data.error) {
                            addLog(`Validation error: ${data.error}`, 'error');
                        }

                    } catch (e) {
                        addLog(`Error parsing stream data: ${e.message}`, 'error');
                        console.error("Parsing error on line:", line);
                    }
                }
            }
        } catch (err) {
            addLog(`Validation request failed: ${err.message}`, 'error');
        } finally {
            runValidationBtn.disabled = false;
            runValidationBtn.textContent = 'Run Validation';
            const finishedCount = getResultDirsForPdf().length;
            if (finishedCount > 0) {
                setReportsStatus(`Validation complete for ${finishedCount} model(s). Click "Generate PDF" to export.`);
            } else {
                setReportsStatus('Validation finished. No report directories were produced.');
            }
            addLog('Validation stream finished.', 'info');
             if (completedSteps === totalSteps && totalSteps > 0) {
                validationProgressBar.style.width = '100%';
                validationProgressText.textContent = '100%';
            }
        }
    });

    // --- Settings Page ---
    const loadSettings = () => {
        window.api.get('/api/settings')
            .then(settings => {
                robettaUserInput.value = settings.robetta_user || '';
                robettaPassInput.value = settings.robetta_pass || '';
                qmeanEmailInput.value = settings.qmean_email || '';
                qmeanTokenInput.value = settings.qmean_token || '';
                voromqaPathInput.value = settings.voromqa_path || '';
                dsspPathInput.value = settings.dssp_path || '';
                phenixPathInput.value = settings.phenix_path || '';
                freesasaPathValue = settings.freesasa_path || '';
                addLog('Loaded settings.', 'info');
            })
            .catch(err => addLog(`Failed to load settings: ${err.message}`, 'error'));
    };

    if (saveSettingsBtn) saveSettingsBtn.addEventListener('click', () => {
        const settingsData = {
            robetta_user: robettaUserInput.value,
            robetta_pass: robettaPassInput.value,
            qmean_email: qmeanEmailInput.value,
            qmean_token: qmeanTokenInput.value,
            voromqa_path: voromqaPathInput.value,
            dssp_path: dsspPathInput.value,
            phenix_path: phenixPathInput.value,
            freesasa_path: freesasaPathValue
        };
        addLog('Saving settings...', 'info');
        window.api.post('/api/settings', settingsData)
            .then(res => addLog(res.message, 'success'))
            .catch(err => addLog(`Failed to save settings: ${err.message}`, 'error'));
    });

    if (dsspPathBrowseBtn) dsspPathBrowseBtn.addEventListener('click', () => {
        window.api.showOpenDialog({
            title: 'Select mkdssp Executable',
            properties: ['openFile']
        }).then(filePath => {
            if (filePath) {
                dsspPathInput.value = filePath;
            }
        });
    });

    if (phenixPathBrowseBtn) phenixPathBrowseBtn.addEventListener('click', () => {
        window.api.showOpenDialog({
            title: 'Select Phenix Bin Directory',
            properties: ['openDirectory']
        }).then(filePath => {
            if (filePath) {
                phenixPathInput.value = filePath;
            }
        });
    });

    // --- Initial Load ---
    const initialize = () => {
        document.querySelector('.nav-item[data-page="modeling"]').classList.add('disabled');
        document.querySelector('.nav-item[data-page="validation"]').classList.add('disabled');
        
        loadProjects();
        loadSettings();
        addLog('Application initialized. Please create or select a project.', 'info');
    };

    initialize();
});
