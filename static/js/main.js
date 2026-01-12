// ======================
// Global Variables
// ======================
let selectedFiles = [];
let currentSessionId = null;
let dataTable = null;
let currentInvoiceIndex = 0;
let totalInvoices = 0;

// ======================
// Document Ready
// ======================
$(document).ready(function () {
    initializeEventListeners();
});

// ======================
// Initialize Event Listeners
// ======================
function initializeEventListeners() {
    // File input change
    $('#fileInput').on('change', handleFileSelect);

    // Drag and drop
    const uploadZone = $('#uploadZone')[0];
    uploadZone.addEventListener('dragover', handleDragOver);
    uploadZone.addEventListener('dragleave', handleDragLeave);
    uploadZone.addEventListener('drop', handleDrop);

    // Click to browse files (prevent recursion)
    $('#uploadZone').on('click', (e) => {
        if (e.target.id !== 'fileInput' && e.target.tagName !== 'BUTTON') {
            $('#fileInput').trigger('click');
        }
    });

    // Buttons
    $('#processBtn').on('click', processFiles);
    $('#exportBtn').on('click', exportToExcel);
    $('#processMoreBtn').on('click', resetApp);
    $('#prevInvoiceBtn').on('click', showPreviousInvoice);
    $('#nextInvoiceBtn').on('click', showNextInvoice);

    // Close modal on ESC
    $(document).on('keydown', (e) => {
        if (e.key === 'Escape' && !$('#invoiceModal').hasClass('hidden')) {
            closeModal();
        }
    });

    // Close modal on outside click
    $('#invoiceModal').on('click', (e) => {
        if (e.target.id === 'invoiceModal') closeModal();
    });
}

// ======================
// File Handling
// ======================
function handleFileSelect(e) {
    handleFiles(e.target.files);
}

function handleFiles(files) {
    const allowedExtensions = ['pdf', 'png', 'jpg', 'jpeg', 'webp'];

    for (let file of files) {
        const extension = file.name.split('.').pop().toLowerCase();
        if (!allowedExtensions.includes(extension)) {
            showAlert('danger', `File "${file.name}" has an unsupported format.`);
            continue;
        }

        // Avoid duplicates
        if (selectedFiles.find(f => f.name === file.name && f.size === file.size)) continue;

        selectedFiles.push(file);
    }

    updateFileList();
}

function updateFileList() {
    const fileList = $('#fileList');
    fileList.empty();

    if (selectedFiles.length === 0) {
        $('#processBtn').hide();
        return;
    }

    $('#processBtn').show();

    selectedFiles.forEach((file, index) => {
        const fileIcon = getFileIcon(file.name);
        const fileSize = formatFileSize(file.size);

        const fileItem = $(`
            <div class="file-item">
                <div>
                    <i class="${fileIcon}"></i>
                    <strong>${file.name}</strong>
                    <span class="text-muted ms-2">(${fileSize})</span>
                </div>
                <i class="fas fa-times remove-file" data-index="${index}"></i>
            </div>
        `);

        fileItem.find('.remove-file').on('click', function () {
            removeFile($(this).data('index'));
        });

        fileList.append(fileItem);
    });
}

function removeFile(index) {
    selectedFiles.splice(index, 1);
    updateFileList();
}

function getFileIcon(filename) {
    const extension = filename.split('.').pop().toLowerCase();
    const iconMap = {
        pdf: 'fas fa-file-pdf text-danger',
        png: 'fas fa-image text-primary',
        jpg: 'fas fa-image text-success',
        jpeg: 'fas fa-image text-success',
        webp: 'fas fa-image text-warning',
    };
    return iconMap[extension] || 'fas fa-file';
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
}

// ======================
// Drag & Drop Handlers
// ======================
function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    $('#uploadZone').addClass('drag-over');
}

function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    $('#uploadZone').removeClass('drag-over');
}

function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    $('#uploadZone').removeClass('drag-over');
    const files = e.dataTransfer.files;
    handleFiles(files);
}

