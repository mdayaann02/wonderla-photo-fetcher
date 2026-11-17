/**
 * Wonderla Photo Retrieval Client
 */

let currentAlbum = null;
let currentPhotos = [];
let filteredPhotos = [];
let selectedAssetIds = new Set();
let activeLightboxIndex = 0;
let html5QrCode = null;
let savePollInterval = null;

// DOM references
const claimInput = document.getElementById("claim-code-input");
const loadingState = document.getElementById("loading-state");
const resultsSection = document.getElementById("results-section");
const photosGrid = document.getElementById("photos-grid");
const rideFilter = document.getElementById("ride-filter");
const resVenueName = document.getElementById("res-venue-name");
const resCodeBadge = document.getElementById("res-code-badge");
const resPhotosCount = document.getElementById("res-photos-count");
const selectionCount = document.getElementById("selection-count");
const btnDownloadSelected = document.getElementById("btn-download-selected");
const btnSelectedCount = document.getElementById("btn-selected-count");

// Lightbox DOM
const lightboxModal = document.getElementById("lightbox-modal");
const lightboxImage = document.getElementById("lightbox-image");
const lightboxRide = document.getElementById("lightbox-ride");
const lightboxDate = document.getElementById("lightbox-date");
const lightboxDim = document.getElementById("lightbox-dim");
const lightboxSize = document.getElementById("lightbox-size");
const lightboxDownloadLink = document.getElementById("lightbox-download-link");

// Scanner DOM
const scannerModal = document.getElementById("scanner-modal");

// Progress Modal DOM
const progressModal = document.getElementById("progress-modal");
const progressBarFill = document.getElementById("progress-bar-fill");
const progressStatsText = document.getElementById("progress-stats-text");
const progressCurrentFile = document.getElementById("progress-current-file");
const progressCloseBtn = document.getElementById("progress-close-btn");

// Initialize
document.addEventListener("DOMContentLoaded", () => {
  // Check for URL query parameter ?code=...
  const urlParams = new URLSearchParams(window.location.search);
  const codeParam = urlParams.get("code") || urlParams.get("claim");
  if (codeParam) {
    claimInput.value = codeParam.trim().toUpperCase();
    performSearch(claimInput.value);
  }

  // Keyboard navigation for lightbox
  window.addEventListener("keydown", (e) => {
    if (!lightboxModal.classList.contains("active")) return;
    if (e.key === "ArrowLeft") prevLightbox();
    if (e.key === "ArrowRight") nextLightbox();
    if (e.key === "Escape") closeLightbox();
  });
});

function useSampleCode(sample) {
  claimInput.value = sample;
  performSearch(sample);
}

function handleSearch(e) {
  if (e) e.preventDefault();
  const code = claimInput.value.trim();
  if (!code) {
    showToast("Please enter a claim code or scan a QR code", "error");
    return;
  }
  performSearch(code);
}

async function performSearch(code) {
  // Reset state
  resultsSection.classList.remove("active");
  loadingState.classList.add("active");
  selectedAssetIds.clear();
  updateSelectionUi();

  try {
    const resp = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code })
    });

    const data = await resp.json();
    loadingState.classList.remove("active");

    if (!resp.ok || data.status !== "success") {
      showToast(data.message || "Failed to find photos for this code", "error");
      return;
    }

    currentAlbum = data;
    currentPhotos = data.photos || [];
    filteredPhotos = [...currentPhotos];

    if (currentPhotos.length === 0) {
      showToast("No photos found under this code.", "info");
      return;
    }

    showToast(`Found ${currentPhotos.length} photos!`, "success");
    displayResults();
  } catch (err) {
    loadingState.classList.remove("active");
    showToast(`Network error: ${err.message}`, "error");
  }
}

