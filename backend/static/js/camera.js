function initPhotoCapture(blockId) {
  const galleryInput = document.getElementById(`gallery-input-${blockId}`);
  const cameraBtn = document.getElementById(`camera-btn-${blockId}`);
  const fallbackInput = document.getElementById(`camera-fallback-input-${blockId}`);
  const preview = document.getElementById(`preview-${blockId}`);
  const hiddenFormInput = document.getElementById(`file-input-${blockId}`);
  const submitBtn = document.getElementById(`submit-${blockId}`);

  function acceptFile(file) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      preview.src = e.target.result;
      preview.style.display = "block";
    };
    reader.readAsDataURL(file);

    const dt = new DataTransfer();
    dt.items.add(file);
    hiddenFormInput.files = dt.files;
    if (submitBtn) submitBtn.disabled = false;
  }

  if (galleryInput) galleryInput.onchange = (e) => acceptFile(e.target.files[0]);
  if (fallbackInput) fallbackInput.onchange = (e) => acceptFile(e.target.files[0]);

  if (cameraBtn) {
    cameraBtn.onclick = () => {
      if (!window.isSecureContext) {
        if (fallbackInput) {
          fallbackInput.click();
        } else {
          alert("Camera needs HTTPS on a mobile device. Please use Gallery.");
        }
        return;
      }
      openLiveCamera(acceptFile);
    };
  }
}

let currentStream = null;

function openLiveCamera(onCapture) {
  const modal = document.getElementById("camera-modal");
  const video = document.getElementById("camera-video");
  const canvas = document.getElementById("camera-canvas");
  const captureBtn = document.getElementById("camera-capture-btn");
  const switchBtn = document.getElementById("camera-switch-btn");
  const closeBtn = document.getElementById("camera-close-btn");

  modal.style.display = "flex";
  let facingMode = "environment"; // Default back camera

  async function startStream() {
    if (currentStream) {
      currentStream.getTracks().forEach(track => track.stop());
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      alert("Live camera is not available here. Please use Gallery.");
      modal.style.display = "none";
      return;
    }
    try {
      try {
        currentStream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { exact: facingMode } },
          audio: false
        });
      } catch (exactError) {
        // Some laptops expose only one camera or do not support exact constraints.
        currentStream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: facingMode } },
          audio: false
        });
      }
      video.srcObject = currentStream;
      await video.play();
    } catch (err) {
      console.error("Camera Error: ", err);
      alert("Camera access denied or not available.");
      modal.style.display = "none";
    }
  }

  startStream();

  // Flip Camera logic
  if (switchBtn) {
    switchBtn.onclick = () => {
      facingMode = facingMode === "user" ? "environment" : "user";
      startStream();
    };
  }

  // Capture Photo
  captureBtn.onclick = () => {
    if (!video.videoWidth || !video.videoHeight) {
      alert("Camera is still starting. Please try again in a moment.");
      return;
    }
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      const file = new File([blob], "capture.jpg", { type: "image/jpeg" });
      onCapture(file);
      closeCamera();
    }, "image/jpeg", 0.9);
  };

  // Cancel/Close logic (Fix)
  function closeCamera() {
    if (currentStream) {
      currentStream.getTracks().forEach(track => track.stop());
      currentStream = null;
    }
    video.srcObject = null;
    modal.style.display = "none";
  }

  closeBtn.onclick = closeCamera;
}