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
            if (field === 'presenter_name' || field === 'shared_presenters') {
                updatePresenterDisplay(assignmentId, data.presenter_display, data.presenter_count);
            }
            
            // Visual feedback
            flashElement(document.querySelector(`[data-assignment-id="${assignmentId}"]`), 'success');
            
            return data; // Return data for further processing
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
            // Reload the section or update UI
            location.reload(); // Simple solution, could be optimized
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
    
    // Toggle UI immediately for responsiveness
    if (isCollapsed) {
        dayContent.style.display = 'block';
        collapseIcon.textContent = '▼';
        daySection.dataset.collapsed = 'false';
    } else {
        dayContent.style.display = 'none';
        collapseIcon.textContent = '▶';
        daySection.dataset.collapsed = 'true';
    }
    
    // Save state to server
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

// Show the shared presenter dialog with better feedback
function showSharedPresenterDialog(assignmentId) {
    currentAssignmentId = assignmentId;
    
    // Show loading state
    const modal = document.getElementById('sharedPresenterModal');
    if (modal) {
        modal.style.display = 'block';
        const listContainer = document.getElementById('sharedPresentersList');
        if (listContainer) {
            listContainer.innerHTML = '<div class="loading">Loading...</div>';
        }
    }
    
    // Fetch assignment details from the server
    fetch(`/audiopatch/api/mic/get-assignment/${assignmentId}/`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const assignment = data.assignment;
                
                // Set the main presenter in the modal
                const mainPresenterSpan = document.getElementById('modalMainPresenter');
                if (mainPresenterSpan) {
                    mainPresenterSpan.textContent = assignment.presenter || '(No main presenter)';
                }
                
                // Store and display shared presenters
                currentSharedPresenters = assignment.shared_presenters || [];
                updateSharedPresentersList();
                
                // Focus on the input field
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
    
    // Clear existing list
    listContainer.innerHTML = '';
    
    if (currentSharedPresenters.length === 0) {
        listContainer.innerHTML = '<div class="no-presenters">No shared presenters added</div>';
        return;
    }
    
    // Create list items for each shared presenter
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
    
    // Check if presenter already exists
    if (currentSharedPresenters.includes(presenterName)) {
        showNotification('This presenter has already been added', 'warning');
        input.focus();
        return;
    }
    
    // Add to the array
    currentSharedPresenters.push(presenterName);
    
    // Update the display
    updateSharedPresentersList();
    
    // Clear the input and focus for next entry
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
    
    // Show saving state
    const saveBtn = document.querySelector('.save-btn');
    if (saveBtn) {
        saveBtn.textContent = 'Saving...';
        saveBtn.disabled = true;
    }
    
    // Use the existing updateField function to save
    updateField(currentAssignmentId, 'shared_presenters', JSON.stringify(currentSharedPresenters))
        .then((data) => {
            // Update the button display
            updatePresenterButtonDisplay(currentAssignmentId);
            
            // Update any existing cell display
            const cell = document.querySelector(`[data-id="${currentAssignmentId}"][data-field="presenter"]`);
            if (!cell) {
                // Try alternative selector
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
            
            // Close the modal
            closeSharedPresenterModal();
        })
        .catch(error => {
            console.error('Error saving shared presenters:', error);
            showNotification('Failed to save shared presenters', 'error');
            
            // Reset save button
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
        // Update button to show count
        shareBtn.innerHTML = `<span class="share-count">+${currentSharedPresenters.length}</span>`;
        
        // Add visual indicator
        if (inputGroup) {
            inputGroup.classList.add('has-shared');
        }
        
        // Update button title with names
        const names = currentSharedPresenters.join(', ');
        shareBtn.title = `Shared with: ${names}`;
    } else if (shareBtn) {
        // Reset to default icon
        shareBtn.innerHTML = '<span class="share-icon">👥</span>';
        shareBtn.title = 'Manage shared presenters';
        
        if (inputGroup) {
            inputGroup.classList.remove('has-shared');
        }
    }
}

// Helper function to update cell display
function updateCellDisplay(cell, sharedPresenters) {
    // For cells with the new button structure
    const inputGroup = cell.querySelector('.presenter-input-group');
    if (inputGroup) {
        const shareBtn = inputGroup.querySelector('.btn-share-presenter');
        if (shareBtn) {
            if (sharedPresenters.length > 0) {
                shareBtn.innerHTML = `<span class="share-count">+${sharedPresenters.length}</span>`;
                inputGroup.classList.add('has-shared');
                const names = sharedPresenters.join(', ');
                shareBtn.title = `Shared with: ${names}`;
            } else {
                shareBtn.innerHTML = '<span class="share-icon">👥</span>';
                shareBtn.title = 'Manage shared presenters';
                inputGroup.classList.remove('has-shared');
            }
        }
        return;
    }
    
    // Fallback for old structure (backward compatibility)
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
    
    // Reset variables
    currentAssignmentId = null;
    currentSharedPresenters = [];
    
    // Clear the input
    const input = document.getElementById('newPresenterInput');
    if (input) {
        input.value = '';
    }
    
    // Reset save button if needed
    const saveBtn = document.querySelector('.save-btn');
    if (saveBtn) {
        saveBtn.textContent = 'Save Changes';
        saveBtn.disabled = false;
    }
}

// ============ INLINE SHARED PRESENTER FUNCTIONS ============

/**
 * Toggle the expandable shared presenters section
 */
function togglePresenters(assignmentId) {
    const row = document.querySelector(`[data-assignment-id="${assignmentId}"]`);
    if (!row) return;
    
    const container = row.querySelector('.shared-presenters-container');
    const expandBtn = row.querySelector('.btn-expand-presenters, .btn-add-presenter');
    
    if (!container) return;
    
    const isVisible = container.style.display !== 'none';
    
    if (isVisible) {
        // Collapse
        container.style.display = 'none';
        if (expandBtn && expandBtn.querySelector('.expand-icon')) {
            expandBtn.querySelector('.expand-icon').textContent = '▶';
        }
    } else {
        // Expand
        container.style.display = 'block';
        if (expandBtn && expandBtn.querySelector('.expand-icon')) {
            expandBtn.querySelector('.expand-icon').textContent = '▼';
        }
        
        // Focus on add input
        const addInput = container.querySelector('.add-presenter-input');
        if (addInput) {
            setTimeout(() => addInput.focus(), 100);
        }
    }
}

/**
 * Add a shared presenter inline (no modal)
 */
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
            
            // Clear input
            input.value = '';
            
            // Reload the page to update the UI
            // TODO: Could be optimized to update inline without reload
            setTimeout(() => location.reload(), 500);
        } else {
            showNotification(data.error || 'Failed to add presenter', 'error');
        }
    } catch (error) {
        console.error('Error adding shared presenter:', error);
        showNotification('Error adding presenter', 'error');
    }
}

