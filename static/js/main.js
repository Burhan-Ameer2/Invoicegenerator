// ======================
// Global Variables
// ======================
let selectedFiles = [];
let currentSessionId = null;
let dataTable = null;
let currentInvoiceIndex = 0;
let totalInvoices = 0;
// Initialize with default schema from HTML or fallback
// Initialize with schema from server or default fallback
let currentSchema = []; // Will store objects {id, name, description}

// fetch actual fields from database on load
$(document).ready(function () {
    fetchFields();
    fetchUsage();
});

function fetchUsage() {
    $.get('/api/usage', function(data) {
        updateUsageUI(data);
    });
}

function updateUsageUI(data) {
    if (!data) return;

    // Update call counter
    $("#usageTotalCalls").text(data.total_calls.toLocaleString());
    
    // Update invoice limit progress
    const maxInvoices = data.max_trial_invoices;
    const currentInvoices = data.total_calls;
    const invoicesRemaining = data.invoices_remaining;
    
    // Calculate percentage (capped at 100%)
    const invoiceProgress = Math.min(100, (currentInvoices / maxInvoices) * 100);
    
    $("#invoiceLimitText").text(`${invoicesRemaining} Invoice${invoicesRemaining !== 1 ? 's' : ''} Left`);
    $("#invoiceProgressBar").css("width", `${invoiceProgress}%`);
    
    // Show/hide limit warning color
    if (invoiceProgress >= 90) {
        $("#invoiceProgressBar").removeClass("bg-brand-red").addClass("bg-red-600");
    }

    // Start Trial Countdown
    if (data.trial_expires_at) {
        startTrialCountdown(new Date(data.trial_expires_at));
    } else {
        // Fallback for older data without expiration
        const remaining = data.trial_days_remaining;
        $("#trialDaysText").text(`${remaining} Day${remaining !== 1 ? 's' : ''} Left`);
    }

    // Update trial progress bar
    const remainingDays = data.trial_days_remaining;
    const progress = Math.min(100, ( (7 - remainingDays) / 7 ) * 100);
    $("#trialProgressBar").css("width", `${progress}%`);

    // Enforce trial expiration or limit reached
    if (data.is_trial_expired || data.is_limit_reached) {
        $("#trialExpiredOverlay").removeClass("hidden");
        
        // Update overlay text based on reason
        if (data.is_limit_reached) {
             $("#trialExpiredTitle").text("Invoice Limit Reached");
             $("#trialExpiredMessage").html(`You have processed <b>${currentInvoices}</b> invoices, reaching the trial limit. <br>To continue using the <span class="text-brand-red font-bold">Invoice Data Extractor Pro</span>, please contact support.`);
        }
        
        // Disable all buttons and inputs to make it unusable
        $("button, input, select, textarea").prop("disabled", true);
        // Special case for our custom browse button
        $("#uploadZone").addClass("pointer-events-none opacity-50");
    }
}

function fetchFields() {
    $.get('/api/fields', function(data) {
        currentSchema = data;
        updateUIWithNewSchema();
    });
}

function updateUIWithNewSchema() {
    // Update sidebar summary
    const summaryList = $("#fieldsSummaryList");
    if (summaryList.length) {
        summaryList.empty();
        currentSchema.forEach(field => {
            if (field.is_active) {
                summaryList.append(`
                    <div class="text-muted-text font-medium">
                        <i class="fas fa-check text-brand-red mr-2"></i>
                        ${field.name.replace(/_/g, " ")}
                    </div>
                `);
            }
        });
    }

    // Update table header dynamically
    const tableHeader = $("#invoicesTable thead");
    if (tableHeader.length) {
        let headerHtml = "<tr><th>Source</th><th>Page</th><th>Confidence</th>";
        currentSchema.forEach(field => {
            if (field.is_active) {
                headerHtml += `<th>${field.name.replace(/_/g, " ")}</th>`;
            }
        });
        headerHtml += "<th>Action</th></tr>";
        tableHeader.html(headerHtml);
    }
}

