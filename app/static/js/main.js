(function () {
  const $ = (id) => document.getElementById(id);

  const signInSection = $("signInSection");
  const signOutBtn = $("signOutBtn");
  const pickerSection = $("pickerSection");
  const pickSheetBtn = $("pickSheetBtn");
  const selectedSheetName = $("selectedSheetName");
  const tabsSection = $("tabsSection");
  const processingSection = $("processingSection");
  const resultsArea = $("resultsArea");
  const errorArea = $("errorArea");

  const trackingTabSelect = $("trackingTabSelect");
  const mainTabSelect = $("mainTabSelect");
  const netPayableTabSelect = $("netPayableTabSelect");
  const trackingColumnSelect = $("trackingColumnSelect");
  const trackingStatusColumnSelect = $("trackingStatusColumnSelect");
  const mainColumnSelect = $("mainColumnSelect");
  const netPayableTrackingColumnSelect = $("netPayableTrackingColumnSelect");
  const netPayableValueColumnSelect = $("netPayableValueColumnSelect");
  const trackingHasHeader = $("trackingHasHeader");
  const mainHasHeader = $("mainHasHeader");
  const netPayableHasHeader = $("netPayableHasHeader");
  const processBtn = $("processBtn");
  const resetBtn = $("resetBtn");
  const processAnotherBtn = $("processAnotherBtn");
  const loadingIndicator = $("loadingIndicator");
  const summaryList = $("summaryList");
  const viewSheetBtn = $("viewSheetBtn");
  const downloadUnmatchedBtn = $("downloadUnmatchedBtn");

  const AUTH_ERROR_MESSAGES = {
    consent_denied: "Google sign-in was cancelled.",
    sign_in_failed: "Google sign-in failed. Please try again.",
  };

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

  function populateTabSelect(selectEl, tabs, selected) {
    selectEl.innerHTML = "";
    tabs.forEach((name) => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      if (name === selected) option.selected = true;
      selectEl.appendChild(option);
    });
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

  function maybeEnableProcessButton() {
    const trackingReady = trackingColumnSelect.options.length > 0 && trackingStatusColumnSelect.options.length > 0;
    const mainReady = mainColumnSelect.options.length > 0;
    const netPayableReady =
      netPayableTrackingColumnSelect.options.length > 0 && netPayableValueColumnSelect.options.length > 0;
    processBtn.disabled = !(trackingReady && mainReady && netPayableReady);
  }

  function loadColumnsForTab(tabName, columnSelectEl, statusSelectEl, netPayableSelectEl) {
    clearError();
    fetch(`/worksheet-columns?tab=${encodeURIComponent(tabName)}`)
      .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) {
          showError(data.error || "Could not read the selected tab.");
          return;
        }
        populateColumnSelect(columnSelectEl, data.columns, data.detected_column);
        if (statusSelectEl) {
          populateColumnSelect(statusSelectEl, data.columns, data.detected_status_column);
        }
        if (netPayableSelectEl) {
          populateColumnSelect(netPayableSelectEl, data.columns, data.detected_net_payable_column);
        }
        maybeEnableProcessButton();
      })
      .catch(() => showError("Could not reach the server. Please try again."));
  }

  function showTabsAndProcessing(
    spreadsheetTitle,
    tabs,
    trackingTab,
    mainTab,
    netPayableTab,
    trackingFile,
    mainFile,
    netPayableFile
  ) {
    selectedSheetName.textContent = spreadsheetTitle;
    pickerSection.classList.remove("hidden");
    tabsSection.classList.remove("hidden");
    processingSection.classList.remove("hidden");

    populateTabSelect(trackingTabSelect, tabs, trackingTab);
    populateTabSelect(mainTabSelect, tabs, mainTab);
    populateTabSelect(netPayableTabSelect, tabs, netPayableTab);

    if (trackingFile) {
      populateColumnSelect(trackingColumnSelect, trackingFile.columns, trackingFile.detected_column);
      populateColumnSelect(trackingStatusColumnSelect, trackingFile.columns, trackingFile.detected_status_column);
    } else {
      loadColumnsForTab(trackingTab, trackingColumnSelect, trackingStatusColumnSelect);
    }
    if (mainFile) {
      populateColumnSelect(mainColumnSelect, mainFile.columns, mainFile.detected_column);
    } else {
      loadColumnsForTab(mainTab, mainColumnSelect);
    }
    if (netPayableFile) {
      populateColumnSelect(netPayableTrackingColumnSelect, netPayableFile.columns, netPayableFile.detected_column);
      populateColumnSelect(
        netPayableValueColumnSelect,
        netPayableFile.columns,
        netPayableFile.detected_net_payable_column
      );
    } else {
      loadColumnsForTab(netPayableTab, netPayableTrackingColumnSelect, null, netPayableValueColumnSelect);
    }
    maybeEnableProcessButton();
  }

  function connectSheet(spreadsheetId) {
    clearError();
    fetch("/connect-sheet", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ spreadsheet_id: spreadsheetId }),
    })
      .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) {
          showError(data.error || "Could not connect to that Google Sheet.");
          return;
        }
        showTabsAndProcessing(
          data.spreadsheet_title,
          data.tabs,
          data.tracking_tab,
          data.main_tab,
          data.net_payable_tab,
          data.tracking_file,
          data.main_file,
          data.net_payable_file
        );
      })
      .catch(() => showError("Could not reach the server. Please try again."));
  }

  function openPicker() {
    clearError();
    fetch("/picker-token")
      .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
      .then(({ ok, data }) => {
        if (!ok) {
          showError(data.error || "Could not start the Google Sheet picker.");
          return;
        }
        gapi.load("picker", () => {
          const view = new google.picker.DocsView(google.picker.ViewId.SPREADSHEETS);
          const picker = new google.picker.PickerBuilder()
            .addView(view)
            .setOAuthToken(data.token)
            .setDeveloperKey(data.api_key)
            .setAppId(data.app_id)
            .setCallback((pickerData) => {
              if (pickerData.action === google.picker.Action.PICKED) {
                connectSheet(pickerData.docs[0].id);
              }
            })
            .build();
          picker.setVisible(true);
        });
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
      rows_marked_delivered: "Rows marked Delivered (green)",
      rows_marked_return: "Rows marked Return (red)",
      rows_with_unrecognized_status: "Matched rows with an unrecognized status (left uncolored)",
      total_rows_highlighted: "Total rows highlighted",
      net_payable_rows_updated: "Net Payable values updated",
      net_payable_column: "Net Payable column",
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
    tabsSection.classList.add("hidden");
    processingSection.classList.add("hidden");
    resultsArea.classList.remove("hidden");
  }

  function processSheet() {
    clearError();
    setLoading(true);

    fetch("/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tracking_tab: trackingTabSelect.value,
        tracking_column: trackingColumnSelect.value,
        tracking_status_column: trackingStatusColumnSelect.value,
        tracking_has_header: trackingHasHeader.checked,
        main_tab: mainTabSelect.value,
        main_column: mainColumnSelect.value,
        main_has_header: mainHasHeader.checked,
        net_payable_tab: netPayableTabSelect.value,
        net_payable_tracking_column: netPayableTrackingColumnSelect.value,
        net_payable_value_column: netPayableValueColumnSelect.value,
        net_payable_has_header: netPayableHasHeader.checked,
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

  function signOut() {
    fetch("/google/logout", { method: "POST" }).finally(() => window.location.reload());
  }

  function showSignedOutUI() {
    signInSection.classList.remove("hidden");
    signOutBtn.classList.add("hidden");
    pickerSection.classList.add("hidden");
    tabsSection.classList.add("hidden");
    processingSection.classList.add("hidden");
  }

  function showSignedInUI() {
    signInSection.classList.add("hidden");
    signOutBtn.classList.remove("hidden");
    pickerSection.classList.remove("hidden");
  }

  function restoreSheetState() {
    fetch("/sheets-status")
      .then((response) => response.json())
      .then((data) => {
        if (!data.connected) return;

        const trackingTab = data.tabs[0];
        const mainTab = data.tabs.length > 1 ? data.tabs[1] : data.tabs[0];
        const netPayableTab = data.tabs.length > 2 ? data.tabs[2] : data.tabs[0];
        showTabsAndProcessing(
          data.spreadsheet_title,
          data.tabs,
          trackingTab,
          mainTab,
          netPayableTab,
          null,
          null,
          null
        );

        if (data.result) {
          showResults(data.result);
        }
      })
      .catch(() => {});
  }

  function checkAuthError() {
    const params = new URLSearchParams(window.location.search);
    const authError = params.get("auth_error");
    if (authError) {
      showError(AUTH_ERROR_MESSAGES[authError] || "Google sign-in failed. Please try again.");
      params.delete("auth_error");
      const newSearch = params.toString();
      history.replaceState(null, "", window.location.pathname + (newSearch ? `?${newSearch}` : ""));
    }
  }

  function init() {
    checkAuthError();
    fetch("/auth-status")
      .then((response) => response.json())
      .then((data) => {
        if (data.authenticated) {
          showSignedInUI();
          restoreSheetState();
        } else {
          showSignedOutUI();
        }
      })
      .catch(() => showSignedOutUI());
  }

  pickSheetBtn.addEventListener("click", openPicker);

  trackingTabSelect.addEventListener("change", () =>
    loadColumnsForTab(trackingTabSelect.value, trackingColumnSelect, trackingStatusColumnSelect)
  );
  mainTabSelect.addEventListener("change", () => loadColumnsForTab(mainTabSelect.value, mainColumnSelect));
  netPayableTabSelect.addEventListener("change", () =>
    loadColumnsForTab(netPayableTabSelect.value, netPayableTrackingColumnSelect, null, netPayableValueColumnSelect)
  );

  processBtn.addEventListener("click", processSheet);
  resetBtn.addEventListener("click", resetAll);
  processAnotherBtn.addEventListener("click", resetAll);
  signOutBtn.addEventListener("click", signOut);

  init();
})();
