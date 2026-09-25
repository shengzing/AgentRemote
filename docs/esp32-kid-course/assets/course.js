const chapters = [
  { id: "01", title: "Mac 准备站", file: "01-mac-setup.html" },
  { id: "02", title: "Scratch 到硬件", file: "02-scratch-to-hardware.html" },
  { id: "03", title: "输入和输出", file: "03-input-output.html" },
  { id: "04", title: "传感器侦探", file: "04-sensor-detective.html" },
  { id: "05", title: "MicroPython 起步", file: "05-micropython-start.html" },
  { id: "06", title: "Wi-Fi 任务站", file: "06-wifi-task-station.html" },
  { id: "07", title: "综合项目", file: "07-family-reminder-project.html" },
  { id: "08", title: "展示与复盘", file: "08-show-and-review.html" },
];

const storageKey = "esp32-kid-course-progress";

function readProgress() {
  try {
    const raw = localStorage.getItem(storageKey);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch (error) {
    return new Set();
  }
}

function saveProgress(progress) {
  try {
    localStorage.setItem(storageKey, JSON.stringify([...progress]));
  } catch (error) {
    // Progress is optional; the tutorial still works without storage.
  }
}

function updateProgressUI() {
  const progress = readProgress();
  const fill = document.querySelector("[data-progress-fill]");
  const label = document.querySelector("[data-progress-label]");
  if (!fill || !label) return;

  const percent = Math.round((progress.size / chapters.length) * 100);
  fill.style.width = `${percent}%`;
  label.textContent = `${progress.size}/${chapters.length}`;

  document.querySelectorAll("[data-chapter-checkbox]").forEach((input) => {
    input.checked = progress.has(input.dataset.chapterCheckbox);
  });
}

function setupProgress() {
  document.querySelectorAll("[data-chapter-checkbox]").forEach((input) => {
    input.addEventListener("change", () => {
      const progress = readProgress();
      const id = input.dataset.chapterCheckbox;
      if (input.checked) {
        progress.add(id);
      } else {
        progress.delete(id);
      }
      saveProgress(progress);
      updateProgressUI();
      if (input.checked) showToast("太棒了，这一章完成。");
    });
  });
  updateProgressUI();
}

function showToast(message) {
  let toast = document.querySelector(".toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.className = "toast";
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 1800);
}

function setupReveal() {
  const targets = document.querySelectorAll(".reveal, .stagger");
  if (!targets.length) return;

  if (!("IntersectionObserver" in window)) {
    targets.forEach((target) => target.classList.add("visible"));
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("visible");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.12 },
  );

  targets.forEach((target) => observer.observe(target));
}

function setupTaskDemo() {
  const demo = document.querySelector("[data-task-demo]");
  if (!demo) return;

  const message = demo.querySelector("[data-device-message]");
  const title = demo.querySelector("[data-device-title]");
  const status = demo.querySelector("[data-device-status]");
  const taskInputs = demo.querySelectorAll("input[name='task']");
  const sendButton = demo.querySelector("[data-send-task]");
  const confirmButton = demo.querySelector("[data-confirm-task]");

  let currentTask = "喝水";
  let needsConfirm = false;

  function render() {
    title.textContent = needsConfirm ? "新任务来了" : "家庭小助手";
    message.textContent = needsConfirm ? currentTask : "现在没有新任务";
    status.textContent = needsConfirm ? "等待按主键确认" : "已确认，继续加油";
    status.parentElement.classList.toggle("waiting", needsConfirm);
    confirmButton.disabled = !needsConfirm;
  }

  taskInputs.forEach((input) => {
    input.addEventListener("change", () => {
      currentTask = input.value;
    });
  });

  sendButton.addEventListener("click", () => {
    needsConfirm = true;
    render();
    showToast("任务已经发送到设备。");
  });

  confirmButton.addEventListener("click", () => {
    needsConfirm = false;
    render();
    showToast("任务已确认。");
  });

  render();
}

document.addEventListener("DOMContentLoaded", () => {
  setupProgress();
  setupReveal();
  setupTaskDemo();
});

