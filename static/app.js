async function loadRenders() {
  const res  = await fetch("/api/images/renders");
  const data = await res.json();
  const grid = document.getElementById("renders-grid");
  data.renders.forEach(r => {
    const img = document.createElement("img");
    img.src   = r.image;
    img.title = r.name;
    grid.appendChild(img);
  });
}

window.handleRender = async function () {
  const btn    = document.getElementById("btn-render");
  const status = document.getElementById("status-msg");

  btn.disabled    = true;
  btn.textContent = "Extracting specs...";
  status.textContent = "Extracting geometry · finishes · brand specs from documents...";

  document.getElementById("section-result").classList.add("hidden");
  document.getElementById("spec-preview").classList.add("hidden");

  try {
    btn.textContent    = "Generating...";
    status.textContent = "Uploading floor plan · submitting to NanoBanana · this may take 30–60s...";

    const res  = await fetch("/api/render", { method: "POST" });
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    document.getElementById("result-img").src = data.image;
    document.getElementById("section-result").classList.remove("hidden");

    if (data.specs) {
      document.getElementById("spec-geometry").textContent = JSON.stringify(data.specs.geometry, null, 2);
      document.getElementById("spec-finishes").textContent = JSON.stringify(data.specs.finishes, null, 2);
      document.getElementById("spec-brand").textContent    = JSON.stringify(data.specs.brand,    null, 2);
      document.getElementById("spec-preview").classList.remove("hidden");
    }

    status.textContent = "Render complete.";

  } catch (err) {
    status.textContent = "Error: " + err.message;
  } finally {
    btn.disabled    = false;
    btn.textContent = "Generate 3D Render";
  }
};

window.switchSpec = function (name) {
  document.querySelectorAll(".spec-tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".spec-content").forEach(t => t.classList.add("hidden"));
  document.querySelector(`.spec-tab[onclick="switchSpec('${name}')"]`).classList.add("active");
  document.getElementById("spec-" + name).classList.remove("hidden");
};

loadRenders();
