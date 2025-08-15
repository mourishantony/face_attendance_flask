// Simple camera capture and POST to /api/recognize
const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const snapBtn = document.getElementById('snapBtn');
const startBtn = document.getElementById('startBtn');
const result = document.getElementById('result');

async function startCamera() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
    video.srcObject = stream;
  } catch (e) {
    result.innerHTML = `<div class="alert alert-danger">Camera error: ${e}</div>`;
  }
}

startBtn?.addEventListener('click', startCamera);

snapBtn?.addEventListener('click', async () => {
  const w = video.videoWidth;
  const h = video.videoHeight;
  if (!w || !h) {
    result.innerHTML = `<div class="alert alert-warning">Start the camera first.</div>`;
    return;
  }
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, w, h);
  const dataUrl = canvas.toDataURL('image/jpeg', 0.9);

  result.innerHTML = `<div class="alert alert-info">Scanning...</div>`;
  try {
    const res = await fetch('/api/recognize', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ image_b64: dataUrl })
    });
    const j = await res.json();
    if (!j.ok) {
      result.innerHTML = `<div class="alert alert-danger">Error: ${j.error || 'Unknown'}</div>`;
      return;
    }
    if (!j.match) {
      result.innerHTML = `<div class="alert alert-warning">No match found. Please try again.</div>`;
      return;
    }
    const { name, role, class_name } = j.match;
    const within = j.within_window;
    const msg = within ? 'Marked PRESENT' : 'Scanned outside attendance window';
    result.innerHTML = `<div class="alert alert-success"><b>${name}</b> (${role}${class_name ? ', ' + class_name : ''}) — ${msg}</div>`;
  } catch (e) {
    result.innerHTML = `<div class="alert alert-danger">Request failed: ${e}</div>`;
  }
});