/**
 * Remove a shared presenter inline
 */
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
            
            // Reload the page to update the UI
            setTimeout(() => location.reload(), 500);
        } else {
            showNotification(data.error || 'Failed to remove presenter', 'error');
        }
    } catch (error) {
        console.error('Error removing shared presenter:', error);
        showNotification('Error removing presenter', 'error');
    }
}

/**
 * Handle D-MIC checkbox change with automatic presenter rotation
 * IMPROVED VERSION - Prevents checkbox race conditions
 */
async function handleDmicChange(assignmentId, isChecked) {
    // Get the checkbox element FIRST
    const checkbox = document.querySelector(
        `[data-assignment-id="${assignmentId}"] .dmic-checkbox`
    );
    
    if (!checkbox) {
        console.error('Checkbox not found for assignment:', assignmentId);
        return;
    }
    
    // Store the ACTUAL current state (before browser toggles it)
    const currentState = checkbox.checked;
    
    // Since the browser already toggled it, we need to toggle it back
    // and then let our code control it after the server responds
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
            
            // NOW update the checkbox to the server's state
            checkbox.checked = data.is_d_mic;
            
            // NEW: Update the MIC'D checkbox too (mutually exclusive)
            const micdCheckbox = document.querySelector(
                `[data-assignment-id="${assignmentId}"] .mic-checkbox:not(.dmic-checkbox)`
            );
            if (micdCheckbox && data.is_micd !== undefined) {
                micdCheckbox.checked = data.is_micd;
            }
            
            // If presenter rotated, reload to show new current presenter
            if (data.current_presenter !== data.previous_presenter) {
                setTimeout(() => location.reload(), 800);
            }
        } else {
            showNotification(data.error || 'Failed to update D-MIC status', 'error');
            
            // Revert checkbox to original state on error
            checkbox.checked = currentState;
        }
    } catch (error) {
        console.error('Error updating D-MIC:', error);
        showNotification('Error updating D-MIC status', 'error');
        
        // Revert checkbox to original state on error
        checkbox.checked = currentState;
    }
}

            
        

/**
 * Reset presenter rotation back to primary presenter
 */
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
            
            // Reload to update UI
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
    // Update day header stats - implementation depends on your UI structure
    console.log('Day stats updated:', stats);
}

function updatePresenterDisplay(assignmentId, displayText, presenterCount) {
    const row = document.querySelector(`[data-assignment-id="${assignmentId}"]`);
    if (!row) return;
    
    const presenterCell = row.querySelector('.col-presenter');
    if (!presenterCell) return;
    
    // For new button structure
    const shareBtn = presenterCell.querySelector('.btn-share-presenter');
    if (shareBtn && presenterCount > 1) {
        shareBtn.innerHTML = `<span class="share-count">+${presenterCount - 1}</span>`;
        const inputGroup = presenterCell.querySelector('.presenter-input-group');
        if (inputGroup) {
            inputGroup.classList.add('has-shared');
        }
        return;
    }
    
    // Fallback for old structure
    const existingIndicator = presenterCell.querySelector('.shared-indicator');
    if (existingIndicator) {
        existingIndicator.remove();
    }
    
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
    // Remove any existing notifications
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
    
    // Set color based on type
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
        setTimeout(() => {
            notification.remove();
        }, 300);
    }, 3000);
}

