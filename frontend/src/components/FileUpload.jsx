const BASE = "http://127.0.0.1:5000";

function sanitizeJSON(text) {
  // Remplace NaN, Infinity, -Infinity par null avant parsing
  return text
    .replace(/:\s*NaN/g, ': null')
    .replace(/:\s*Infinity/g, ': null')
    .replace(/:\s*-Infinity/g, ': null');
}

export async function sendMessage(message, fileContext = null) {
  const res = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: fileContext ? `${fileContext}\n\nQuestion: ${message}` : message,
    }),
  });

  const rawText = await res.text();
  let data;
  try {
    data = JSON.parse(sanitizeJSON(rawText));
  } catch (e) {
    throw new Error("Réponse invalide du serveur. Veuillez réessayer.");
  }

  if (!res.ok) {
    throw new Error(data.answer || data.error || `Erreur serveur ${res.status}`);
  }

  return data;
}

export async function uploadPDF(file) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${BASE}/upload-pdf`, { method: "POST", body: fd });
  if (!res.ok) throw new Error("Erreur upload PDF");
  const rawText = await res.text();
  return JSON.parse(sanitizeJSON(rawText));
}

export async function resetMemory() {
  await fetch(`${BASE}/reset`, { method: "POST" });
}

export async function uploadFile(file) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${BASE}/upload-file`, {
    method: "POST",
    body: fd,
    credentials: "include",
  });
  const rawText = await res.text();
  return JSON.parse(sanitizeJSON(rawText));
}