// ======================
// Confidence Score Helpers
// ======================
function getConfidenceBadge(score) {
    const numScore = parseInt(score) || 0;
    let colorClass, icon;
    
    if (numScore >= 85) {
        colorClass = 'bg-green-100 text-green-800 border-green-300';
        icon = 'check-circle';
    } else if (numScore >= 60) {
        colorClass = 'bg-yellow-100 text-yellow-800 border-yellow-300';
        icon = 'exclamation-circle';
    } else {
        colorClass = 'bg-red-100 text-red-800 border-red-300';
        icon = 'times-circle';
    }
    
    return `<span class="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-semibold border ${colorClass}">
        <i class="fas fa-${icon}"></i> ${numScore}%
    </span>`;
}

function getConfidenceColor(score) {
    const numScore = parseInt(score) || 0;
    if (numScore >= 85) return 'border-green-400';
    if (numScore >= 60) return 'border-yellow-400';
    return 'border-red-400';
}

// ======================
// Document Ready
// ======================
$(document).ready(function () {
  console.log("Invoice Extractor main.js loaded");
  console.log("Current schema initialized:", currentSchema);
  initializeEventListeners();
});

// ======================
// Initialize Event Listeners
// ======================
function initializeEventListeners() {
  // File input change
  $("#fileInput").on("change", handleFileSelect);

  // Drag and drop
  const uploadZone = $("#uploadZone")[0];
  uploadZone.addEventListener("dragover", handleDragOver);
  uploadZone.addEventListener("dragleave", handleDragLeave);
  uploadZone.addEventListener("drop", handleDrop);

  // Click to browse files (prevent recursion)
  $("#uploadZone").on("click", (e) => {
    if (e.target.id !== "fileInput" && e.target.tagName !== "BUTTON") {
      $("#fileInput").trigger("click");
    }
  });

  // Buttons
  $("#processBtn").on("click", processFiles);
  $("#exportBtn").on("click", exportToExcel);
  $("#processMoreBtn").on("click", resetApp);
  $("#prevInvoiceBtn").on("click", showPreviousInvoice);
  $("#nextInvoiceBtn").on("click", showNextInvoice);

  // Close modal on ESC
  $(document).on("keydown", (e) => {
    if (e.key === "Escape" && !$("#invoiceModal").hasClass("hidden")) {
      closeModal();
    }
  });

  // Close modal on outside click
  $("#invoiceModal").on("click", (e) => {
    if (e.target.id === "invoiceModal") closeModal();
  });

  // Enter key for new field input
  $("#newFieldInput").on("keypress", (e) => {
    if (e.key === "Enter") addNewField();
  });
}

// ======================
// File Handling
// ======================
function handleFileSelect(e) {
  handleFiles(e.target.files);
}

function handleFiles(files) {
  const allowedExtensions = ["pdf", "png", "jpg", "jpeg", "webp"];

  for (let file of files) {
    const extension = file.name.split(".").pop().toLowerCase();
    if (!allowedExtensions.includes(extension)) {
      showAlert("danger", `File "${file.name}" has an unsupported format.`);
      continue;
    }

    // Avoid duplicates
    if (selectedFiles.find((f) => f.name === file.name && f.size === file.size))
      continue;

    selectedFiles.push(file);
  }

  updateFileList();
}

function updateFileList() {
  const fileList = $("#fileList");
  fileList.empty();

  if (selectedFiles.length === 0) {
    $("#processBtn").hide();
    return;
  }

  $("#processBtn").show();

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

    fileItem.find(".remove-file").on("click", function () {
      removeFile($(this).data("index"));
    });

    fileList.append(fileItem);
  });
}

function removeFile(index) {
  selectedFiles.splice(index, 1);
  updateFileList();
}

function getFileIcon(filename) {
  const extension = filename.split(".").pop().toLowerCase();
  const iconMap = {
    pdf: "fas fa-file-pdf text-danger",
    png: "fas fa-image text-primary",
    jpg: "fas fa-image text-success",
    jpeg: "fas fa-image text-success",
    webp: "fas fa-image text-warning",
  };
  return iconMap[extension] || "fas fa-file";
}

function formatFileSize(bytes) {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i];
}

// ======================
// Drag & Drop Handlers
// ======================
function handleDragOver(e) {
  e.preventDefault();
  e.stopPropagation();
  $("#uploadZone").addClass("drag-over");
}

