//const API_BASE_URL = "http://localhost:8080";
const API_BASE_URL = `${window.location.protocol}//${window.location.host}`;
console.log(API_BASE_URL)
let bibInfo = null;
let thumbs = [];
let cropper = null; // Initialize cropper as null explicitly

function showTab(index) {
    document.querySelectorAll(".tab-content").forEach((el, i) => {
        el.style.display = i === index ? "block" : "none";
    });
    document.querySelectorAll(".tabs button").forEach((btn, i) => {
        btn.classList.toggle("active", i === index);
    });
}

async function submitCode() {
    const code = document.getElementById("invite-code").value;
    const recaptchaResponse = window.grecaptcha ? grecaptcha.getResponse() : '';
    if (!window.__CF$cv$params && !recaptchaResponse) {
        Swal.fire({
            title: "CAPTCHA Required",
            text: "Please complete the CAPTCHA to proceed.",
            icon: "warning",
            confirmButtonText: "OK"
        });
        return;
    }

    const response = await fetch(`${API_BASE_URL}/bib`, {
        method: "POST",
        headers: { 
            "Content-Type": "application/json",
            ...(recaptchaResponse && { "X-Recaptcha-Token": recaptchaResponse })
        },
        body: JSON.stringify({ code })
    });
    const data = await response.json();
    
    const infoDiv = document.getElementById("bib-info");
    if (data.error) {
        infoDiv.innerHTML = `<p style="color: red;">${data.error}</p>`;
        bibInfo = null;
    } else {
        bibInfo = data;
        infoDiv.innerHTML = `
            <p>BIB: ${bibInfo.bib}</p>
            ${bibInfo.name ? `<p>Name: ${bibInfo.name}</p>` : ""}
            <p class="${new Date(bibInfo.bib_expiry) < new Date() ? 'expired' : 'valid'}">
                Bib Expiry: ${bibInfo.bib_expiry} ${new Date(bibInfo.bib_expiry) < new Date() ? "(Expired)" : ""}
            </p>
            <p>Event: ${bibInfo.event_name}</p>
            <p class="${new Date(bibInfo.event_expiry) < new Date() ? 'expired' : 'valid'}">
                Event Expiry: ${bibInfo.event_expiry} ${new Date(bibInfo.event_expiry) < new Date() ? "(Expired)" : ""}
            </p>
        `;
        document.getElementById("tab1").disabled = false;
        showTab(1);
        document.getElementById("bib-display").textContent = `BIB: ${bibInfo.bib} ${bibInfo.name || ""} (Event: ${bibInfo.event_name})`;
    }
}

function updateCheckboxState() {
    for (let i = 0; i < 3; i++) {
        const faceBox = document.getElementById(`face-${i}`);
        const useCheckbox = document.getElementById(`use-${i}`);
        const hasImage = faceBox.querySelector("img") !== null;
        useCheckbox.disabled = !hasImage;
        if (!hasImage) {
            useCheckbox.checked = false;
        }
    }
}

function loadImage() {
    const fileInput = document.getElementById("image-input");
    const file = fileInput.files[0];
    const img = document.getElementById("crop-image");
    
    if (file) {
        img.src = URL.createObjectURL(file);
        img.style.display = "block";
        if (cropper) {
            cropper.destroy();
            cropper = null; // Ensure old cropper is fully cleared
        }
        
        cropper = new Cropper(img, {
            aspectRatio: 358 / 441,
            viewMode: 1,
            autoCropArea: 0.8,
            movable: true,
            zoomable: true,
        });
        
        // Assign onclick handlers after cropper creation
        document.getElementById("copy-0").onclick = () => copyToFace(0);
        document.getElementById("copy-1").onclick = () => copyToFace(1);
        document.getElementById("copy-2").onclick = () => copyToFace(2);
    }
    
    // Enable/disable Paste buttons based on cropper existence
    const hasCropper = !!cropper;
    document.querySelectorAll(".copy-btn").forEach(btn => {
        btn.disabled = !hasCropper;
    });
    
    // Reset file input
    fileInput.value = "";
    
    updateCheckboxState();
}

function copyToFace(index) {
    if (cropper) {
        const canvas = cropper.getCroppedCanvas({ width: 358, height: 441 });
        const quality = 0.7;
        let imgData = canvas.toDataURL('image/jpeg', quality);
        let blob = dataURLtoBlob(imgData);
        
        while (blob.size > 260 * 1024 && quality > 0.1) {
            imgData = canvas.toDataURL('image/jpeg', quality - 0.1);
            blob = dataURLtoBlob(imgData);
        }

        const imgEl = document.createElement("img");
        imgEl.src = imgData;
        const faceBox = document.getElementById(`face-${index}`);
        faceBox.innerHTML = "";
        faceBox.appendChild(imgEl);
        
        // Set the corresponding "Use" checkbox to true
        const useCheckbox = document.getElementById(`use-${index}`);
        useCheckbox.checked = true;
        
        cropper.destroy();
        cropper = null;
        const img = document.getElementById("crop-image");
        img.src = "";
        img.style.display = "none";
        
        // Disable Paste buttons after pasting
        document.querySelectorAll(".copy-btn").forEach(btn => btn.disabled = true);
        
        updateCheckboxState();
    } else {
        console.error("No active cropper instance to paste from.");
    }
}

function dataURLtoBlob(dataURL) {
    const arr = dataURL.split(',');
    const mime = arr[0].match(/:(.*?);/)[1];
    const bstr = atob(arr[1]);
    let n = bstr.length;
    const u8arr = new Uint8Array(n);
    while (n--) {
        u8arr[n] = bstr.charCodeAt(n);
    }
    return new Blob([u8arr], { type: mime });
}

