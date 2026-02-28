// planner/static/admin/js/mic_tracker.js

// CSRF token handling for Django
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

const csrftoken = getCookie('csrftoken');
function getCsrfToken() { return getCookie("csrftoken"); }

// Global variables for managing shared presenters
let currentAssignmentId = null;
let currentSharedPresenters = [];

// Update a single field via AJAX
async function updateField(assignmentId, field, value) {
    try {
        const response = await fetch('/audiopatch/api/mic/update/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken
            },
            body: JSON.stringify({
                assignment_id: assignmentId,
                field: field,
                value: value
            })
        });

        const data = await response.json();
        
        if (data.success) {
            // Update UI with new stats
            updateSessionStats(assignmentId, data.session_stats);
            updateDayStats(data.day_stats);
            
            // Update presenter display if needed
            if (field === 'presenter_name' || field === 'presenter_id' || field === 'shared_presenters') {
                updatePresenterDisplay(assignmentId, data.presenter_display, data.presenter_count);
                // Update active slot chip
                const activeChip = document.querySelector(`#slot-queue-${assignmentId} .a2-slot-chip.active`);
                if (activeChip) activeChip.textContent = data.presenter_display || 'Unassigned';
            }
            
            // Visual feedback
            flashElement(document.querySelector(`[data-assignment-id="${assignmentId}"]`), 'success');
            
            return data;
        } else {
            console.error('Update failed:', data.error);
            showNotification('Update failed: ' + data.error, 'error');
            throw new Error(data.error);
        }
    } catch (error) {
        console.error('Error updating field:', error);
        showNotification('Error updating field', 'error');
        throw error;
    }
}

// Bulk update operations
async function bulkUpdate(sessionId, action) {
    if (action === 'clear_all' && !confirm('Clear all assignments in this session?')) {
        return;
    }
    
    try {
        const response = await fetch('/audiopatch/api/mic/bulk-update/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken
            },
            body: JSON.stringify({
                session_id: sessionId,
                action: action
            })
        });

        const data = await response.json();
        
        if (data.success) {
            location.reload();
        } else {
            showNotification('Bulk update failed: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('Error in bulk update:', error);
        showNotification('Error in bulk update', 'error');
    }
}

// Toggle day collapse/expand
async function toggleDay(dayId) {
    const daySection = document.querySelector(`[data-day-id="${dayId}"]`);
    const dayContent = daySection.querySelector('.day-content');
    const collapseIcon = daySection.querySelector('.collapse-icon');
    const isCollapsed = daySection.dataset.collapsed === 'true';
    
    if (isCollapsed) {
        dayContent.style.display = 'block';
        collapseIcon.textContent = '▼';
        daySection.dataset.collapsed = 'false';
    } else {
        dayContent.style.display = 'none';
        collapseIcon.textContent = '▶';
        daySection.dataset.collapsed = 'true';
    }
    
    try {
        await fetch('/audiopatch/api/day/toggle/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken
            },
            body: JSON.stringify({
                day_id: dayId
            })
        });
    } catch (error) {
        console.error('Error saving day state:', error);
    }
}

// Expand all days
function expandAllDays() {
    document.querySelectorAll('.day-section').forEach(daySection => {
        const dayContent = daySection.querySelector('.day-content');
        const collapseIcon = daySection.querySelector('.collapse-icon');
        dayContent.style.display = 'block';
        collapseIcon.textContent = '▼';
        daySection.dataset.collapsed = 'false';
    });
}

// Collapse all days
function collapseAllDays() {
    document.querySelectorAll('.day-section').forEach(daySection => {
        const dayContent = daySection.querySelector('.day-content');
        const collapseIcon = daySection.querySelector('.collapse-icon');
        dayContent.style.display = 'none';
        collapseIcon.textContent = '▶';
        daySection.dataset.collapsed = 'true';
    });
}

// ============ SHARED PRESENTER DIALOG FUNCTIONS ============

function showSharedPresenterDialog(assignmentId) {
    currentAssignmentId = assignmentId;
    
    const modal = document.getElementById('sharedPresenterModal');
    if (modal) {
        modal.style.display = 'block';
        const listContainer = document.getElementById('sharedPresentersList');
        if (listContainer) {
            listContainer.innerHTML = '<div class="loading">Loading...</div>';
        }
    }
    
    fetch(`/audiopatch/api/mic/get-assignment/${assignmentId}/`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const assignment = data.assignment;
                
                const mainPresenterSpan = document.getElementById('modalMainPresenter');
                if (mainPresenterSpan) {
                    mainPresenterSpan.textContent = assignment.presenter || '(No main presenter)';
                }
                
                currentSharedPresenters = assignment.shared_presenters || [];
                updateSharedPresentersList();
                
                const input = document.getElementById('newPresenterInput');
                if (input) {
                    input.value = '';
                    input.focus();
                }
            } else {
                console.error('Failed to fetch assignment details:', data.error);
                showNotification('Failed to load presenter details', 'error');
                closeSharedPresenterModal();
            }
        })
        .catch(error => {
            console.error('Error fetching assignment details:', error);
            showNotification('Error loading presenter details', 'error');
            closeSharedPresenterModal();
        });
}

