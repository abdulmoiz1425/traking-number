(function () {
  const $ = (id) => document.getElementById(id);

  const serviceAccountBanner = $("serviceAccountBanner");
  const serviceAccountEmail = $("serviceAccountEmail");
  const uploadSection = $("uploadSection");
  const processingSection = $("processingSection");
  const resultsArea = $("resultsArea");
  const errorArea = $("errorArea");

  const trackingUrlInput = $("trackingUrlInput");
  const mainUrlInput = $("mainUrlInput");
  const trackingFilename = $("trackingFilename");
  const mainFilename = $("mainFilename");
  const trackingWorksheetSelect = $("trackingWorksheetSelect");
  const mainWorksheetSelect = $("mainWorksheetSelect");
  const trackingColumnSelect = $("trackingColumnSelect");
  const mainColumnSelect = $("mainColumnSelect");
  const trackingHasHeader = $("trackingHasHeader");
  const mainHasHeader = $("mainHasHeader");
  const processBtn = $("processBtn");
  const resetBtn = $("resetBtn");
  const processAnotherBtn = $("processAnotherBtn");
  const loadingIndicator = $("loadingIndicator");
  const summaryList = $("summaryList");
  const viewSheetBtn = $("viewSheetBtn");
  const downloadUnmatchedBtn = $("downloadUnmatchedBtn");

  function showError(message) {
    errorArea.textContent = message;
    errorArea.classList.remove("hidden");
  }

  function clearError() {
    errorArea.textContent = "";
    errorArea.classList.add("hidden");
  }

  function columnLabel(column) {
    let label = `Column ${column.letter}`;
    if (column.header) label += ` — ${column.header}`;
    if (column.example) label += ` — Example: ${column.example}`;
    return label;
  }

  function populateWorksheetSelect(selectEl, worksheets, selected) {
    selectEl.innerHTML = "";
    worksheets.forEach((name) => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      if (name === selected) option.selected = true;
      selectEl.appendChild(option);
    });
    selectEl.disabled = worksheets.length <= 1;
  }

  function populateColumnSelect(selectEl, columns, detectedLetter) {
    selectEl.innerHTML = "";
    columns.forEach((column) => {
      const option = document.createElement("option");
      option.value = column.letter;
      option.textContent = columnLabel(column);
      if (column.letter === detectedLetter) option.selected = true;
      selectEl.appendChild(option);
    });
    selectEl.disabled = false;
  }

  function applyConnectResult(data) {
    populateWorksheetSelect(
      trackingWorksheetSelect,
      data.tracking_file.worksheets,
      data.tracking_file.selected_worksheet
    );
    populateColumnSelect(trackingColumnSelect, data.tracking_file.columns, data.tracking_file.detected_column);
    populateWorksheetSelect(mainWorksheetSelect, data.main_file.worksheets, data.main_file.selected_worksheet);
    populateColumnSelect(mainColumnSelect, data.main_file.columns, data.main_file.detected_column);
    maybeEnableProcessButton();
  }

  function maybeEnableProcessButton() {
    const trackingReady = trackingColumnSelect.options.length > 0;
    const mainReady = mainColumnSelect.options.length > 0;
    processBtn.disabled = !(trackingReady && mainReady);
  }

  function maybeConnectSheets() {
    if (trackingUrlInput.value.trim() && mainUrlInput.value.trim()) {
      connectSheets();
    }
  }

  function connectSheets() {
    clearError();
    fetch("/connect-sheets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tracking_sheet_url: trackingUrlInput.value.trim(),
        main_sheet_url: mainUrlInput.value.trim(),
      }),
    })
      .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) {
          showError(data.error || "Could not connect to those Google Sheets.");
          return;
        }
        applyConnectResult(data);
      })
      .catch(() => showError("Could not reach the server. Please try again."));
  }

  function fetchColumnsForSheet(fileKey, sheetName, columnSelectEl) {
    clearError();
    fetch(`/worksheet-columns?file=${encodeURIComponent(fileKey)}&sheet=${encodeURIComponent(sheetName)}`)
      .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) {
          showError(data.error || "Could not read the selected worksheet.");
          return;
        }
        populateColumnSelect(columnSelectEl, data.columns, data.detected_column);
        maybeEnableProcessButton();
      })
      .catch(() => showError("Could not reach the server. Please try again."));
  }

  function setLoading(isLoading) {
    loadingIndicator.classList.toggle("hidden", !isLoading);
    processBtn.disabled = isLoading;
  }

  function renderSummary(summary) {
    const labels = {
      total_tracking_numbers_read: "Total tracking numbers read",
      blank_tracking_cells_ignored: "Blank tracking cells ignored",
      duplicate_tracking_numbers_removed: "Duplicate tracking numbers removed",
      unique_tracking_numbers_searched: "Unique tracking numbers searched",
      tracking_numbers_matched: "Tracking numbers matched",
      tracking_numbers_not_matched: "Tracking numbers not matched",
      total_rows_highlighted: "Total rows highlighted",
      processing_status: "Processing status",
      processing_datetime: "Processing date and time",
    };
    summaryList.innerHTML = "";
    Object.entries(labels).forEach(([key, label]) => {
      if (!(key in summary)) return;
      const li = document.createElement("li");
      li.textContent = `${label}: ${summary[key]}`;
      summaryList.appendChild(li);
    });
    if (summary.tracking_numbers_matched === 0) {
      const li = document.createElement("li");
      li.textContent = "No matching tracking numbers were found.";
      summaryList.appendChild(li);
    }
  }

  function showResults(data) {
    renderSummary(data.summary);
    viewSheetBtn.href = data.main_sheet_url;
    downloadUnmatchedBtn.href = `/download-unmatched/${data.unmatched_token}`;
    uploadSection.classList.add("hidden");
    processingSection.classList.add("hidden");
    resultsArea.classList.remove("hidden");
  }

  function processFiles() {
    clearError();
    setLoading(true);

    fetch("/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tracking_sheet: trackingWorksheetSelect.value,
        tracking_column: trackingColumnSelect.value,
        tracking_has_header: trackingHasHeader.checked,
        main_sheet: mainWorksheetSelect.value,
        main_column: mainColumnSelect.value,
        main_has_header: mainHasHeader.checked,
      }),
    })
      .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
      .then(({ ok, data }) => {
        setLoading(false);
        if (!ok) {
          processBtn.disabled = false;
          showError(data.error || "Processing failed.");
          return;
        }
        showResults(data);
      })
      .catch(() => {
        setLoading(false);
        processBtn.disabled = false;
        showError("Could not reach the server. Please try again.");
      });
  }

  function resetAll() {
    fetch("/reset", { method: "POST" }).finally(() => window.location.reload());
  }

  function restoreSessionState() {
    fetch("/sheets-status")
      .then((response) => response.json())
      .then((data) => {
        if (!data.connected) return;

        trackingUrlInput.value = data.tracking_url || "";
        mainUrlInput.value = data.main_url || "";
        trackingFilename.textContent = data.tracking_name || "";
        mainFilename.textContent = data.main_name || "";
        applyConnectResult(data);

        if (data.result) {
          showResults(data.result);
        }
      })
      .catch(() => {});
  }

  function loadServiceAccountEmail() {
    fetch("/service-account-email")
      .then((response) => response.json())
      .then((data) => {
        if (data.email) {
          serviceAccountEmail.textContent = data.email;
          serviceAccountBanner.classList.remove("hidden");
        } else if (data.error) {
          showError(data.error);
        }
      })
      .catch(() => {});
  }

  trackingUrlInput.addEventListener("change", maybeConnectSheets);
  mainUrlInput.addEventListener("change", maybeConnectSheets);

  trackingWorksheetSelect.addEventListener("change", () =>
    fetchColumnsForSheet("tracking", trackingWorksheetSelect.value, trackingColumnSelect)
  );
  mainWorksheetSelect.addEventListener("change", () =>
    fetchColumnsForSheet("main", mainWorksheetSelect.value, mainColumnSelect)
  );

  processBtn.addEventListener("click", processFiles);
  resetBtn.addEventListener("click", resetAll);
  processAnotherBtn.addEventListener("click", resetAll);

  loadServiceAccountEmail();
  restoreSessionState();
})();
