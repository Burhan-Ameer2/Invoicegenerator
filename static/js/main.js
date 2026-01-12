// Global variables
let selectedFiles = [];
let currentSessionId = null;
let dataTable = null;
let currentInvoiceIndex = 0;
let totalInvoices = 0;

$(document).ready(function() {
    // Initialize event listeners
    initializeEventListeners();
});

function initializeEventListeners() {
    // File input change
    $('#fileInput').on('change', handleFileSelect);

    // Upload zone drag and drop
    const uploadZone = $('#uploadZone')[0];

    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.stopPropagation();
        $('#uploadZone').addClass('drag-over');
    });

    uploadZone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        e.stopPropagation();
        $('#uploadZone').removeClass('drag-over');
    });

    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
        $('#uploadZone').removeClass('drag-over');

        const files = e.dataTransfer.files;
        handleFiles(files);
    });

    // Click upload zone to browse
    $('#uploadZone').on('click', function(e) {
        if (e.target.tagName !== 'BUTTON') {
            $('#fileInput').click();
        }
    });

    // Process button
    $('#processBtn').on('click', processFiles);

    // Export button
    $('#exportBtn').on('click', exportToExcel);

    // Process more button
    $('#processMoreBtn').on('click', resetApp);

    // Modal navigation
    $('#prevInvoiceBtn').on('click', showPreviousInvoice);
    $('#nextInvoiceBtn').on('click', showNextInvoice);
}

function handleFileSelect(e) {
    const files = e.target.files;
    handleFiles(files);
}