// Update the shared presenters list display
function updateSharedPresentersList() {
    const listContainer = document.getElementById('sharedPresentersList');
    
    if (!listContainer) return;
    
    listContainer.innerHTML = '';
    
    if (currentSharedPresenters.length === 0) {
        listContainer.innerHTML = '<div class="no-presenters">No shared presenters added</div>';
        return;
    }
    
    currentSharedPresenters.forEach((presenter, index) => {
        const item = document.createElement('div');
        item.className = 'shared-presenter-item';
        item.innerHTML = `
            <span>${presenter}</span>
            <button type="button" class="remove-btn" onclick="removeSharedPresenterModal(${index})" title="Remove">×</button>
        `;
        listContainer.appendChild(item);
    });
}

// Add a new shared presenter (modal version)
function addSharedPresenter() {
    const input = document.getElementById('newPresenterInput');
    if (!input) return;
    
    const presenterName = input.value.trim();
    
    if (!presenterName) {
        showNotification('Please enter a presenter name', 'warning');
        input.focus();
        return;
    }
    
    if (currentSharedPresenters.includes(presenterName)) {
        showNotification('This presenter has already been added', 'warning');
        input.focus();
        return;
    }
    
    currentSharedPresenters.push(presenterName);
    updateSharedPresentersList();
    input.value = '';
    input.focus();
}

// Remove a shared presenter (modal version)
function removeSharedPresenterModal(index) {
    if (index >= 0 && index < currentSharedPresenters.length) {
        const removedName = currentSharedPresenters[index];
        currentSharedPresenters.splice(index, 1);
        updateSharedPresentersList();
        showNotification(`Removed: ${removedName}`, 'info');
    }
}

// Save shared presenters to the database
function saveSharedPresenters() {
    if (!currentAssignmentId) {
        console.error('No assignment ID available');
        return;
    }
    
    const saveBtn = document.querySelector('.save-btn');
    if (saveBtn) {
        saveBtn.textContent = 'Saving...';
        saveBtn.disabled = true;
    }
    
    updateField(currentAssignmentId, 'shared_presenters', JSON.stringify(currentSharedPresenters))
        .then((data) => {
            updatePresenterButtonDisplay(currentAssignmentId);
            
            const cell = document.querySelector(`[data-id="${currentAssignmentId}"][data-field="presenter"]`);
            if (!cell) {
                const row = document.querySelector(`[data-assignment-id="${currentAssignmentId}"]`);
                if (row) {
                    const presenterCell = row.querySelector('.col-presenter');
                    if (presenterCell) {
                        updateCellDisplay(presenterCell, currentSharedPresenters);
                    }
                }
            } else {
                updateCellDisplay(cell, currentSharedPresenters);
            }
            
            showNotification(`Saved ${currentSharedPresenters.length} shared presenter(s)`, 'success');
            closeSharedPresenterModal();
        })
        .catch(error => {
            console.error('Error saving shared presenters:', error);
            showNotification('Failed to save shared presenters', 'error');
            
            if (saveBtn) {
                saveBtn.textContent = 'Save Changes';
                saveBtn.disabled = false;
            }
        });
}

// Update the presenter button display
function updatePresenterButtonDisplay(assignmentId) {
    const row = document.querySelector(`[data-assignment-id="${assignmentId}"]`);
    if (!row) return;
    
    const shareBtn = row.querySelector('.btn-share-presenter');
    const inputGroup = row.querySelector('.presenter-input-group');
    
    if (shareBtn && currentSharedPresenters.length > 0) {
        shareBtn.innerHTML = `<span class="share-count">+${currentSharedPresenters.length}</span>`;
        if (inputGroup) inputGroup.classList.add('has-shared');
        shareBtn.title = `Shared with: ${currentSharedPresenters.join(', ')}`;
    } else if (shareBtn) {
        shareBtn.innerHTML = '<span class="share-icon">👥</span>';
        shareBtn.title = 'Manage shared presenters';
        if (inputGroup) inputGroup.classList.remove('has-shared');
    }
}