// ============ SESSION MANAGEMENT FUNCTIONS ============


// Add new day
function addNewDay() {
    const dateStr = prompt('Enter date for new day (MM/DD/YYYY):');
    if (!dateStr) return;
    
    // Convert MM/DD/YYYY to YYYY-MM-DD for the backend
    const parts = dateStr.split('/');
    if (parts.length !== 3) {
        alert('Invalid date format. Please use MM/DD/YYYY');
        return;
    }
    
    const month = parts[0].padStart(2, '0');
    const day = parts[1].padStart(2, '0');
    const year = parts[2];
    
    const isoDate = `${year}-${month}-${day}`;
    
    const name = prompt('Enter optional name for this day:');
    
    // Redirect to admin to add new day
    window.location.href = `/admin/planner/showday/add/?date=${isoDate}&name=${encodeURIComponent(name || '')}`;
}

// Add new session
function addSession(dayId, columnPosition = 0) {
    const name = prompt('Enter session name:');
    if (!name) return;
    
    // Redirect to admin to add new session
    window.location.href = `/admin/planner/micsession/add/?day=${dayId}&name=${encodeURIComponent(name)}&column_position=${columnPosition}`;
}

// Edit session
function editSession(sessionId) {
    window.location.href = `/admin/planner/micsession/${sessionId}/change/`;
}

// Duplicate session
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

// ============ INITIALIZATION ============

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Initialize any existing shared presenter indicators
    document.querySelectorAll('.btn-share-presenter').forEach(btn => {
        const countSpan = btn.querySelector('.share-count');
        if (countSpan) {
            const row = btn.closest('[data-assignment-id]');
            if (row) {
                const inputGroup = row.querySelector('.presenter-input-group');
                if (inputGroup) {
                    inputGroup.classList.add('has-shared');
                }
            }
        }
    });

   
    
    // Add event listener for Enter key in the shared presenter input field
    const input = document.getElementById('newPresenterInput');
    if (input) {
        input.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                addSharedPresenter();
            }
        });
    }
    
    // Close modal when clicking outside of it
    const modal = document.getElementById('sharedPresenterModal');
    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                closeSharedPresenterModal();
            }
        });
    }
    
    // Add double-click handler to presenter cells (backward compatibility)
    document.addEventListener('dblclick', function(e) {
        const cell = e.target.closest('.editable[data-field="presenter"], .col-presenter');
        if (cell) {
            // Don't trigger if clicking on button or input
            if (e.target.closest('.btn-share-presenter') || e.target.tagName === 'INPUT') {
                return;
            }
            
            e.preventDefault();
            // Try to get assignment ID from different possible attributes
            let assignmentId = cell.dataset.id || cell.dataset.assignmentId;
            
            // If not found on cell, check parent row
            if (!assignmentId) {
                const row = cell.closest('[data-assignment-id]');
                if (row) {
                    assignmentId = row.dataset.assignmentId;
                }
            }
            
            if (assignmentId) {
                showSharedPresenterDialog(assignmentId);
            }
        }
    });
    
    // Add keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        // Ctrl+E to expand all
        if (e.ctrlKey && e.key === 'e') {
            e.preventDefault();
            expandAllDays();
        }
        
        // Ctrl+L to collapse all
        if (e.ctrlKey && e.key === 'l') {
            e.preventDefault();
            collapseAllDays();
        }
        
        // Esc to close modal
        if (e.key === 'Escape') {
            const modal = document.getElementById('sharedPresenterModal');
            if (modal && modal.style.display !== 'none') {
                closeSharedPresenterModal();
            }
        }
    });
    
    // Auto-save notification for regular inputs (not shared presenters)
    let saveTimeout;
    document.querySelectorAll('.presenter-input:not(.modal input), .mic-type-select').forEach(input => {
        input.addEventListener('input', function() {
            clearTimeout(saveTimeout);
            saveTimeout = setTimeout(() => {
                showNotification('Changes saved', 'success');
            }, 1000);
        });
    });
    
    // Add CSS for animations if not already present
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
    
    console.log('Mic Tracker initialized with inline shared presenter support');
});


/**
 * Load presenters list for autocomplete
 */
async function loadPresentersList() {
    try {
        const response = await fetch('/audiopatch/api/presenters/list/');
        const data = await response.json();
        
        if (data.presenters) {
            const datalist = document.getElementById('presenters-datalist');
            datalist.innerHTML = ''; // Clear existing options
            
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

// Load presenters when page loads
document.addEventListener('DOMContentLoaded', loadPresentersList);
// ── Mic Groups ─────────────────────────────────────────────────
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
