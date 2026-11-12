/**
 * Anti-Matrix Admin & Application Portal JavaScript
 */
document.addEventListener('DOMContentLoaded', () => {
  // Auto-dismiss alert notifications after 6 seconds
  const flashAlerts = document.querySelectorAll('.flash-alert');
  flashAlerts.forEach(alert => {
    setTimeout(() => {
      alert.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
      alert.style.opacity = '0';
      alert.style.transform = 'translateY(-10px)';
      setTimeout(() => {
        const container = alert.closest('.flash-messages-container');
        alert.remove();
        if (container && container.querySelectorAll('.flash-alert').length === 0) {
          container.remove();
        }
      }, 400);
    }, 6000);
  });

  // Client-side quick filter for tables
  const quickSearchInput = document.getElementById('admin-quick-search');
  if (quickSearchInput) {
    quickSearchInput.addEventListener('input', (e) => {
      const term = e.target.value.toLowerCase().trim();
      const rows = document.querySelectorAll('.admin-table tbody tr');
      rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(term) ? '' : 'none';
      });
    });
  }

  // --- Delete All Job Postings Modal Controller ---
  const openDeleteAllBtn = document.getElementById('open-delete-all-modal-btn');
  const deleteAllModal = document.getElementById('delete-all-modal');
  const cancelDeleteAllBtn = document.getElementById('cancel-delete-all-btn');
  const modalBackdrop = document.getElementById('modal-backdrop');
  const deleteConfirmInput = document.getElementById('delete-confirm-input');
  const confirmDeleteAllBtn = document.getElementById('confirm-delete-all-btn');
  const deleteAllForm = document.getElementById('delete-all-jobs-form');
  const confirmBtnText = document.getElementById('confirm-btn-text');

  function openModal() {
    if (deleteAllModal) {
      deleteAllModal.style.display = 'flex';
      deleteAllModal.setAttribute('aria-hidden', 'false');
      if (deleteConfirmInput) {
        deleteConfirmInput.value = '';
        if (confirmDeleteAllBtn) confirmDeleteAllBtn.disabled = true;
        setTimeout(() => deleteConfirmInput.focus(), 50);
      }
    }
  }

  function closeModal() {
    if (deleteAllModal) {
      deleteAllModal.style.display = 'none';
      deleteAllModal.setAttribute('aria-hidden', 'true');
      if (deleteConfirmInput) deleteConfirmInput.value = '';
      if (confirmDeleteAllBtn) confirmDeleteAllBtn.disabled = true;
    }
  }

  if (openDeleteAllBtn) {
    openDeleteAllBtn.addEventListener('click', openModal);
  }

  if (cancelDeleteAllBtn) {
    cancelDeleteAllBtn.addEventListener('click', closeModal);
  }

  if (modalBackdrop) {
    modalBackdrop.addEventListener('click', closeModal);
  }

  // Close on Escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && deleteAllModal && deleteAllModal.style.display !== 'none') {
      closeModal();
    }
  });

  // Strict case-sensitive validation for DELETE confirmation
  if (deleteConfirmInput && confirmDeleteAllBtn) {
    deleteConfirmInput.addEventListener('input', () => {
      const val = deleteConfirmInput.value.trim();
      if (val === 'DELETE') {
        confirmDeleteAllBtn.disabled = false;
      } else {
        confirmDeleteAllBtn.disabled = true;
      }
    });
  }

  // Double-submission prevention and loading state
  if (deleteAllForm && confirmDeleteAllBtn) {
    deleteAllForm.addEventListener('submit', (e) => {
      if (deleteConfirmInput && deleteConfirmInput.value.trim() !== 'DELETE') {
        e.preventDefault();
        return false;
      }
      confirmDeleteAllBtn.disabled = true;
      if (confirmBtnText) {
        confirmBtnText.textContent = 'Deleting All Jobs...';
      }
      confirmDeleteAllBtn.style.opacity = '0.7';
      confirmDeleteAllBtn.style.cursor = 'wait';
    });
  }
});