function handleDragLeave(e) {
  e.preventDefault();
  e.stopPropagation();
  $("#uploadZone").removeClass("drag-over");
}

function handleDrop(e) {
  e.preventDefault();
  e.stopPropagation();
  $("#uploadZone").removeClass("drag-over");
  const files = e.dataTransfer.files;
  handleFiles(files);
}

// ======================
// Process & Upload Files
// ======================
function processFiles() {
  if (selectedFiles.length === 0) {
    showAlert("warning", "Please select files to process.");
    return;
  }

  $("#progressSection").show();
  $("#processBtn").prop("disabled", true);
  updateProgress(0, 0, 0, "Uploading files...");

  const formData = new FormData();
  selectedFiles.forEach((file) => formData.append("files[]", file));

  $.ajax({
    url: "/upload",
    type: "POST",
    data: formData,
    processData: false,
    contentType: false,
    xhr: function () {
      const xhr = new window.XMLHttpRequest();
      xhr.upload.addEventListener(
        "progress",
        function (e) {
          if (e.lengthComputable) {
            const percentComplete = Math.round((e.loaded / e.total) * 20);
            updateProgress(percentComplete, 0, 0, "Uploading files...");
          }
        },
        false,
      );
      return xhr;
    },
    success: function (response) {
      if (response?.success && response.session_id) {
        currentSessionId = response.session_id;
        totalInvoices = response.total_invoices || 0;
        
        // Start polling for progress
        startProgressPolling(currentSessionId);
      } else {
        const msg = response?.error || "Processing failed.";
        showAlert("danger", msg);
        $("#progressSection").hide();
        $("#processBtn").prop("disabled", false);
      }
    },
    error: function (xhr) {
      const errorMsg =
        xhr.responseJSON?.error || "Upload failed. Please try again.";
      showAlert(errorMsg.includes("limit") ? "warning" : "danger", errorMsg);
      $("#progressSection").hide();
      $("#processBtn").prop("disabled", false);
    },
  });
}

function startProgressPolling(sessionId) {
  let lastPercentage = 0;

  const pollInterval = setInterval(() => {
    $.ajax({
      url: `/api/progress/${sessionId}`,
      type: "GET",
      success: function (status) {
        if (status.error && !status.completed) {
          clearInterval(pollInterval);
          showAlert("danger", status.error);
          $("#progressSection").hide();
          $("#processBtn").prop("disabled", false);
          return;
        }

        const percentage = status.percentage !== undefined ? status.percentage : 0;

        // Smooth animation - increment gradually towards target
        if (percentage > lastPercentage) {
          lastPercentage = percentage;
        }

        updateProgress(
          percentage,
          status.processed || 0,
          status.total || 0,
          status.message || "Processing..."
        );

        if (status.completed) {
          clearInterval(pollInterval);
          // Ensure we show 100%
          updateProgress(100, status.total, status.total, "Complete!");
          if (status.error) {
            showAlert("danger", "Processing error: " + status.error);
          } else {
            fetchUsage(); // Update usage stats after processing
            setTimeout(() => loadInvoices(sessionId), 500);
          }
        }
      },
      error: function () {
        clearInterval(pollInterval);
        showAlert("danger", "Lost connection to server while processing.");
        $("#progressSection").hide();
        $("#processBtn").prop("disabled", false);
      }
    });
  }, 500); // Poll every 500ms for smoother updates
}

// ======================
// Load & Display Invoices
// ======================
function loadInvoices(sessionId) {
  if (!sessionId) {
    showAlert("danger", "Session ID not found. Please try again.");
    return;
  }

  $.ajax({
    url: `/get_invoices/${sessionId}`,
    type: "GET",
    success: function (response) {
      if (response?.success) {
        displayInvoices(response.invoices || []);
        $("#progressSection").hide();
        $("#resultsSection").show().addClass("fade-in");
      } else {
        const msg = response?.error || "Failed to load invoices.";
        showAlert("danger", msg);
      }
    },
    error: function (xhr) {
      let message = "Failed to load invoices.";
      try {
        const json = JSON.parse(xhr.responseText);
        message = json.error || message;
      } catch (e) {
        message = xhr.statusText || message;
      }
      showAlert("danger", message);
    },
  });
}