function displayResults() {
  resVenueName.textContent = currentAlbum.venue || "Wonderla";
  resCodeBadge.textContent = currentAlbum.code;
  resPhotosCount.textContent = `${currentPhotos.length} Photos Found`;

  // Populate Ride Filter dropdown
  const rides = new Set(currentPhotos.map(p => p.ride).filter(Boolean));
  rideFilter.innerHTML = `<option value="ALL">All Attractions & Rides (${currentPhotos.length})</option>`;
  rides.forEach(ride => {
    const count = currentPhotos.filter(p => p.ride === ride).length;
    const opt = document.createElement("option");
    opt.value = ride;
    opt.textContent = `${ride} (${count})`;
    rideFilter.appendChild(opt);
  });

  renderPhotosGrid();
  resultsSection.classList.add("active");

  // Scroll smoothly to results
  resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderPhotosGrid() {
  photosGrid.innerHTML = "";

  if (filteredPhotos.length === 0) {
    photosGrid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">No photos match the selected ride filter.</div>`;
    return;
  }

  filteredPhotos.forEach((photo, idx) => {
    const isSelected = selectedAssetIds.has(photo.id);
    const card = document.createElement("div");
    card.className = `photo-card ${isSelected ? 'selected' : ''}`;
    card.id = `card-${photo.id}`;

    const previewUrl = `/api/asset-preview?id=${encodeURIComponent(photo.id)}&venueId=${encodeURIComponent(photo.venueId)}`;
    const downloadUrl = `/api/asset-download?id=${encodeURIComponent(photo.id)}&venueId=${encodeURIComponent(photo.venueId)}`;

    card.innerHTML = `
      <div class="photo-thumbnail-wrap" onclick="openLightbox(${idx})">
        <img class="photo-thumbnail" src="${previewUrl}" alt="${photo.ride}" loading="lazy" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%22100%22 height=%22100%22><text y=%2250%%22 x=%2250%%22 text-anchor=%22middle%22 fill=%22%23666%22>Photo</text></svg>'">
        <div class="photo-badge-ride">
          <span>🎢</span> ${escapeHtml(photo.ride)}
        </div>
        <div class="photo-checkbox-wrap" onclick="event.stopPropagation()">
          <input type="checkbox" class="photo-checkbox" ${isSelected ? 'checked' : ''} onchange="toggleSelectPhoto('${photo.id}', this.checked)">
        </div>
      </div>
      <div class="photo-info">
        <div class="photo-meta-row">
          <span>🕒 ${photo.captureDate.split(" ")[1] || photo.captureDate}</span>
          <span>📐 ${photo.dimension || 'High Res'}</span>
        </div>
        <div class="photo-meta-row">
          <span>ID: ${photo.id.slice(-6)}</span>
          <span style="color: #fbbf24; font-weight: 600;">${photo.sizeFormatted}</span>
        </div>
        <div class="photo-card-actions">
          <button class="btn-card-action" onclick="openLightbox(${idx})">
            <span>👁️</span> Preview
          </button>
          <a class="btn-card-action" href="${downloadUrl}" target="_blank" download="${photo.filename}">
            <span>⬇️</span> Download
          </a>
        </div>
      </div>
    `;

    photosGrid.appendChild(card);
  });
}

function filterPhotos() {
  const selectedRide = rideFilter.value;
  if (selectedRide === "ALL") {
    filteredPhotos = [...currentPhotos];
  } else {
    filteredPhotos = currentPhotos.filter(p => p.ride === selectedRide);
  }
  renderPhotosGrid();
}

function toggleSelectPhoto(assetId, checked) {
  if (checked) {
    selectedAssetIds.add(assetId);
  } else {
    selectedAssetIds.delete(assetId);
  }

  const card = document.getElementById(`card-${assetId}`);
  if (card) {
    card.classList.toggle("selected", checked);
  }
  updateSelectionUi();
}

function selectAllPhotos(select) {
  if (select) {
    filteredPhotos.forEach(p => selectedAssetIds.add(p.id));
  } else {
    selectedAssetIds.clear();
  }

  // Update card visuals
  document.querySelectorAll(".photo-card").forEach(c => {
    const checkbox = c.querySelector(".photo-checkbox");
    if (checkbox) checkbox.checked = select;
    c.classList.toggle("selected", select);
  });

  updateSelectionUi();
}

function updateSelectionUi() {
  const count = selectedAssetIds.size;
  selectionCount.textContent = `${count} selected`;
  btnSelectedCount.textContent = count;
  btnDownloadSelected.style.display = count > 0 ? "inline-flex" : "none";
}

// Lightbox
function openLightbox(index) {
  activeLightboxIndex = index;
  updateLightboxContent();
  lightboxModal.classList.add("active");
  document.body.style.overflow = "hidden";
}

function closeLightbox() {
  lightboxModal.classList.remove("active");
  document.body.style.overflow = "";
}

function handleLightboxBackdropClick(e) {
  if (e.target === lightboxModal) {
    closeLightbox();
  }
}

function updateLightboxContent() {
  if (!filteredPhotos || filteredPhotos.length === 0) return;
  const photo = filteredPhotos[activeLightboxIndex];
  if (!photo) return;

  const previewUrl = `/api/asset-preview?id=${encodeURIComponent(photo.id)}&venueId=${encodeURIComponent(photo.venueId)}`;
  const downloadUrl = `/api/asset-download?id=${encodeURIComponent(photo.id)}&venueId=${encodeURIComponent(photo.venueId)}`;

  lightboxImage.src = previewUrl;
  lightboxRide.textContent = photo.ride || "Wonderla Ride";
  lightboxDate.textContent = `🕒 ${photo.captureDate}`;
  lightboxDim.textContent = `📐 ${photo.dimension || 'High Resolution'}`;
  lightboxSize.textContent = `💾 ${photo.sizeFormatted}`;

  lightboxDownloadLink.href = downloadUrl;
  lightboxDownloadLink.download = photo.filename;
}

function prevLightbox(e) {
  if (e) e.stopPropagation();
  if (activeLightboxIndex > 0) {
    activeLightboxIndex--;
  } else {
    activeLightboxIndex = filteredPhotos.length - 1;
  }
  updateLightboxContent();
}

function nextLightbox(e) {
  if (e) e.stopPropagation();
  if (activeLightboxIndex < filteredPhotos.length - 1) {
    activeLightboxIndex++;
  } else {
    activeLightboxIndex = 0;
  }
  updateLightboxContent();
}

// Downloads & ZIP
function downloadAllZip() {
  if (!currentPhotos || currentPhotos.length === 0) return;
  const allIds = currentPhotos.map(p => p.id);
  triggerZipDownload(allIds, `${currentAlbum.code}_All_Photos.zip`);
}

function downloadSelectedZip() {
  if (selectedAssetIds.size === 0) {
    showToast("No photos selected", "error");
    return;
  }
  const ids = Array.from(selectedAssetIds);
  triggerZipDownload(ids, `${currentAlbum.code}_Selected_Photos.zip`);
}

function triggerZipDownload(assetIds, zipName) {
  showToast(`Preparing ${assetIds.length} photos in ZIP...`, "info");
  const venueId = currentAlbum.venueId || "IN06";
  const idsParam = assetIds.join(",");
  const url = `/api/download-zip?venueId=${encodeURIComponent(venueId)}&ids=${encodeURIComponent(idsParam)}&code=${encodeURIComponent(currentAlbum.code)}`;
  
  // Create hidden link to initiate browser file download
  const a = document.createElement("a");
  a.href = url;
  a.download = zipName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

// Save Directly to Android Device Storage (/sdcard/Download)
async function saveToPhoneStorage() {
  if (!currentPhotos || currentPhotos.length === 0) return;

  const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
  if (!isLocal) {
    showToast("Direct local storage save is for Termux mode. Starting ZIP download for cloud deployment!", "info");
    downloadAllZip();
    return;
  }

  const targetPhotos = selectedAssetIds.size > 0 
    ? currentPhotos.filter(p => selectedAssetIds.has(p.id))
    : currentPhotos;

  try {
    const resp = await fetch("/api/save-local", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        assets: targetPhotos,
        venueId: currentAlbum.venueId || "IN06"
      })
    });

    const res = await resp.json();
    if (!resp.ok || (res.status !== "started" && res.status !== "busy")) {
      showToast(res.message || "Failed to start local save", "error");
      return;
    }

    openProgressModal(targetPhotos.length);
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
}