// Helper function to update cell display
function updateCellDisplay(cell, sharedPresenters) {
    const inputGroup = cell.querySelector('.presenter-input-group');
    if (inputGroup) {
        const shareBtn = inputGroup.querySelector('.btn-share-presenter');
        if (shareBtn) {
            if (sharedPresenters.length > 0) {
                shareBtn.innerHTML = `<span class="share-count">+${sharedPresenters.length}</span>`;
                inputGroup.classList.add('has-shared');
                shareBtn.title = `Shared with: ${sharedPresenters.join(', ')}`;
            } else {
                shareBtn.innerHTML = '<span class="share-icon">👥</span>';
                shareBtn.title = 'Manage shared presenters';
                inputGroup.classList.remove('has-shared');
            }
        }
        return;
    }
    
    // Fallback for old structure
    const mainPresenter = cell.textContent.trim().replace(/\s*\(\+\d+\)/, '');
    
    if (sharedPresenters.length > 0) {
        const displayText = mainPresenter ?
            `${mainPresenter} (+${sharedPresenters.length})` :
            `${sharedPresenters[0]}${sharedPresenters.length > 1 ? ` (+${sharedPresenters.length - 1})` : ''}`;
        cell.textContent = displayText;
        cell.classList.add('has-shared');
    } else {
        cell.textContent = mainPresenter;
        cell.classList.remove('has-shared');
    }
}

// Close the shared presenter modal
function closeSharedPresenterModal() {
    const modal = document.getElementById('sharedPresenterModal');
    if (modal) {
        modal.style.display = 'none';
    }
    
    currentAssignmentId = null;
    currentSharedPresenters = [];
    
    const input = document.getElementById('newPresenterInput');
    if (input) input.value = '';
    
    const saveBtn = document.querySelector('.save-btn');
    if (saveBtn) {
        saveBtn.textContent = 'Save Changes';
        saveBtn.disabled = false;
    }
}

// ============ INLINE SHARED PRESENTER FUNCTIONS ============

function togglePresenters(assignmentId) {
    const row = document.querySelector(`[data-assignment-id="${assignmentId}"]`);
    if (!row) return;
    
    const container = row.querySelector('.shared-presenters-container');
    const expandBtn = row.querySelector('.btn-expand-presenters, .btn-add-presenter');
    
    if (!container) return;
    
    const isVisible = container.style.display !== 'none';
    
    if (isVisible) {
        container.style.display = 'none';
        if (expandBtn && expandBtn.querySelector('.expand-icon')) {
            expandBtn.querySelector('.expand-icon').textContent = '▶';
        }
    } else {
        container.style.display = 'block';
        if (expandBtn && expandBtn.querySelector('.expand-icon')) {
            expandBtn.querySelector('.expand-icon').textContent = '▼';
        }
        
        const addInput = container.querySelector('.add-presenter-input');
        if (addInput) {
            setTimeout(() => addInput.focus(), 100);
        }
    }
}