// ======================
// Display Invoices in Table
// ======================
function displayInvoices(invoices) {
  $("#invoiceCount").text(invoices.length);

  if (dataTable) dataTable.destroy();

  const tableBody = $("#invoicesTable tbody");
  tableBody.empty();

  invoices.forEach((invoice, index) => {
    let row = "<tr>";
    row += `<td>${invoice.Source_File || ""}</td>`;
    row += `<td>${invoice.Page_Number || ""}</td>`;
    
    // Add confidence badge
    const confidence = invoice._overall_confidence || 0;
    row += `<td>${getConfidenceBadge(confidence)}</td>`;

    const schemaFields = currentSchema.filter(f => f.is_active).map(f => f.name);

    schemaFields.forEach((field) => {
      const value = invoice[field] || "-";
      row += `<td>${value}</td>`;
    });

    row += `<td>
            <button class="px-4 py-2 bg-brand-red text-white rounded-lg hover:bg-promo-red text-sm font-semibold transition shadow-md" onclick="viewInvoice(${index})">
                <i class="fas fa-eye mr-1"></i>View
            </button>
        </td>`;
    row += "</tr>";

    tableBody.append(row);
  });

  dataTable = $("#invoicesTable").DataTable({
    pageLength: 10,
    lengthMenu: [
      [10, 25, 50, -1],
      [10, 25, 50, "All"],
    ],
    order: [[0, "asc"]],
    language: {
      search: "_INPUT_",
      searchPlaceholder: "Search invoices...",
    },
    columnDefs: [{ targets: "_all", className: "text-nowrap" }],
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
    type: "GET",
    success: function (response) {
      if (response?.success) showInvoiceModal(response, index);
      else showAlert("danger", response?.error || "Failed to load invoice.");
    },
    error: function () {
      showAlert("danger", "Failed to load invoice details.");
    },
  });
}

function showInvoiceModal(invoiceData, index) {
  $("#modalRowNumber").text(`Row ${index}`);
  $("#modalInvoiceImage").attr(
    "src",
    `data:image/png;base64,${invoiceData.image}`,
  );

  const dataContainer = $("#modalInvoiceData");
  dataContainer.empty();

  // Add overall confidence header
  const overallConfidence = invoiceData.overall_confidence || 0;
  const overallBadge = getConfidenceBadge(overallConfidence);
  dataContainer.append(`
    <div class="bg-gray-50 rounded-lg p-4 border-2 border-gray-200 shadow-sm mb-4 col-span-full">
      <div class="flex items-center justify-between">
        <div class="text-sm font-bold text-dark-text">Overall Extraction Confidence</div>
        ${overallBadge}
      </div>
    </div>
  `);

  const data = invoiceData.data || {};
  const confidenceScores = invoiceData.confidence_scores || {};
  
  for (let key in data) {
    if (key !== "_image_base64" && key !== "row_id") {
      const value = data[key] || "-";
      const label = key.replace(/_/g, " ");
      const fieldConfidence = confidenceScores[key] || 0;
      const borderColor = getConfidenceColor(fieldConfidence);
      
      const fieldHtml = `
                <div class="bg-white rounded-lg p-3 border-l-4 ${borderColor} shadow-sm">
                    <div class="flex items-center justify-between mb-1">
                      <div class="text-xs font-semibold text-muted-text uppercase">${label}</div>
                      <span class="text-xs font-medium ${fieldConfidence >= 85 ? 'text-green-600' : fieldConfidence >= 60 ? 'text-yellow-600' : 'text-red-600'}">
                        ${fieldConfidence}%
                      </span>
                    </div>
                    <div class="text-sm font-semibold text-dark-text">${value}</div>
                </div>
            `;
      dataContainer.append(fieldHtml);
    }
  }

  $("#prevInvoiceBtn").prop("disabled", index === 0);
  $("#nextInvoiceBtn").prop("disabled", index === totalInvoices - 1);
  $("#invoiceCounter").text(`Invoice ${index + 1} of ${totalInvoices}`);

  $("#invoiceModal").removeClass("hidden");
  $("body").addClass("overflow-hidden");
}