function openProgressModal(total) {
  progressModal.classList.add("active");
  progressBarFill.style.width = "0%";
  progressStatsText.textContent = `Downloading 0 of ${total} photos (0%)`;
  progressCurrentFile.textContent = "Connecting to storage...";
  progressCloseBtn.style.display = "none";

  if (savePollInterval) clearInterval(savePollInterval);

  savePollInterval = setInterval(async () => {
    try {
      const resp = await fetch("/api/save-progress");
      const status = await resp.json();

      const cur = status.current || 0;
      const tot = status.total || total;
      const pct = tot > 0 ? Math.round((cur / tot) * 100) : 0;

      progressBarFill.style.width = `${pct}%`;
      progressStatsText.textContent = `Downloading ${cur} of ${tot} photos (${pct}%)`;
      if (status.filename) {
        progressCurrentFile.textContent = `Current: ${status.filename}`;
      }

      if (!status.is_running && cur >= tot && tot > 0) {
        clearInterval(savePollInterval);
        progressBarFill.style.width = "100%";
        progressStatsText.textContent = `🎉 All ${tot} photos saved successfully!`;
        progressCurrentFile.textContent = `Folder: ${status.saved_path}`;
        progressCloseBtn.style.display = "inline-block";
        showToast("All photos saved to /sdcard/Download/Wonderla_Photos!", "success");
      } else if (status.error) {
        clearInterval(savePollInterval);
        progressStatsText.textContent = `⚠️ Error: ${status.error}`;
        progressCloseBtn.style.display = "inline-block";
      }
    } catch (e) {
      // Continue polling
    }
  }, 800);
}