// ======================
// Process & Upload Files
// ======================
function processFiles() {
    if (selectedFiles.length === 0) {
        showAlert('warning', 'Please select files to process.');
        return;
    }

    $('#progressSection').show();
    $('#processBtn').prop('disabled', true);
    updateProgress(0, 0, 0, 'Uploading files...');

    const formData = new FormData();
    selectedFiles.forEach((file) => formData.append('files[]', file));

    $.ajax({
        url: '/upload',
        type: 'POST',
        data: formData,
        processData: false,
        contentType: false,
        xhr: function () {
            const xhr = new window.XMLHttpRequest();
            xhr.upload.addEventListener(
                'progress',
                function (e) {
                    if (e.lengthComputable) {
                        const percentComplete = Math.round((e.loaded / e.total) * 20);
                        updateProgress(percentComplete, 0, 0, 'Uploading files...');
                    }
                },
                false
            );
            return xhr;
        },
        success: function (response) {
            if (response?.success && response.session_id) {
                currentSessionId = response.session_id;
                totalInvoices = response.total_invoices || 0;
                updateProgress(100, totalInvoices, totalInvoices, 'Processing complete!');
                setTimeout(() => loadInvoices(currentSessionId), 800);
            } else {
                const msg = response?.error || 'Processing failed.';
                showAlert('danger', msg);
                $('#progressSection').hide();
                $('#processBtn').prop('disabled', false);
            }
        },
        error: function (xhr) {
            const errorMsg = xhr.responseJSON?.error || 'Upload failed. Please try again.';
            showAlert(errorMsg.includes('limit') ? 'warning' : 'danger', errorMsg);
            $('#progressSection').hide();
            $('#processBtn').prop('disabled', false);
        },
    });
}

// ======================
// Load & Display Invoices
// ======================
function loadInvoices(sessionId) {
    if (!sessionId) {
        showAlert('danger', 'Session ID not found. Please try again.');
        return;
    }

    $.ajax({
        url: `/get_invoices/${sessionId}`,
        type: 'GET',
        success: function (response) {
            if (response?.success) {
                displayInvoices(response.invoices || []);
                $('#progressSection').hide();
                $('#resultsSection').show().addClass('fade-in');
            } else {
                const msg = response?.error || 'Failed to load invoices.';
                showAlert('danger', msg);
            }
        },
        error: function (xhr) {
            let message = 'Failed to load invoices.';
            try {
                const json = JSON.parse(xhr.responseText);
                message = json.error || message;
            } catch (e) {
                message = xhr.statusText || message;
            }
            showAlert('danger', message);
        },
    });
}

// ======================
// Display Invoices in Table
// ======================
function displayInvoices(invoices) {
    $('#invoiceCount').text(invoices.length);

    if (dataTable) dataTable.destroy();

    const tableBody = $('#invoicesTable tbody');
    tableBody.empty();

    invoices.forEach((invoice, index) => {
        let row = '<tr>';
        row += `<td>${invoice.Source_File || ''}</td>`;
        row += `<td>${invoice.Page_Number || ''}</td>`;

        const schemaFields = [
            'Invoice_Date',
            'Invoice_No',
            'Supplier_Name',
            'Supplier_NTN',
            'Supplier_GST_No',
            'Supplier_Registration_No',
            'Buyer_Name',
            'Buyer_NTN',
            'Buyer_GST_No',
            'Buyer_Registration_No',
            'Exclusive_Value',
            'GST_Sales_Tax',
            'Inclusive_Value',
            'Advance_Tax',
            'Net_Amount',
        ];

        schemaFields.forEach((field) => {
            const value = invoice[field] || '-';
            row += `<td>${value}</td>`;
        });

        row += `<td>
            <button class="px-4 py-2 bg-brand-red text-white rounded-lg hover:bg-promo-red text-sm font-semibold transition shadow-md" onclick="viewInvoice(${index})">
                <i class="fas fa-eye mr-1"></i>View
            </button>
        </td>`;
        row += '</tr>';

        tableBody.append(row);
    });

    dataTable = $('#invoicesTable').DataTable({
        pageLength: 10,
        lengthMenu: [
            [10, 25, 50, -1],
            [10, 25, 50, 'All'],
        ],
        order: [[0, 'asc']],
        language: {
            search: '_INPUT_',
            searchPlaceholder: 'Search invoices...',
        },
        columnDefs: [{ targets: '_all', className: 'text-nowrap' }],
    });
}