function closeModal() {
  $("#invoiceModal").addClass("hidden");
  $("body").removeClass("overflow-hidden");
}

// ======================
// Navigation
// ======================
function showPreviousInvoice() {
  if (currentInvoiceIndex > 0) viewInvoice(currentInvoiceIndex - 1);
}

function showNextInvoice() {
  if (currentInvoiceIndex < totalInvoices - 1)
    viewInvoice(currentInvoiceIndex + 1);
}

// ======================
// Export & Reset
// ======================
function exportToExcel() {
  if (!currentSessionId) {
    showAlert("danger", "No session to export.");
    return;
  }
  window.location.href = `/export/${currentSessionId}`;
}

function resetApp() {
  selectedFiles = [];
  currentSessionId = null;
  currentInvoiceIndex = 0;
  totalInvoices = 0;

  $("#fileList").empty();
  $("#fileInput").val("");
  $("#processBtn").hide().prop("disabled", false);
  $("#resultsSection").hide();
  $("#progressSection").hide();

  if (dataTable) {
    dataTable.destroy();
    dataTable = null;
  }

  $("html, body").animate({ scrollTop: 0 }, 500);
}

// ======================
// Progress & Alerts
// ======================
function updateProgress(percentage, processed, total, message) {
  $("#progressPercentage").text(percentage + "%");
  $("#progressBar").css("width", percentage + "%");
  $("#progressBarText").text(percentage > 10 ? percentage + "%" : "");
  $("#progressText").text(message);
  $("#progressCount").text(total > 0 ? `${processed} / ${total} invoices` : "");
}

function showAlert(type, message) {
  const alertClass =
    type === "danger"
      ? "bg-red-100 text-red-800 border-red-300"
      : type === "warning"
        ? "bg-yellow-100 text-yellow-800 border-yellow-300"
        : "bg-green-100 text-green-800 border-green-300";

  const iconClass =
    type === "danger"
      ? "exclamation-circle"
      : type === "warning"
        ? "exclamation-triangle"
        : "check-circle";

  const alert = $(`
        <div class="fixed top-4 right-4 ${alertClass} border-2 px-6 py-4 rounded-lg shadow-lg z-50 max-w-md animate-fade-in">
            <div class="flex items-center gap-3">
                <i class="fas fa-${iconClass} text-xl"></i>
                <p class="font-semibold">${message}</p>
                <button onclick="this.parentElement.parentElement.remove()" class="ml-4 text-xl font-bold opacity-50 hover:opacity-100">×</button>
            </div>
        </div>
    `);

  $("body").append(alert);
  setTimeout(
    () =>
      alert.fadeOut(300, function () {
        $(this).remove();
      }),
    5000,
  );
}
// ======================
// ======================
// Schema Management (PostgreSQL Dynamic)
// ======================
function openManageFieldsModal() {
  renderFieldsList();
  $("#manageFieldsModal").removeClass("hidden");
}

function closeManageFieldsModal() {
  $("#manageFieldsModal").addClass("hidden");
}

function renderFieldsList() {
  const list = $("#fieldsList");
  list.empty();
  
  $("#fieldCountBadge").text(currentSchema.length);

  currentSchema.forEach((field) => {
    const item = $(`
            <div class="bg-white p-3 rounded-lg border border-gray-100 shadow-sm hover:border-brand-red/20 transition-all">
                <div class="flex items-center gap-3">
                    <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-2 mb-1">
                            <span class="text-[10px] font-bold text-gray-400 uppercase tracking-wider">ID:</span>
                            <input type="text" value="${field.name}" 
                                   onchange="patchField(${field.id}, {name: this.value})"
                                   class="flex-1 font-bold text-sm text-dark-text bg-transparent border-b border-transparent hover:border-red-200 focus:border-brand-red focus:outline-none transition-colors truncate">
                        </div>
                        <div class="flex items-center gap-2">
                            <span class="text-[10px] font-bold text-gray-400 uppercase tracking-wider">Prompt:</span>
                            <input type="text" value="${field.description || ""}"
                                   onchange="patchField(${field.id}, {description: this.value})"
                                   placeholder="AI instruction..."
                                   class="flex-1 text-xs text-muted-text bg-transparent border-b border-transparent hover:border-red-200 focus:border-brand-red focus:outline-none transition-colors truncate">
                        </div>
                    </div>
                    
                    <div class="flex items-center gap-2 shrink-0 border-l pl-3 border-gray-100">
                        <div class="flex flex-col items-center gap-1">
                            <input type="checkbox" ${field.is_active ? 'checked' : ''} 
                                   onchange="patchField(${field.id}, {is_active: this.checked})"
                                   id="active_${field.id}" 
                                   class="w-4 h-4 text-brand-red border-gray-300 rounded focus:ring-brand-red cursor-pointer">
                            <label for="active_${field.id}" class="text-[8px] font-bold text-gray-400 cursor-pointer">ACTIVE</label>
                        </div>
                        <button onclick="deleteField(${field.id})" class="text-gray-300 hover:text-red-500 transition-colors p-2" title="Delete Field">
                            <i class="fas fa-trash-alt text-sm"></i>
                        </button>
                    </div>
                </div>
            </div>
        `);
    
    list.append(item);
  });
}