async function addSharedPresenterInline(assignmentId) {
    const input = document.getElementById(`newPresenter_${assignmentId}`);
    if (!input) return;
    
    const presenterName = input.value.trim();
    
    if (!presenterName) {
        showNotification('Please enter a presenter name', 'warning');
        input.focus();
        return;
    }
    
    try {
        const response = await fetch('/audiopatch/api/mic/add-shared-presenter/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken
            },
            body: JSON.stringify({
                assignment_id: assignmentId,
                presenter_name: presenterName
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification(data.message, 'success');
            input.value = '';
            setTimeout(() => location.reload(), 500);
        } else {
            showNotification(data.error || 'Failed to add presenter', 'error');
        }
    } catch (error) {
        console.error('Error adding shared presenter:', error);
        showNotification('Error adding presenter', 'error');
    }
}

async function removeSharedPresenter(assignmentId, presenterName) {
    if (!confirm(`Remove ${presenterName} from shared presenters?`)) {
        return;
    }
    
    try {
        const response = await fetch('/audiopatch/api/mic/remove-shared-presenter/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken
            },
            body: JSON.stringify({
                assignment_id: assignmentId,
                presenter_name: presenterName
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification(data.message, 'success');
            setTimeout(() => location.reload(), 500);
        } else {
            showNotification(data.error || 'Failed to remove presenter', 'error');
        }
    } catch (error) {
        console.error('Error removing shared presenter:', error);
        showNotification('Error removing presenter', 'error');
    }
}

async function handleDmicChange(assignmentId, isChecked) {
    const checkbox = document.querySelector(
        `[data-assignment-id="${assignmentId}"] .dmic-checkbox`
    );
    
    if (!checkbox) {
        console.error('Checkbox not found for assignment:', assignmentId);
        return;
    }
    
    const currentState = checkbox.checked;
    checkbox.checked = !currentState;
    
    try {
        const response = await fetch('/audiopatch/api/mic/dmic-and-rotate/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken
            },
            body: JSON.stringify({
                assignment_id: assignmentId
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification(data.message, 'success');
            checkbox.checked = data.is_d_mic;
            
            const micdCheckbox = document.querySelector(
                `[data-assignment-id="${assignmentId}"] .mic-checkbox:not(.dmic-checkbox)`
            );
            if (micdCheckbox && data.is_micd !== undefined) {
                micdCheckbox.checked = data.is_micd;
            }
            
            if (data.current_presenter !== data.previous_presenter) {
                setTimeout(() => location.reload(), 800);
            }
        } else {
            showNotification(data.error || 'Failed to update D-MIC status', 'error');
            checkbox.checked = currentState;
        }
    } catch (error) {
        console.error('Error updating D-MIC:', error);
        showNotification('Error updating D-MIC status', 'error');
        checkbox.checked = currentState;
    }
}

async function resetPresenterRotation(assignmentId) {
    if (!confirm('Reset to primary presenter?')) {
        return;
    }
    
    try {
        const response = await fetch('/audiopatch/api/mic/reset-rotation/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken
            },
            body: JSON.stringify({
                assignment_id: assignmentId
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification(data.message, 'success');
            setTimeout(() => location.reload(), 500);
        } else {
            showNotification(data.error || 'Failed to reset rotation', 'error');
        }
    } catch (error) {
        console.error('Error resetting rotation:', error);
        showNotification('Error resetting rotation', 'error');
    }
}

// ============ UI UPDATE FUNCTIONS ============

function updateSessionStats(assignmentId, stats) {
    const row = document.querySelector(`[data-assignment-id="${assignmentId}"]`);
    if (!row) return;
    
    const sessionColumn = row.closest('.session-column');
    if (!sessionColumn) return;
    
    const footer = sessionColumn.querySelector('.session-footer');
    if (!footer) return;
    
    footer.innerHTML = `
        <span class="session-stat">MIC'D: ${stats.micd}/${stats.total}</span>
        <span class="session-stat">Available: ${stats.total - stats.micd}</span>
        ${stats.shared > 0 ? `<span class="session-stat">Shared: ${stats.shared}</span>` : ''}
    `;
}

function updateDayStats(stats) {
    console.log('Day stats updated:', stats);
}

function updatePresenterDisplay(assignmentId, displayText, presenterCount) {
    const row = document.querySelector(`[data-assignment-id="${assignmentId}"]`);
    if (!row) return;
    
    const presenterCell = row.querySelector('.col-presenter');
    if (!presenterCell) return;
    
    const shareBtn = presenterCell.querySelector('.btn-share-presenter');
    if (shareBtn && presenterCount > 1) {
        shareBtn.innerHTML = `<span class="share-count">+${presenterCount - 1}</span>`;
        const inputGroup = presenterCell.querySelector('.presenter-input-group');
        if (inputGroup) inputGroup.classList.add('has-shared');
        return;
    }
    
    const existingIndicator = presenterCell.querySelector('.shared-indicator');
    if (existingIndicator) existingIndicator.remove();
    
    if (presenterCount > 1) {
        const indicator = document.createElement('span');
        indicator.className = 'shared-indicator';
        indicator.title = displayText;
        indicator.textContent = ` (+${presenterCount - 1})`;
        presenterCell.appendChild(indicator);
    }
}

// Visual feedback
function flashElement(element, type) {
    if (!element) return;
    
    element.classList.remove('flash-success', 'flash-error');
    
    setTimeout(() => {
        if (type === 'success') {
            element.classList.add('flash-success');
        } else {
            element.classList.add('flash-error');
        }
    }, 10);
    
    setTimeout(() => {
        element.classList.remove('flash-success', 'flash-error');
    }, 510);
}

// Show notification
function showNotification(message, type = 'info') {
    const existingNotifications = document.querySelectorAll('.notification');
    existingNotifications.forEach(n => n.remove());
    
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 20px;
        border-radius: 4px;
        z-index: 10000;
        animation: slideIn 0.3s ease;
        box-shadow: 0 2px 5px rgba(0,0,0,0.3);
    `;
    
    switch(type) {
        case 'success':
            notification.style.backgroundColor = '#4caf50';
            notification.style.color = 'white';
            break;
        case 'error':
            notification.style.backgroundColor = '#f44336';
            notification.style.color = 'white';
            break;
        case 'warning':
            notification.style.backgroundColor = '#ff9800';
            notification.style.color = 'white';
            break;
        default:
            notification.style.backgroundColor = '#2196F3';
            notification.style.color = 'white';
    }
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// ============ SESSION MANAGEMENT FUNCTIONS ============

// ── Add Day Modal ─────────────────────────────────────────────
function openAddDayModal() {
    // Default date to today
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('add-day-date').value = today;
    document.getElementById('add-day-name').value = '';
    document.getElementById('add-day-error').style.display = 'none';
    document.getElementById('add-day-modal').classList.remove('hidden');
    setTimeout(() => document.getElementById('add-day-name').focus(), 50);
}

function closeAddDayModal() {
    document.getElementById('add-day-modal').classList.add('hidden');
}

async function submitAddDay() {
    const date = document.getElementById('add-day-date').value;
    const name = document.getElementById('add-day-name').value.trim();
    const errEl = document.getElementById('add-day-error');

    if (!date) { errEl.textContent = 'Please select a date.'; errEl.style.display = 'block'; return; }
    errEl.style.display = 'none';

    try {
        const resp = await fetch('/audiopatch/api/day/create/', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken()},
            body: JSON.stringify({ date: date, name: name })
        });
        const data = await resp.json();
        if (data.success) {
            closeAddDayModal();
            location.reload();
        } else {
            errEl.textContent = data.error || 'Failed to create day.';
            errEl.style.display = 'block';
        }
    } catch(e) {
        errEl.textContent = 'Network error. Please try again.';
        errEl.style.display = 'block';
    }
}

// ── Add Session Modal ──────────────────────────────────────────
let _addSessionDayId = null;

function openAddSessionModal(dayId) {
    _addSessionDayId = dayId;
    document.getElementById('add-session-name').value = '';
    document.getElementById('add-session-mics').value = '16';
    document.getElementById('add-session-location').value = '';
    document.getElementById('add-session-error').style.display = 'none';
    document.getElementById('add-session-submit').disabled = false;
    document.getElementById('add-session-modal').classList.remove('hidden');
    setTimeout(() => document.getElementById('add-session-name').focus(), 50);
}

function closeAddSessionModal() {
    document.getElementById('add-session-modal').classList.add('hidden');
    _addSessionDayId = null;
}

async function submitAddSession() {
    const name = document.getElementById('add-session-name').value.trim();
    const numMics = parseInt(document.getElementById('add-session-mics').value);
    const location = document.getElementById('add-session-location').value.trim();
    const errEl = document.getElementById('add-session-error');
    const submitBtn = document.getElementById('add-session-submit');

    if (!name) { errEl.textContent = 'Please enter a session name.'; errEl.style.display = 'block'; return; }
    if (!numMics || numMics < 1 || numMics > 100) { errEl.textContent = 'Mic count must be between 1 and 100.'; errEl.style.display = 'block'; return; }
    if (!_addSessionDayId) { errEl.textContent = 'No day selected.'; errEl.style.display = 'block'; return; }
    errEl.style.display = 'none';
    submitBtn.disabled = true;
    submitBtn.textContent = 'Adding...';

    try {
        const resp = await fetch('/audiopatch/api/session/create/', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken()},
            body: JSON.stringify({ day_id: _addSessionDayId, name: name, num_mics: numMics, location: location })
        });
        const data = await resp.json();
        if (data.success) {
            closeAddSessionModal();
            location.reload();
        } else {
            errEl.textContent = data.error || 'Failed to create session.';
            errEl.style.display = 'block';
            submitBtn.disabled = false;
            submitBtn.textContent = 'Add Session';
        }
    } catch(e) {
        errEl.textContent = 'Network error. Please try again.';
        errEl.style.display = 'block';
        submitBtn.disabled = false;
        submitBtn.textContent = 'Add Session';
    }
}

// Close modals on backdrop click
document.addEventListener('DOMContentLoaded', function() {
    document.getElementById('add-day-modal').addEventListener('mousedown', function(e) {
        if (e.target === this) closeAddDayModal();
    });
    document.getElementById('add-session-modal').addEventListener('mousedown', function(e) {
        if (e.target === this) closeAddSessionModal();
    });
});

// Enter key support for modals
document.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
        if (!document.getElementById('add-day-modal').classList.contains('hidden')) submitAddDay();
        else if (!document.getElementById('add-session-modal').classList.contains('hidden')) submitAddSession();
    }
});

function addNewDay() { openAddDayModal(); }  // legacy alias

function addSession(dayId, columnPosition = 0) { openAddSessionModal(dayId); }  // legacy alias

function editSession(sessionId) {
    window.location.href = `/admin/planner/micsession/${sessionId}/change/`;
}

async function duplicateSession(sessionId) {
    const targetSessionName = prompt('Enter name for duplicated session:');
    if (!targetSessionName) return;
    
    try {
        const response = await fetch('/audiopatch/api/session/duplicate/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken
            },
            body: JSON.stringify({
                source_session_id: sessionId,
                target_session_name: targetSessionName
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification(data.message, 'success');
            setTimeout(() => location.reload(), 1000);
        } else {
            showNotification('Duplication failed: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('Error duplicating session:', error);
        showNotification('Error duplicating session', 'error');
    }
}

// ============ PHOTO UPLOAD — SLOT-BASED ============
// Each presenter slot has its own discrete photo stored on PresenterSlot.photo.
// All photo functions use slot_id as the key, never assignment_id.

/**
 * Trigger the hidden file input for a specific presenter slot.
 * Called by onclick on the .a2-photo-zone in the template.
 */
function triggerPhotoForSlot(slotId, assignmentId) {
    if (!slotId) return;
    const input = document.getElementById('photo-input-slot-' + slotId);
    if (input) input.click();
}

/**
 * Upload a photo for a specific presenter slot.
 * Posts to /audiopatch/api/mic/slot/upload-photo/ with slot_id.
 * Updates the photo zone in the card without a page reload.
 */
async function uploadPhotoForSlot(slotId, assignmentId, input) {
    if (!slotId || !input.files || !input.files[0]) return;

    const fd = new FormData();
    fd.append('slot_id', slotId);
    fd.append('photo', input.files[0]);

    try {
        const resp = await fetch('/audiopatch/api/mic/slot/upload-photo/', {
            method: 'POST',
            headers: { 'X-CSRFToken': csrftoken },
            body: fd
        });
        const data = await resp.json();

        if (data.success && data.photo_url) {
            const zone = document.getElementById('photo-zone-' + assignmentId);
            if (!zone) return;

            // Hide placeholder
            const placeholder = document.getElementById('photo-placeholder-' + assignmentId);
            if (placeholder) placeholder.style.display = 'none';

            // Update or create the thumbnail
            let img = document.getElementById('photo-img-' + assignmentId);
            if (!img) {
                img = document.createElement('img');
                img.id = 'photo-img-' + assignmentId;
                img.style.cssText = 'width:70px;height:70px;object-fit:cover;border-radius:5px;display:block;';
                zone.insertBefore(img, zone.firstChild);
            }
            img.style.display = 'block';
            img.src = data.photo_url;

            // Update or create the hover-expand panel
            let expandImg = document.getElementById('photo-expand-' + assignmentId);
            if (!expandImg) {
                const wrapper = document.createElement('div');
                wrapper.className = 'a2-photo-expand';
                expandImg = document.createElement('img');
                expandImg.id = 'photo-expand-' + assignmentId;
                wrapper.appendChild(expandImg);
                zone.appendChild(wrapper);
            }
            expandImg.src = data.photo_url;

            showNotification('Photo saved', 'success');
        } else {
            showNotification('Photo upload failed: ' + (data.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Photo upload error:', error);
        showNotification('Photo upload failed', 'error');
    }
}

// ============ MIC GROUPS ============

var currentGroupSessionId = null;
var sessionGroups = {};
var GROUP_COLORS = {
    blue:   '#4a9eff',
    amber:  '#ffab00',
    red:    '#ff5252',
    purple: '#b464ff',
    teal:   '#00bcd4'
};

function loadGroups(sessionId, callback) {
    fetch('/audiopatch/api/mic-groups/' + sessionId + '/')
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                sessionGroups[sessionId] = data.groups;
                if (callback) callback(data.groups);
            }
        });
}

function openGroupPicker(assignmentId, sessionId, dotEl) {
    document.querySelectorAll('.group-picker.open').forEach(p => p.classList.remove('open'));
    var picker = document.getElementById('group-picker-' + assignmentId);
    if (!picker) return;
    loadGroups(sessionId, function(groups) {
        picker.innerHTML = '';
        var title = document.createElement('div');
        title.className = 'group-picker-title';
        title.textContent = 'Assign Group';
        picker.appendChild(title);

        var noneItem = document.createElement('div');
        noneItem.className = 'group-picker-none';
        noneItem.textContent = '— No Group —';
        noneItem.onmousedown = function(e) {
            e.preventDefault();
            assignGroup(assignmentId, null, null, null, dotEl);
            picker.classList.remove('open');
        };
        picker.appendChild(noneItem);

        if (groups.length > 0) {
            var div = document.createElement('div');
            div.className = 'group-picker-divider';
            picker.appendChild(div);
        }

        groups.forEach(function(g) {
            var item = document.createElement('div');
            item.className = 'group-picker-item';
            item.innerHTML = '<span style="width:12px;height:12px;border-radius:50%;background:' + GROUP_COLORS[g.color] + ';display:inline-block;flex-shrink:0;"></span> ' + g.name;
            item.onmousedown = function(e) {
                e.preventDefault();
                assignGroup(assignmentId, g.id, g.name, g.color, dotEl);
                picker.classList.remove('open');
            };
            picker.appendChild(item);
        });

        var divider2 = document.createElement('div');
        divider2.className = 'group-picker-divider';
        picker.appendChild(divider2);

        var manageBtn = document.createElement('div');
        manageBtn.className = 'group-picker-manage';
        manageBtn.textContent = '⚙ Manage Groups...';
        manageBtn.onmousedown = function(e) {
            e.preventDefault();
            picker.classList.remove('open');
            openGroupManager(sessionId);
        };
        picker.appendChild(manageBtn);

        var dotRect = dotEl.getBoundingClientRect();
        var spaceBelow = window.innerHeight - dotRect.bottom;
        if (spaceBelow < 200) {
            picker.style.bottom = '100%';
            picker.style.top = 'auto';
        } else {
            picker.style.top = '100%';
            picker.style.bottom = 'auto';
        }
        picker.classList.add('open');
    });
}

function assignGroup(assignmentId, groupId, groupName, groupColor, dotEl) {
    fetch('/audiopatch/api/mic-groups/assign/', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken()},
        body: JSON.stringify({assignment_id: assignmentId, group_id: groupId})
    })
    .then(r => r.json())
    .then(function(data) {
        if (data.success) {
            dotEl.className = 'group-dot ' + (groupColor ? 'color-' + groupColor : 'empty');
            dotEl.title = groupName || 'Assign group';
            var row = document.getElementById('a1-row-' + assignmentId);
            if (row) {
                row.classList.remove('group-blue', 'group-amber', 'group-red', 'group-purple', 'group-teal');
                if (groupColor) row.classList.add('group-' + groupColor);
            }
        }
    });
}

function openGroupManager(sessionId) {
    currentGroupSessionId = sessionId;
    var modal = document.getElementById('group-manage-modal');
    modal.classList.remove('hidden');
    refreshGroupManagerList(sessionId);
}

function closeGroupManager() {
    document.getElementById('group-manage-modal').classList.add('hidden');
    currentGroupSessionId = null;
}

function refreshGroupManagerList(sessionId) {
    loadGroups(sessionId, function(groups) {
        var list = document.getElementById('group-manage-list');
        list.innerHTML = '';
        if (groups.length === 0) {
            list.innerHTML = '<div style="color:var(--text-dim);font-size:12px;padding:8px 0;">No groups yet. Add one below.</div>';
            return;
        }
        groups.forEach(function(g) {
            var item = document.createElement('div');
            item.className = 'group-manage-item';
            item.innerHTML = '<span style="width:14px;height:14px;border-radius:50%;background:' + GROUP_COLORS[g.color] + ';display:inline-block;flex-shrink:0;"></span>' +
                '<span class="group-manage-name">' + g.name + '</span>' +
                '<button class="group-manage-delete" onclick="deleteGroup(' + g.id + ',' + sessionId + ')">✕</button>';
            list.appendChild(item);
        });
    });
}

function addGroup() {
    var name = document.getElementById('group-add-name').value.trim();
    var color = document.getElementById('group-add-color').value;
    if (!name || !currentGroupSessionId) return;
    fetch('/audiopatch/api/mic-groups/' + currentGroupSessionId + '/', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken()},
        body: JSON.stringify({action: 'create', name: name, color: color})
    })
    .then(r => r.json())
    .then(function(data) {
        if (data.success) {
            document.getElementById('group-add-name').value = '';
            delete sessionGroups[currentGroupSessionId];
            refreshGroupManagerList(currentGroupSessionId);
        }
    });
}

function deleteGroup(groupId, sessionId) {
    if (!confirm('Delete this group? Assignments will be unassigned.')) return;
    fetch('/audiopatch/api/mic-groups/' + sessionId + '/', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken()},
        body: JSON.stringify({action: 'delete', group_id: groupId})
    })
    .then(r => r.json())
    .then(function(data) {
        if (data.success) {
            delete sessionGroups[sessionId];
            refreshGroupManagerList(sessionId);
            document.querySelectorAll('[data-session-id="' + sessionId + '"] .a1-row').forEach(function(row) {
                row.classList.remove('group-blue', 'group-amber', 'group-red', 'group-purple', 'group-teal');
            });
            document.querySelectorAll('[data-session-id="' + sessionId + '"] .group-dot').forEach(function(dot) {
                dot.className = 'group-dot empty';
                dot.title = 'Assign group';
            });
        }
    });
}

document.addEventListener('mousedown', function(e) {
    if (!e.target.closest('.group-picker') && !e.target.classList.contains('group-dot')) {
        document.querySelectorAll('.group-picker.open').forEach(function(p) { p.classList.remove('open'); });
    }
});

// ============ INITIALIZATION ============

document.addEventListener('DOMContentLoaded', function() {
    // Initialize existing shared presenter indicators
    document.querySelectorAll('.btn-share-presenter').forEach(btn => {
        const countSpan = btn.querySelector('.share-count');
        if (countSpan) {
            const row = btn.closest('[data-assignment-id]');
            if (row) {
                const inputGroup = row.querySelector('.presenter-input-group');
                if (inputGroup) inputGroup.classList.add('has-shared');
            }
        }
    });

    // Enter key in modal presenter input
    const input = document.getElementById('newPresenterInput');
    if (input) {
        input.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                addSharedPresenter();
            }
        });
    }
    
    // Close modal on outside click
    const modal = document.getElementById('sharedPresenterModal');
    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) closeSharedPresenterModal();
        });
    }
    
    // Double-click handler for presenter cells (backward compatibility)
    document.addEventListener('dblclick', function(e) {
        const cell = e.target.closest('.editable[data-field="presenter"], .col-presenter');
        if (cell) {
            if (e.target.closest('.btn-share-presenter') || e.target.tagName === 'INPUT') return;
            e.preventDefault();
            let assignmentId = cell.dataset.id || cell.dataset.assignmentId;
            if (!assignmentId) {
                const row = cell.closest('[data-assignment-id]');
                if (row) assignmentId = row.dataset.assignmentId;
            }
            if (assignmentId) showSharedPresenterDialog(assignmentId);
        }
    });
    
    // Keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        if (e.ctrlKey && e.key === 'e') { e.preventDefault(); expandAllDays(); }
        if (e.ctrlKey && e.key === 'l') { e.preventDefault(); collapseAllDays(); }
        if (e.key === 'Escape') {
            const modal = document.getElementById('sharedPresenterModal');
            if (modal && modal.style.display !== 'none') closeSharedPresenterModal();
        }
    });
    
    // Add CSS animations
    if (!document.getElementById('notification-animations')) {
        const style = document.createElement('style');
        style.id = 'notification-animations';
        style.textContent = `
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes slideOut {
                from { transform: translateX(0); opacity: 1; }
                to { transform: translateX(100%); opacity: 0; }
            }
            .flash-success {
                background-color: rgba(76, 175, 80, 0.1) !important;
                transition: background-color 0.5s ease;
            }
            .flash-error {
                background-color: rgba(244, 67, 54, 0.1) !important;
                transition: background-color 0.5s ease;
            }
            .loading {
                text-align: center;
                padding: 20px;
                color: #888;
                font-style: italic;
            }
        `;
        document.head.appendChild(style);
    }
    
    console.log('Mic Tracker initialized');

    // Restore saved session tabs after reload
    document.querySelectorAll('[data-session-id]').forEach(session => {
        const sessionId = session.dataset.sessionId;
        const savedTab = localStorage.getItem('sessionTab-' + sessionId);
        if (savedTab) {
            const btn = session.querySelector(`.session-tab[onclick*="${savedTab}"]`);
            if (btn) btn.click();
        }
    });
});

// Load presenters for datalist autocomplete
async function loadPresentersList() {
    try {
        const response = await fetch('/audiopatch/api/presenters/list/');
        const data = await response.json();
        
        if (data.presenters) {
            const datalist = document.getElementById('presenters-datalist');
            datalist.innerHTML = '';
            data.presenters.forEach(presenter => {
                const option = document.createElement('option');
                option.value = presenter.name;
                datalist.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading presenters list:', error);
    }
}

document.addEventListener('DOMContentLoaded', loadPresentersList);
async function deleteSession(sessionId) {
    if (!confirm('Delete this session and all its mic assignments? This cannot be undone.')) return;
    try {
        const response = await fetch('/audiopatch/api/mic/delete-session/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
            body: JSON.stringify({ session_id: sessionId })
        });
        const data = await response.json();
        if (data.success) {
            location.reload();
        } else {
            alert('Failed to delete session: ' + (data.error || 'Unknown error'));
        }
    } catch (e) {
        alert('Error deleting session');
    }
}