function closeProgressModal() {
  if (savePollInterval) clearInterval(savePollInterval);
  progressModal.classList.remove("active");
}

// QR Code Scanner (Camera)
function openScanner() {
  scannerModal.classList.add("active");

  if (!html5QrCode) {
    html5QrCode = new Html5Qrcode("qr-reader");
  }

  const config = { fps: 10, qrbox: { width: 250, height: 250 } };

  html5QrCode.start(
    { facingMode: "environment" },
    config,
    (decodedText) => {
      // QR code scanned successfully
      closeScanner();
      handleScannedCode(decodedText);
    },
    (errorMessage) => {
      // scanning in progress
    }
  ).catch(err => {
    showToast(`Camera permission denied or camera not found: ${err}`, "error");
    closeScanner();
  });
}

function closeScanner() {
  if (html5QrCode && html5QrCode.isScanning) {
    html5QrCode.stop().then(() => {
      scannerModal.classList.remove("active");
    }).catch(() => {
      scannerModal.classList.remove("active");
    });
  } else {
    scannerModal.classList.remove("active");
  }
}

// QR Code Scanner (Image File Upload)
async function handleQrFileUpload(event) {
  const file = event.target.files[0];
  if (!file) return;

  if (!html5QrCode) {
    html5QrCode = new Html5Qrcode("qr-reader");
  }

  showToast("Scanning uploaded image for QR code...", "info");

  try {
    const decodedText = await html5QrCode.scanFile(file, true);
    handleScannedCode(decodedText);
  } catch (err) {
    showToast("No QR code found in uploaded image. Please try a clearer picture.", "error");
  } finally {
    event.target.value = "";
  }
}

function handleScannedCode(rawText) {
  // Extract Wonderla code from URL or raw text
  let code = rawText.trim();
  if (code.includes("?") || code.includes("://")) {
    try {
      const url = new URL(code);
      const codeParam = url.searchParams.get("code") || url.searchParams.get("c") || url.searchParams.get("claim");
      if (codeParam) {
        code = codeParam;
      } else {
        const parts = url.pathname.split("/").filter(Boolean);
        if (parts.length > 0) code = parts[parts.length - 1];
      }
    } catch (e) {
      // Fallback regex
      const match = code.match(/[?&]code=([A-Za-z0-9_\-]+)/);
      if (match) code = match[1];
    }
  }

  code = code.replace(/[^A-Za-z0-9_\-]/g, "").toUpperCase();
  claimInput.value = code;
  showToast(`QR Code detected: ${code}`, "success");
  performSearch(code);
}

// Toast Notifications
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;

  const icon = type === "success" ? "✅" : (type === "error" ? "❌" : "ℹ️");
  toast.innerHTML = `<span>${icon}</span> <span>${escapeHtml(message)}</span>`;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(100%)";
    setTimeout(() => {
      if (toast.parentNode) container.removeChild(toast);
    }, 300);
  }, 4000);
}

function escapeHtml(text) {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