function addNewField() {
  const nameInput = $("#newFieldName");
  const descInput = $("#newFieldDesc");
  const name = nameInput.val().trim();
  const description = descInput.val().trim();

  if (!name) {
    showAlert("warning", "Field name is required");
    return;
  }

  $.ajax({
    url: "/api/fields",
    type: "POST",
    contentType: "application/json",
    data: JSON.stringify({ name, description }),
    success: function (newField) {
      currentSchema.push(newField);
      nameInput.val("");
      descInput.val("");
      renderFieldsList();
      updateUIWithNewSchema();
      showAlert("success", "Field added successfully");
    },
    error: function (xhr) {
      showAlert("danger", xhr.responseJSON?.error || "Failed to add field");
    },
  });
}

function patchField(id, data) {
  $.ajax({
    url: `/api/fields/${id}`,
    type: "PATCH",
    contentType: "application/json",
    data: JSON.stringify(data),
    success: function (updatedField) {
      const index = currentSchema.findIndex(f => f.id === id);
      if (index !== -1) {
          currentSchema[index] = updatedField;
          updateUIWithNewSchema();
      }
    },
    error: function (xhr) {
      showAlert("danger", xhr.responseJSON?.error || "Failed to update field");
    },
  });
}

function deleteField(id) {
  if (!confirm("Are you sure you want to delete this field?")) return;

  $.ajax({
    url: `/api/fields/${id}`,
    type: "DELETE",
    success: function () {
      currentSchema = currentSchema.filter(f => f.id !== id);
      renderFieldsList();
      updateUIWithNewSchema();
      showAlert("success", "Field deleted");
    },
    error: function () {
      showAlert("danger", "Failed to delete field");
    },
  });
}

// ======================
// Prompt Preview logic
// ======================
function openPromptPreviewModal() {
  $("#promptContentView").text("Loading AI prompt...");
  $("#promptPreviewModal").removeClass("hidden");
  
  $.get('/api/prompt-preview', function(data) {
    $("#promptContentView").text(data.prompt);
  }).fail(function() {
    $("#promptContentView").text("Error loading prompt.");
  });
}

function closePromptPreviewModal() {
  $("#promptPreviewModal").addClass("hidden");
}

let trialCountdownInterval;

function startTrialCountdown(expiryDate) {
    // Clear any existing interval
    if (trialCountdownInterval) clearInterval(trialCountdownInterval);
    
    function update() {
        const now = new Date();
        const diff = expiryDate - now;
        
        if (diff <= 0) {
            $("#trialDaysText").text("Expired");
            clearInterval(trialCountdownInterval);
            // Optionally force UI refresh to lock it down
            fetchUsageStats(); 
            return;
        }
        
        const days = Math.floor(diff / (1000 * 60 * 60 * 24));
        const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((diff % (1000 * 60)) / 1000);
        
        let timeString = "";
        if (days > 0) timeString += `${days}d `;
        if (hours > 0 || days > 0) timeString += `${hours}h `;
        timeString += `${minutes}m ${seconds}s`;
        
        $("#trialDaysText").text(timeString);
    }
    
    // Initial call
    update();
    // Start interval
    trialCountdownInterval = setInterval(update, 1000);
}