async function submitFaces() {
    const images = Array.from(document.querySelectorAll(".face-box img"))
        .map((img, index) => ({
            src: img.src,
            use: document.getElementById(`use-${index}`).checked
        }))
        .filter(item => item.use)
        .map(item => item.src);
    
    if (images.length === 0) {
        const { value: action } = await Swal.fire({
            title: "No faces selected",
            html: "Press <b>Continue</b> to search photos<br>Press <b>Add Face</b> to add or use face image",
            icon: "warning",
            showCancelButton: true,
            confirmButtonText: "Continue",
            cancelButtonText: "Add Face",
            reverseButtons: true,
            focusConfirm: false,
            customClass: {
                confirmButton: "swal2-confirm",
                cancelButton: "swal2-cancel"
            }
        });

        if (action === undefined || action === "Add") {
            return;
        }
    }
    
    const response = await fetch(`${API_BASE_URL}/thumb`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ images, code: bibInfo.code })
    });
    const data = await response.json();
    
    if (data.error) {
        await Swal.fire({
            title: "Error",
            text: data.error,
            icon: "error",
            confirmButtonText: "OK"
        });
        return;
    }
    
    thumbs = data;
    document.getElementById("tab2").disabled = false;
    showTab(2);
    displayThumbs();

    const submitButton = document.getElementById("submit-faces");
    submitButton.disabled = true;
    const disableDuration = 60000;
    let remainingTime = disableDuration / 1000;

    const updateCountdown = () => {
        submitButton.textContent = `Submit (${remainingTime})`;
        remainingTime--;
        if (remainingTime < 0) {
            clearInterval(countdownInterval);
            submitButton.textContent = "Submit";
            submitButton.disabled = false;
        }
    };
    updateCountdown();
    const countdownInterval = setInterval(updateCountdown, 1000);
}

function displayThumbs() {
    const grid = document.getElementById("thumbs-grid");
    const controlsTop = document.getElementById("thumbnail-controls-top");
    const controlsBottom = document.getElementById("thumbnail-controls-bottom");
    const totalPhotos = document.getElementById("total-photos");
    const noPhotosMessage = document.getElementById("no-photos-message");
    grid.innerHTML = "";
    
    if (thumbs.thumbs.length === 0) {
        noPhotosMessage.style.display = "block";
        totalPhotos.textContent = "No photos found for the bib and face uploaded.";
        controlsTop.style.display = "none";
        controlsBottom.style.display = "none";
    } else {
        noPhotosMessage.style.display = "none";
        totalPhotos.textContent = `Total photos found: ${thumbs.thumbs.length}`;
        thumbs.thumbs.forEach(thumb => {
            const div = document.createElement("div");
            div.style.position = "relative";
            const img = document.createElement("img");
            img.src = `${thumbs["main-url"]}${thumb}`;
            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.value = thumb;
            checkbox.checked = true;
            div.appendChild(img);
            div.appendChild(checkbox);
            grid.appendChild(div);
        });
        controlsTop.style.display = "block";
        controlsBottom.style.display = "block";
    }
}

function selectAll() {
    document.querySelectorAll("#thumbs-grid input").forEach(cb => cb.checked = true);
}

function selectNone() {
    document.querySelectorAll("#thumbs-grid input").forEach(cb => cb.checked = false);
}

function selectInverse() {
    document.querySelectorAll("#thumbs-grid input").forEach(cb => cb.checked = !cb.checked);
}

async function download() {
    const selected = Array.from(document.querySelectorAll("#thumbs-grid input:checked")).map(cb => cb.value);

    if (selected.length === 0) {
        await Swal.fire({
            title: "No images selected",
            text: "Please select at least one image to download.",
            icon: "warning",
            confirmButtonText: "OK"
        });
        return;
    }

    const { isConfirmed } = await Swal.fire({
        title: "Confirm Download",
        text: `You have selected ${selected.length} thumbnail(s). Do you want to proceed with the download?`,
        icon: "question",
        showCancelButton: true,
        confirmButtonText: "Yes",
        cancelButtonText: "No",
        reverseButtons: true
    });

    if (!isConfirmed) {
        return;
    }

    const loadingSwal = Swal.fire({
        title: "Processing",
        text: "Preparing your download, please wait...",
        allowOutsideClick: false,
        didOpen: () => {
            Swal.showLoading();
        }
    });

    try {
        const response = await fetch(`${API_BASE_URL}/download`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ thumbs: selected, code: bibInfo.code })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || "Failed to download files.");
        }

        await loadingSwal.close();
        const downloadSwal = Swal.fire({
            title: "Download Started",
            text: "Your download has started. Please wait until it completes.",
            icon: "info",
            allowOutsideClick: false,
            didOpen: () => {
                Swal.showLoading();
            }
        });

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "photo.zip";
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);

        await downloadSwal.close();
    } catch (error) {
        await loadingSwal.close();
        await Swal.fire({
            title: "Download Error",
            text: error.message,
            icon: "error",
            confirmButtonText: "OK"
        });
    }
}

window.onload = () => {
    updateCheckboxState();
    if (!window.__CF$cv$params && window.grecaptcha) {
        grecaptcha.render("recaptcha-container", {
            "sitekey": "6LduOvsqAAAAAFq70zQvjSds5g16UclT-JkEVqak"
        });
    }
};