// ======================
// View Single Invoice Modal
// ======================
function viewInvoice(index) {
    if (!currentSessionId) return;
    currentInvoiceIndex = index;

    $.ajax({
        url: `/get_invoice_image/${currentSessionId}/${index}`,
        type: 'GET',
        success: function (response) {
            if (response?.success) showInvoiceModal(response, index);
            else showAlert('danger', response?.error || 'Failed to load invoice.');
        },
        error: function () {
            showAlert('danger', 'Failed to load invoice details.');
        },
    });
}

function showInvoiceModal(invoiceData, index) {
    $('#modalRowNumber').text(`Row ${index}`);
    $('#modalInvoiceImage').attr('src', `data:image/png;base64,${invoiceData.image}`);

    const dataContainer = $('#modalInvoiceData');
    dataContainer.empty();

    const data = invoiceData.data || {};
    for (let key in data) {
        if (key !== '_image_base64' && key !== 'row_id') {
            const value = data[key] || '-';
            const label = key.replace(/_/g, ' ');
            const fieldHtml = `
                <div class="bg-white rounded-lg p-3 border-l-4 border-brand-red shadow-sm">
                    <div class="text-xs font-semibold text-muted-text uppercase mb-1">${label}</div>
                    <div class="text-sm font-semibold text-dark-text">${value}</div>
                </div>
            `;
            dataContainer.append(fieldHtml);
        }
    }

    $('#prevInvoiceBtn').prop('disabled', index === 0);
    $('#nextInvoiceBtn').prop('disabled', index === totalInvoices - 1);
    $('#invoiceCounter').text(`Invoice ${index + 1} of ${totalInvoices}`);

    $('#invoiceModal').removeClass('hidden');
    $('body').addClass('overflow-hidden');
}

function closeModal() {
    $('#invoiceModal').addClass('hidden');
    $('body').removeClass('overflow-hidden');
}

// ======================
// Navigation
// ======================
function showPreviousInvoice() {
    if (currentInvoiceIndex > 0) viewInvoice(currentInvoiceIndex - 1);
}

function showNextInvoice() {
    if (currentInvoiceIndex < totalInvoices - 1) viewInvoice(currentInvoiceIndex + 1);
}

// ======================
// Export & Reset
// ======================
function exportToExcel() {
    if (!currentSessionId) {
        showAlert('danger', 'No session to export.');
        return;
    }
    window.location.href = `/export/${currentSessionId}`;
}

function resetApp() {
    selectedFiles = [];
    currentSessionId = null;
    currentInvoiceIndex = 0;
    totalInvoices = 0;

    $('#fileList').empty();
    $('#fileInput').val('');
    $('#processBtn').hide().prop('disabled', false);
    $('#resultsSection').hide();
    $('#progressSection').hide();

    if (dataTable) {
        dataTable.destroy();
        dataTable = null;
    }

    $('html, body').animate({ scrollTop: 0 }, 500);
}

// ======================
// Progress & Alerts
// ======================
function updateProgress(percentage, processed, total, message) {
    $('#progressPercentage').text(percentage + '%');
    $('#progressBar').css('width', percentage + '%');
    $('#progressBarText').text(percentage > 10 ? percentage + '%' : '');
    $('#progressText').text(message);
    $('#progressCount').text(total > 0 ? `${processed} / ${total} invoices` : '');
}

function showAlert(type, message) {
    const alertClass =
        type === 'danger'
            ? 'bg-red-100 text-red-800 border-red-300'
            : type === 'warning'
            ? 'bg-yellow-100 text-yellow-800 border-yellow-300'
            : 'bg-green-100 text-green-800 border-green-300';

    const iconClass =
        type === 'danger'
            ? 'exclamation-circle'
            : type === 'warning'
            ? 'exclamation-triangle'
            : 'check-circle';

    const alert = $(`
        <div class="fixed top-4 right-4 ${alertClass} border-2 px-6 py-4 rounded-lg shadow-lg z-50 max-w-md animate-fade-in">
            <div class="flex items-center gap-3">
                <i class="fas fa-${iconClass} text-xl"></i>
                <p class="font-semibold">${message}</p>
                <button onclick="this.parentElement.parentElement.remove()" class="ml-4 text-xl font-bold opacity-50 hover:opacity-100">×</button>
            </div>
        </div>
    `);

    $('body').append(alert);
    setTimeout(() => alert.fadeOut(300, function () { $(this).remove(); }), 5000);
}
