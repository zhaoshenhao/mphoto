const API_BASE_URL = "http://localhost:8000";
let bibInfo = null;
let thumbs = [];
let cropper;

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
    const response = await fetch(`${API_BASE_URL}/bib`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
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
    const file = document.getElementById("image-input").files[0];
    if (file) {
        const img = document.getElementById("crop-image");
        img.src = URL.createObjectURL(file);
        img.style.display = "block";
        if (cropper) cropper.destroy();
        
        cropper = new Cropper(img, {
            aspectRatio: 358 / 441,
            viewMode: 1,
            autoCropArea: 0.8,
            movable: true,
            zoomable: true,
        });
        
        document.querySelectorAll(".copy-btn").forEach(btn => btn.disabled = false);
        
        document.getElementById("copy-0").onclick = () => copyToFace(0);
        document.getElementById("copy-1").onclick = () => copyToFace(1);
        document.getElementById("copy-2").onclick = () => copyToFace(2);
    } else {
        document.querySelectorAll(".copy-btn").forEach(btn => btn.disabled = true);
    }
    updateCheckboxState();
}

function copyToFace(index) {
    if (cropper) {
        const canvas = cropper.getCroppedCanvas({ width: 358, height: 441 });
        const imgEl = document.createElement("img");
        imgEl.src = canvas.toDataURL();
        const faceBox = document.getElementById(`face-${index}`);
        faceBox.innerHTML = "";
        faceBox.appendChild(imgEl);
        
        cropper.destroy();
        const img = document.getElementById("crop-image");
        img.src = "";
        img.style.display = "none";
        document.querySelectorAll(".copy-btn").forEach(btn => btn.disabled = true);
        
        updateCheckboxState();
    }
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
            html: "Press <b>Continue</b> to search photos<br>Press <b>Add</b> to add or use face image",
            icon: "warning",
            showCancelButton: true,
            confirmButtonText: "Continue",
            cancelButtonText: "Add",
            reverseButtons: true,
            focusConfirm: false,
            customClass: {
                confirmButton: "swal2-confirm",
                cancelButton: "swal2-cancel"
            }
        });

        if (action === undefined || action === "Add") {
            return; // 如果选择 "Add" 或关闭对话框，停留在当前页面
        }
        // 如果选择 "Continue"，继续提交空列表
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
    document.getElementById("submit-faces").disabled = true;
    setTimeout(() => document.getElementById("submit-faces").disabled = false, 60000);
}

function displayThumbs() {
    const grid = document.getElementById("thumbs-grid");
    grid.innerHTML = "";
    thumbs.thumbs.forEach(thumb => {
        const div = document.createElement("div");
        div.style.position = "relative";
        const img = document.createElement("img");
        img.src = `${thumbs["main-url"]}${thumb}`;
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.value = thumb;
        div.appendChild(img);
        div.appendChild(checkbox);
        grid.appendChild(div);
    });
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

    // 情况 1：没有选择任何缩略图
    if (selected.length === 0) {
        await Swal.fire({
            title: "No images selected",
            text: "Please select at least one image to download.",
            icon: "warning",
            confirmButtonText: "OK"
        });
        return; // 用户确认后不提交
    }

    // 情况 2：有选择的缩略图，显示总数并让用户确认
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
        return; // 用户取消，不提交
    }

    // 情况 3：提交后显示 Loading Indicator
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

        // 下载开始前关闭 Loading Indicator，提示下载开始
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

        // 获取文件流并转换为 Blob
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);

        // 创建临时链接并触发下载
        const link = document.createElement("a");
        link.href = url;
        link.download = "photo.zip";
        document.body.appendChild(link);
        link.click();

        // 清理临时链接
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);

        // 下载完成后关闭提示窗口
        await downloadSwal.close();
    } catch (error) {
        // 出错时关闭 Loading Indicator 并显示错误
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
};