function handleFiles(files) {
    const allowedExtensions = ['pdf', 'png', 'jpg', 'jpeg', 'webp'];

    for (let file of files) {
        const extension = file.name.split('.').pop().toLowerCase();

        if (!allowedExtensions.includes(extension)) {
            showAlert('danger', `File "${file.name}" has an unsupported format.`);
            continue;
        }

        // Check if file already added
        if (selectedFiles.find(f => f.name === file.name && f.size === file.size)) {
            continue;
        }

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

        fileItem.find('.remove-file').on('click', function() {
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
        'pdf': 'fas fa-file-pdf text-danger',
        'png': 'fas fa-image text-primary',
        'jpg': 'fas fa-image text-success',
        'jpeg': 'fas fa-image text-success',
        'webp': 'fas fa-image text-warning'
    };
    return iconMap[extension] || 'fas fa-file';
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

function processFiles() {
    if (selectedFiles.length === 0) {
        showAlert('warning', 'Please select files to process.');
        return;
    }

    // Show progress section
    $('#progressSection').show();
    $('#processBtn').prop('disabled', true);

    // Reset progress
    updateProgress(0, 0, 0, 'Uploading files...');

    // Prepare form data
    const formData = new FormData();
    selectedFiles.forEach(file => {
        formData.append('files[]', file);
    });

    // Upload and process
    $.ajax({
        url: '/upload',
        type: 'POST',
        data: formData,
        processData: false,
        contentType: false,
        xhr: function() {
            const xhr = new window.XMLHttpRequest();
            xhr.upload.addEventListener('progress', function(e) {
                if (e.lengthComputable) {
                    const percentComplete = Math.round((e.loaded / e.total) * 20);
                    updateProgress(percentComplete, 0, 0, 'Uploading files...');
                }
            }, false);
            return xhr;
        },
        success: function(response) {
            if (response.success) {
                currentSessionId = response.session_id;
                totalInvoices = response.total_invoices;

                updateProgress(100, totalInvoices, totalInvoices, 'Processing complete!');

                setTimeout(() => {
                    loadInvoices(response.session_id);
                }, 800);
            } else {
                showAlert('danger', 'Processing failed: ' + response.error);
                $('#progressSection').hide();
                $('#processBtn').prop('disabled', false);
            }
        },
        error: function(xhr, status, error) {
            console.error('Upload error:', error);
            showAlert('danger', 'Upload failed. Please try again.');
            $('#progressSection').hide();
            $('#processBtn').prop('disabled', false);
        }
    });
}

function loadInvoices(sessionId) {
    $.ajax({
        url: `/get_invoices/${sessionId}`,
        type: 'GET',
        success: function(response) {
            if (response.success) {
                displayInvoices(response.invoices);
                $('#progressSection').hide();
                $('#resultsSection').show().addClass('fade-in');
            }
        },
        error: function(xhr, status, error) {
            console.error('Load invoices error:', error);
            showAlert('danger', 'Failed to load invoices.');
        }
    });
}

function displayInvoices(invoices) {
    $('#invoiceCount').text(invoices.length);

    // Destroy existing DataTable if any
    if (dataTable) {
        dataTable.destroy();
    }

    // Prepare table data
    const tableBody = $('#invoicesTable tbody');
    tableBody.empty();

    invoices.forEach((invoice, index) => {
        let row = '<tr>';
        row += `<td>${invoice.Source_File || ''}</td>`;
        row += `<td>${invoice.Page_Number || ''}</td>`;

        // Add all schema fields
        const schemaFields = [
            'Invoice_Date', 'Invoice_No', 'Supplier_Name', 'Supplier_NTN',
            'Supplier_GST_No', 'Supplier_Registration_No', 'Buyer_Name',
            'Buyer_NTN', 'Buyer_GST_No', 'Buyer_Registration_No',
            'Exclusive_Value', 'GST_Sales_Tax', 'Inclusive_Value',
            'Advance_Tax', 'Net_Amount'
        ];

        schemaFields.forEach(field => {
            const value = invoice[field] || '-';
            row += `<td>${value}</td>`;
        });

        row += `<td><button class="px-4 py-2 bg-brand-red text-white rounded-lg hover:bg-promo-red text-sm font-semibold transition shadow-md" onclick="viewInvoice(${index})"><i class="fas fa-eye mr-1"></i>View</button></td>`;
        row += '</tr>';

        tableBody.append(row);
    });

    // Initialize DataTable
    dataTable = $('#invoicesTable').DataTable({
        pageLength: 10,
        lengthMenu: [[10, 25, 50, -1], [10, 25, 50, "All"]],
        order: [[0, 'asc']],
        language: {
            search: "_INPUT_",
            searchPlaceholder: "Search invoices..."
        },
        columnDefs: [
            { targets: '_all', className: 'text-nowrap' }
        ]
    });
}

function viewInvoice(index) {
    if (!currentSessionId) return;

    currentInvoiceIndex = index;

    // Fetch invoice data
    $.ajax({
        url: `/get_invoice_image/${currentSessionId}/${index}`,
        type: 'GET',
        success: function(response) {
            if (response.success) {
                showInvoiceModal(response, index);
            }
        },
        error: function(xhr, status, error) {
            console.error('Load invoice error:', error);
            showAlert('danger', 'Failed to load invoice details.');
        }
    });
}

function showInvoiceModal(invoiceData, index) {
    // Set modal title
    $('#modalRowNumber').text(`Row ${index}`);

    // Set image
    $('#modalInvoiceImage').attr('src', `data:image/png;base64,${invoiceData.image}`);

    // Set extracted data
    const dataContainer = $('#modalInvoiceData');
    dataContainer.empty();

    const data = invoiceData.data;
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

    // Update navigation buttons
    const prevBtn = document.getElementById('prevInvoiceBtn');
    const nextBtn = document.getElementById('nextInvoiceBtn');

    if (index === 0) {
        prevBtn.setAttribute('disabled', 'true');
    } else {
        prevBtn.removeAttribute('disabled');
    }

    if (index === totalInvoices - 1) {
        nextBtn.setAttribute('disabled', 'true');
    } else {
        nextBtn.removeAttribute('disabled');
    }

    // Update counter
    $('#invoiceCounter').text(`Invoice ${index + 1} of ${totalInvoices}`);

    // Show modal
    $('#invoiceModal').removeClass('hidden');
    $('body').addClass('overflow-hidden');
}

function closeModal() {
    $('#invoiceModal').addClass('hidden');
    $('body').removeClass('overflow-hidden');
}

// Close modal on ESC key
$(document).on('keydown', function(e) {
    if (e.key === 'Escape' && !$('#invoiceModal').hasClass('hidden')) {
        closeModal();
    }
});

// Close modal when clicking outside
$('#invoiceModal').on('click', function(e) {
    if (e.target.id === 'invoiceModal') {
        closeModal();
    }
});

function showPreviousInvoice() {
    if (currentInvoiceIndex > 0) {
        viewInvoice(currentInvoiceIndex - 1);
    }
}

function showNextInvoice() {
    if (currentInvoiceIndex < totalInvoices - 1) {
        viewInvoice(currentInvoiceIndex + 1);
    }
}

function exportToExcel() {
    if (!currentSessionId) return;

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

function updateProgress(percentage, processed, total, message) {
    // Update percentage display
    $('#progressPercentage').text(percentage + '%');

    // Update progress bar
    $('#progressBar').css('width', percentage + '%');

    // Update progress bar text (only show if > 10%)
    if (percentage > 10) {
        $('#progressBarText').text(percentage + '%');
    } else {
        $('#progressBarText').text('');
    }

    // Update status message
    $('#progressText').text(message);

    // Update count if provided
    if (total > 0) {
        $('#progressCount').text(`${processed} / ${total} invoices`);
    } else {
        $('#progressCount').text('');
    }
}

function showAlert(type, message) {
    const alertClass = type === 'danger' ? 'bg-red-100 text-red-800 border-red-300' :
                       type === 'warning' ? 'bg-yellow-100 text-yellow-800 border-yellow-300' :
                       'bg-green-100 text-green-800 border-green-300';

    const alert = $(`
        <div class="fixed top-4 right-4 ${alertClass} border-2 px-6 py-4 rounded-lg shadow-lg z-50 max-w-md animate-fade-in">
            <div class="flex items-center gap-3">
                <i class="fas fa-${type === 'danger' ? 'exclamation-circle' : type === 'warning' ? 'exclamation-triangle' : 'check-circle'} text-xl"></i>
                <p class="font-semibold">${message}</p>
                <button onclick="this.parentElement.parentElement.remove()" class="ml-4 text-xl font-bold opacity-50 hover:opacity-100">×</button>
            </div>
        </div>
    `);

    $('body').append(alert);

    setTimeout(() => {
        alert.fadeOut(300, function() {
            $(this).remove();
        });
    }, 5000);
}
