import { useState, useRef, useEffect } from "react";
import Papa from "papaparse";
import jsPDF from "jspdf";
import ExcelJS from "exceljs";
import * as XLSX from "xlsx";
import ChartBlock from "./components/ChartBlock";      
import { sendMessage as apiSend, uploadPDF } from "./api/chat"; 

// ════════════════════════════════════════════════════════
//  AUTH  (inchangé)
// ════════════════════════════════════════════════════════
const USERS_KEY = "dataolist_users";
const SESSION_KEY = "dataolist_auth";
function getUsers() {
  try {
    const u = JSON.parse(localStorage.getItem(USERS_KEY) || "[]");
    if (!u.find(x => x.username === "admin"))
      u.push({ username: "admin", password: "admin123", email: "admin@olist.com" });
    localStorage.setItem(USERS_KEY, JSON.stringify(u));
    return u;
  } catch { return []; }
}
function loginUser(username, password) {
  const user = getUsers().find(u => u.username === username && u.password === password);
  if (!user) return { ok: false, error: "Identifiants incorrects." };
  const s = { username: user.username, email: user.email, loginAt: Date.now() };
  localStorage.setItem(SESSION_KEY, JSON.stringify(s));
  return { ok: true, session: s };
}
function registerUser(username, email, password) {
  const users = getUsers();
  if (users.find(u => u.username === username || u.email === email))
    return { ok: false, error: "Nom d'utilisateur ou email déjà utilisé." };
  users.push({ username, email, password });
  localStorage.setItem(USERS_KEY, JSON.stringify(users));
  return { ok: true };
}
function getSession()  { try { return JSON.parse(localStorage.getItem(SESSION_KEY)); } catch { return null; } }
function clearSession(){ localStorage.removeItem(SESSION_KEY); }

// ════════════════════════════════════════════════════════
//  HELPERS  (inchangé)
// ════════════════════════════════════════════════════════
const fmtTime = d => new Date(d).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
const fmtDate = d => {
  const now = new Date(), dt = new Date(d);
  if (dt.toDateString() === now.toDateString()) return "Aujourd'hui";
  const y = new Date(now); y.setDate(now.getDate() - 1);
  if (dt.toDateString() === y.toDateString()) return "Hier";
  return dt.toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
};
const WELCOME = { role:"assistant", content:"Bonjour 👋 Je suis **DataOlist AI**.\nPosez une question ou envoyez un fichier (PDF, Excel, CSV) pour l'analyser.", time:Date.now() };
const SUGGESTIONS = ["Montre l'évolution des ventes par mois 📈","Top 5 vendeurs par revenu 🏆","Répartition des modes de paiement 💳","Délai moyen de livraison par état 🗺️"];
const STORAGE_KEY = "dataolist_sessions";
const loadSessions  = () => { try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"); } catch { return []; } };
const saveSessions  = s => localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
const newSession    = (msgs = [{ ...WELCOME, time: Date.now() }]) => ({ id: Date.now().toString(), title: "Nouvelle conversation", date: Date.now(), messages: msgs });

// ════════════════════════════════════════════════════════
//  FILE  (inchangé)
// ════════════════════════════════════════════════════════
const readText   = f => new Promise((res, rej) => { const r = new FileReader(); r.onload = e => res(e.target.result); r.onerror = rej; r.readAsText(f); });
const readBase64 = f => new Promise((res, rej) => { const r = new FileReader(); r.onload = e => res(e.target.result.split(",")[1]); r.onerror = rej; r.readAsDataURL(f); });
async function extractFileContent(file) {
  const ext = file.name.split(".").pop().toLowerCase();
  if (ext === "csv") { const text = await readText(file); const p = Papa.parse(text, { header:true, skipEmptyLines:true }); return `[CSV: ${file.name}]\nColonnes: ${p.meta.fields?.join(", ")}\nLignes: ${p.data.length}\nAperçu:\n${JSON.stringify(p.data.slice(0,30),null,2)}`; }
  if (ext === "xlsx" || ext === "xls") { const wb = XLSX.read(await file.arrayBuffer(), { type:"array" }); const data = XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]], { defval:"" }); return `[Excel: ${file.name}]\nColonnes: ${Object.keys(data[0]||{}).join(", ")}\nLignes: ${data.length}\nAperçu:\n${JSON.stringify(data.slice(0,30),null,2)}`; }
  await readBase64(file); return `[PDF: ${file.name}, ${Math.round(file.size/1024)}KB]`;
}

// ════════════════════════════════════════════════════════
//  EXPORT  (inchangé)
// ════════════════════════════════════════════════════════
// ── Détection type d'export ──────────────────────────────────────────────────
// ── Détection type d'export ──────────────────────────────────────────────────
const detectExport = t => {
  const l = t.toLowerCase();
  if (l.includes("excel") || l.includes("xlsx")) return "excel";
  if (l.includes("csv"))                          return "csv";
  if (l.includes("pdf") || l.includes("rapport")) return "pdf";
  return null;
};

// ── NOUVEAU : nettoyage de la question avant envoi au SQL agent ─────────────
const EXPORT_NOISE_WORDS = [
  "génère moi", "génère", "generer", "générer", "generate",
  "csv", "excel", "xlsx", "pdf",
  "exporte", "exporter", "export",
  "télécharge", "telecharge", "download"
  // ⚠️ "fichier" et "rapport" retirés : trop génériques, peuvent faire partie d'une vraie question
];

function cleanExportQuery(q) {
  let cleaned = q;
  EXPORT_NOISE_WORDS.forEach(w => {
    cleaned = cleaned.replace(new RegExp(`\\b${w}\\b`, "gi"), "");
  });
  cleaned = cleaned.replace(/\s+/g, " ").trim();

  // Si après nettoyage il ne reste presque rien → demande générique par défaut
  if (cleaned.length < 5) {
    return "liste détaillée de toutes les commandes";
  }
  if (!/^(montre|affiche|liste|top|combien|quel|donne|exporte)/i.test(cleaned)) {
    cleaned = "liste " + cleaned;
  }
  return cleaned;
}
// ── Nettoyage données avant export ──────────────────────────────────────────
function sanitizeRows(rows) {
  if (!Array.isArray(rows)) return [{ value: String(rows ?? "") }];
  return rows.map(row => {
    if (typeof row !== "object" || row === null) return { value: String(row) };
    const clean = {};
    for (const [k, v] of Object.entries(row)) {
      if (v === null || v === undefined || (typeof v === "number" && !isFinite(v))) {
        clean[k] = "";
      } else {
        clean[k] = v;
      }
    }
    return clean;
  });
}

// ── CSV ──────────────────────────────────────────────────────────────────────
function exportCSV(data, filename) {
  if (!data) return;
  const rows = sanitizeRows(Array.isArray(data) ? data : [{ value: data }]);
  const csv  = Papa.unparse(rows);
  const a    = document.createElement("a");
  a.href     = URL.createObjectURL(new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" }));
  a.download = filename.endsWith(".csv") ? filename : filename + ".csv";
  a.click();
}

// ── Excel ────────────────────────────────────────────────────────────────────
async function exportExcel(data, filename) {
  if (!data) return;
  const rows     = sanitizeRows(Array.isArray(data) ? data : [{ value: data }]);
  const workbook = new ExcelJS.Workbook();
  const sheet    = workbook.addWorksheet("Data");
  const keys     = rows.length ? Object.keys(rows[0]) : ["value"];
  sheet.columns  = keys.map(k => ({ header: k, key: k, width: 22 }));
  // Style en-tête
  sheet.getRow(1).eachCell(cell => {
    cell.font      = { bold: true, color: { argb: "FFFFFFFF" } };
    cell.fill      = { type: "pattern", pattern: "solid", fgColor: { argb: "FF111110" } };
    cell.alignment = { vertical: "middle", horizontal: "center" };
  });
  rows.forEach(row => sheet.addRow(row));
  const buffer = await workbook.xlsx.writeBuffer();
  const a      = document.createElement("a");
  a.href       = URL.createObjectURL(new Blob([buffer], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
  }));
  a.download = filename.endsWith(".xlsx") ? filename : filename + ".xlsx";
  a.click();
}

// ── PDF ──────────────────────────────────────────────────────────────────────
function exportPDF(data, filename) {
  const doc = new jsPDF();
  const pageW = doc.internal.pageSize.getWidth();
  const margin = 14;
  let y = 20;

  // Titre
  doc.setFontSize(14);
  doc.setFont("helvetica", "bold");
  doc.text("DataOlist AI — Rapport", margin, y);
  y += 8;

  // Date
  doc.setFontSize(9);
  doc.setFont("helvetica", "normal");
  doc.setTextColor(130, 130, 130);
  doc.text(new Date().toLocaleString("fr-FR"), margin, y);
  y += 10;
  doc.setTextColor(0, 0, 0);

  // Contenu : tableau ou texte
  const rows = Array.isArray(data) && data.length > 0 && typeof data[0] === "object"
    ? sanitizeRows(data)
    : null;

  if (rows) {
    // ── Mode tableau ──
    const headers = Object.keys(rows[0]);
    const colW    = Math.min((pageW - margin * 2) / headers.length, 45);

    // En-têtes
    doc.setFillColor(17, 17, 16);
    doc.setTextColor(255, 255, 255);
    doc.setFontSize(8);
    doc.setFont("helvetica", "bold");
    headers.forEach((h, i) => {
      doc.rect(margin + i * colW, y, colW, 8, "F");
      doc.text(String(h).slice(0, 18), margin + i * colW + 2, y + 5.5);
    });
    y += 8;

    // Lignes
    doc.setFont("helvetica", "normal");
    doc.setFontSize(7.5);
    rows.forEach((row, ri) => {
      if (y > 275) { doc.addPage(); y = 15; }
      const fill = ri % 2 === 0 ? [245, 244, 241] : [255, 255, 255];
      doc.setFillColor(...fill);
      doc.setTextColor(17, 17, 16);
      headers.forEach((h, i) => {
        doc.rect(margin + i * colW, y, colW, 7, "F");
        doc.text(String(row[h] ?? "").slice(0, 20), margin + i * colW + 2, y + 4.8);
      });
      y += 7;
    });
  } else {
    // ── Mode texte ──
    const text  = typeof data === "string" ? data : JSON.stringify(data, null, 2);
    doc.setFontSize(10);
    doc.setFont("helvetica", "normal");
    doc.setTextColor(17, 17, 16);
    const lines = doc.splitTextToSize(text, pageW - margin * 2);
    lines.forEach(line => {
      if (y > 280) { doc.addPage(); y = 15; }
      doc.text(line, margin, y);
      y += 6;
    });
  }

  doc.save(filename.endsWith(".pdf") ? filename : filename + ".pdf");
}
const parseTable = answer => {
  const lines = answer.split("\n").filter(l => l.includes("|"));
  if (lines.length < 2) return null;
  try {
    const headers = lines[0].split("|").map(h => h.trim()).filter(Boolean);
    const rows    = lines.slice(2).map(l => { const c = l.split("|").map(x => x.trim()).filter(Boolean); return headers.reduce((o, h, i) => { o[h] = c[i] || ""; return o; }, {}); });
    return rows.length ? rows : null;
  } catch { return null; }
};

// ════════════════════════════════════════════════════════
//  ICONS  (inchangé)
// ════════════════════════════════════════════════════════
const Ic = ({ d, size=20, stroke="currentColor", fill="none" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={fill} stroke={stroke} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round"><path d={d}/></svg>
);
const IC = {
  new:     "M12 5v14M5 12h14",
  history: "M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z",
  search:  "M21 21l-4.35-4.35M17 11A6 6 0 115 11a6 6 0 0112 0z",
  star:    "M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z",
  cog:     "M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z",
  send:    "M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z",
  trash:   "M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6",
  edit:    "M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z",
  close:   "M18 6L6 18M6 6l12 12",
  attach:  "M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48",
  file:    "M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8zM14 2v6h6",
  logout:  "M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1",
  eye:     "M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8zM12 9a3 3 0 100 6 3 3 0 000-6z",
  eyeoff:  "M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24M1 1l22 22",
};

// ════════════════════════════════════════════════════════
//  ROOT  (inchangé)
// ════════════════════════════════════════════════════════
export default function App() {
  const [session, setSession] = useState(() => getSession());
  const [mounted, setMounted] = useState(false);
  useEffect(() => { if (session) setTimeout(() => setMounted(true), 80); }, [session]);
  const handleLogin  = s => { setSession(s); setTimeout(() => setMounted(true), 80); };
  const handleLogout = () => { setMounted(false); setTimeout(() => { clearSession(); setSession(null); }, 350); };
  if (!session) return <LoginPage onLogin={handleLogin} />;
  return <ChatApp session={session} onLogout={handleLogout} mounted={mounted} />;
}

// ════════════════════════════════════════════════════════
//  LOGIN PAGE  (inchangé)
// ════════════════════════════════════════════════════════
function LoginPage({ onLogin }) {
  const [mode, setMode]       = useState("login");
  const [form, setForm]       = useState({ username:"", password:"", email:"", confirm:"" });
  const [error, setError]     = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [focused, setFocused] = useState(null);
  const [showPw, setShowPw]   = useState(false);

  useEffect(() => { setTimeout(() => setMounted(true), 60); }, []);
  useEffect(() => { setError(""); setSuccess(""); setForm({ username:"", password:"", email:"", confirm:"" }); }, [mode]);

  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }));
  const handleLogin = async () => {
    if (!form.username || !form.password) return setError("Remplissez tous les champs.");
    setLoading(true); setError("");
    await new Promise(r => setTimeout(r, 600));
    const res = loginUser(form.username, form.password);
    setLoading(false);
    if (!res.ok) return setError(res.error);
    onLogin(res.session);
  };
  const handleRegister = async () => {
    if (!form.username || !form.email || !form.password || !form.confirm) return setError("Remplissez tous les champs.");
    if (form.password.length < 6) return setError("Mot de passe trop court (6 min).");
    if (form.password !== form.confirm) return setError("Les mots de passe ne correspondent pas.");
    if (!form.email.includes("@")) return setError("Email invalide.");
    setLoading(true); setError("");
    await new Promise(r => setTimeout(r, 600));
    const res = registerUser(form.username, form.email, form.password);
    setLoading(false);
    if (!res.ok) return setError(res.error);
    setSuccess("Compte créé ! Connectez-vous."); setMode("login");
  };
  const onKey = e => e.key === "Enter" && (mode === "login" ? handleLogin() : handleRegister());

  return (
    <div style={L.root}>
      <div style={L.bg}/>
      {Array.from({length:16}).map((_,i) => (
        <div key={i} style={{ position:"absolute", width:i%3===0?6:i%3===1?4:3, height:i%3===0?6:i%3===1?4:3, borderRadius:"50%", background:"#c8c4bc", left:`${(i*17+5)%96}%`, top:`${(i*23+8)%94}%`, opacity:0.4+(i%3)*0.15, animation:`pdrift ${5+i%4}s ease-in-out infinite`, animationDelay:`${(i*0.4)%4}s`, pointerEvents:"none", zIndex:1 }}/>
      ))}
      <div style={{ ...L.left, opacity:mounted?1:0, transform:mounted?"none":"translateX(-28px)", transition:"all 0.7s cubic-bezier(.34,1.56,.64,1)" }}>
        <div style={L.orb}><div style={L.orbInner}/></div>
        <div style={L.brandName}>DataOlist<br/>AI</div>
        <div style={L.brandSub}>Assistant intelligent<br/>pour l'analyse e-commerce</div>
      </div>
      <div style={L.right}>
        <div style={{ ...L.card, opacity:mounted?1:0, transform:mounted?"translateY(0)":"translateY(20px)", transition:"all 0.6s ease 0.1s" }}>
          <div style={L.cardTitle}>{mode==="login"?"Bon retour 👋":"Créer un compte"}</div>
          <div style={L.cardSub}>{mode==="login"?"Connectez-vous pour continuer":"Rejoignez DataOlist AI"}</div>
          <div style={L.tabs}>
            {["login","register"].map(m => (
              <button key={m} style={{ ...L.tab, ...(mode===m?L.tabOn:{}) }} onClick={()=>setMode(m)}>
                {m==="login"?"Connexion":"Inscription"}
              </button>
            ))}
          </div>
          <div style={L.form}>
            {mode==="register" && <LField label="Email" type="email" value={form.email} onChange={set("email")} onKey={onKey} placeholder="vous@email.com" focused={focused} setFocused={setFocused} id="email"/>}
            <LField label="Nom d'utilisateur" type="text" value={form.username} onChange={set("username")} onKey={onKey} placeholder={mode==="login"?"admin":"votre_nom"} focused={focused} setFocused={setFocused} id="username"/>
            <LField label="Mot de passe" type={showPw?"text":"password"} value={form.password} onChange={set("password")} onKey={onKey} placeholder="••••••••" focused={focused} setFocused={setFocused} id="password"
              suffix={<button style={L.eyeBtn} onClick={()=>setShowPw(!showPw)}><Ic d={showPw?IC.eyeoff:IC.eye} size={16} stroke="#9ca3af"/></button>}/>
            {mode==="register" && <LField label="Confirmer" type="password" value={form.confirm} onChange={set("confirm")} onKey={onKey} placeholder="••••••••" focused={focused} setFocused={setFocused} id="confirm"/>}
            {error   && <div style={L.errBox}><span>⚠</span>{error}</div>}
            {success && <div style={L.okBox}><span>✓</span>{success}</div>}
            <button style={{...L.submitBtn, opacity:loading?0.8:1}} onClick={mode==="login"?handleLogin:handleRegister} disabled={loading}>
              {loading?<><span style={L.spinner}/>Vérification…</>:mode==="login"?"Se connecter →":"Créer mon compte →"}
            </button>
          </div>
        </div>
      </div>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500;600&display=swap');
        *{box-sizing:border-box;margin:0;padding:0;}body{font-family:'DM Sans',sans-serif;}
        @keyframes pdrift{0%,100%{transform:translateY(0);opacity:.4}50%{transform:translateY(-16px);opacity:.7}}
        @keyframes orbpulse{0%,100%{transform:scale(1);opacity:.5}50%{transform:scale(1.9);opacity:0}}
        @keyframes lspin{to{transform:rotate(360deg)}}
        input::placeholder{color:#b8b4ae;}input:focus{outline:none;}button{cursor:pointer;font-family:inherit;}
      `}</style>
    </div>
  );
}
function LField({ label, type, value, onChange, onKey, placeholder, focused, setFocused, id, suffix }) {
  return (
    <div style={L.fieldWrap}>
      <label style={L.label}>{label}</label>
      <div style={{ ...L.inputWrap, ...(focused===id?L.inputFocus:{}) }}>
        <input type={type} value={value} onChange={onChange} onKeyDown={onKey} placeholder={placeholder}
          onFocus={()=>setFocused(id)} onBlur={()=>setFocused(null)} style={L.input}/>
        {suffix}
      </div>
    </div>
  );
}
const L = {
  root:{position:"fixed",inset:0,display:"flex",fontFamily:"'DM Sans',sans-serif",overflow:"hidden"},
  bg:{position:"absolute",inset:0,background:"linear-gradient(135deg,#e8e6e1 0%,#f0eee9 30%,#ede9e4 60%,#e6e2dd 100%)",zIndex:0},
  left:{width:"42%",display:"flex",flexDirection:"column",justifyContent:"center",padding:"4rem 3rem 4rem 5rem",position:"relative",zIndex:2},
  orb:{width:72,height:72,borderRadius:"50%",background:"rgba(17,17,16,.08)",display:"flex",alignItems:"center",justifyContent:"center",marginBottom:"2rem",position:"relative"},
  orbInner:{width:28,height:28,borderRadius:"50%",background:"#111110",boxShadow:"0 0 0 8px rgba(17,17,16,.12)",animation:"orbpulse 3s ease-out infinite"},
  brandName:{fontFamily:"'Syne',sans-serif",fontSize:58,fontWeight:800,color:"#111110",lineHeight:1.0,letterSpacing:"-0.04em",marginBottom:"1rem"},
  brandSub:{fontSize:15,color:"#6f6e69",lineHeight:1.65,fontWeight:300},
  right:{width:"58%",display:"flex",alignItems:"center",justifyContent:"center",position:"relative",zIndex:2,padding:"2rem"},
  card:{width:"100%",maxWidth:460,background:"#fff",borderRadius:20,padding:"2.5rem 2.25rem 2.25rem",boxShadow:"0 2px 4px rgba(0,0,0,.04),0 12px 40px rgba(0,0,0,.10)",border:"1px solid rgba(255,255,255,.9)"},
  cardTitle:{fontFamily:"'Syne',sans-serif",fontSize:26,fontWeight:800,color:"#111110",letterSpacing:"-0.03em",marginBottom:6},
  cardSub:{fontSize:13.5,color:"#9ca3af",fontWeight:300,marginBottom:"1.5rem"},
  tabs:{display:"flex",background:"#f3f2ef",borderRadius:12,padding:4,marginBottom:"1.5rem",gap:3},
  tab:{flex:1,background:"transparent",border:"none",color:"#a8a39a",fontSize:13.5,fontWeight:500,padding:"8px 0",borderRadius:9,transition:"all .18s"},
  tabOn:{background:"#fff",color:"#111110",boxShadow:"0 1px 5px rgba(0,0,0,.08)",fontWeight:600},
  form:{display:"flex",flexDirection:"column",gap:14},
  fieldWrap:{display:"flex",flexDirection:"column",gap:5},
  label:{fontSize:12,fontWeight:600,color:"#6f6e69",letterSpacing:".01em"},
  inputWrap:{display:"flex",alignItems:"center",background:"#f5f4f1",border:"1.5px solid #e8e5e0",borderRadius:11,transition:"all .18s",overflow:"hidden"},
  inputFocus:{border:"1.5px solid #111110",background:"#fff",boxShadow:"0 0 0 3px rgba(17,17,16,.06)"},
  input:{flex:1,background:"transparent",border:"none",outline:"none",padding:"11px 14px",fontSize:14,color:"#111110",fontFamily:"'DM Sans',sans-serif"},
  eyeBtn:{background:"none",border:"none",padding:"0 12px",cursor:"pointer",display:"flex",alignItems:"center",flexShrink:0},
  errBox:{background:"#fef2f2",border:"1px solid #fecaca",borderRadius:9,padding:"9px 13px",fontSize:13,color:"#dc2626",display:"flex",gap:8,alignItems:"center"},
  okBox:{background:"#f0fdf4",border:"1px solid #bbf7d0",borderRadius:9,padding:"9px 13px",fontSize:13,color:"#16a34a",display:"flex",gap:8,alignItems:"center"},
  submitBtn:{background:"#111110",color:"#fff",border:"none",borderRadius:12,padding:"14px 0",fontSize:15,fontWeight:600,cursor:"pointer",fontFamily:"'Syne',sans-serif",letterSpacing:"-0.01em",transition:"all .18s",display:"flex",alignItems:"center",justifyContent:"center",gap:8,marginTop:4,boxShadow:"0 4px 16px rgba(0,0,0,.2)"},
  spinner:{width:15,height:15,border:"2px solid rgba(255,255,255,.3)",borderTop:"2px solid #fff",borderRadius:"50%",animation:"lspin .7s linear infinite",display:"inline-block",flexShrink:0},
};

// ════════════════════════════════════════════════════════
//  CHAT APP  ← MODIFIÉ : affichage graphes + dashboard
// ════════════════════════════════════════════════════════
function ChatApp({ session, onLogout, mounted }) {
  const [sessions, setSessions] = useState(() => { const s = loadSessions(); return s.length ? s : [newSession()]; });
  const [activeId, setActiveId] = useState(() => { const s = loadSessions(); return s.length ? s[0].id : null; });
  const [panel, setPanel]       = useState("history");
  const [input, setInput]       = useState("");
  const [loading, setLoading]   = useState(false);
  const [searchQ, setSearchQ]   = useState("");
  const [editingId, setEditingId]   = useState(null);
  const [editTitle, setEditTitle]   = useState("");
  const [starred, setStarred]   = useState(() => { try { return JSON.parse(localStorage.getItem("dataolist_starred") || "[]"); } catch { return []; } });
  const [fileCtx, setFileCtx]   = useState(null);
  const [fileLoading, setFileLoading] = useState(false);
  const [showLogout, setShowLogout]   = useState(false);
  const [pdfUploading, setPdfUploading] = useState(false); // ← NOUVEAU
  const bottomRef = useRef(null);
  const inputRef  = useRef(null);
  const fileRef   = useRef(null);
  const active    = sessions.find(s => s.id === activeId) || sessions[0];

  useEffect(() => { saveSessions(sessions); }, [sessions]);
  useEffect(() => { localStorage.setItem("dataolist_starred", JSON.stringify(starred)); }, [starred]);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior:"smooth" }); }, [active?.messages, loading]);

  const updateSession = (id, msgs) => setSessions(prev => prev.map(s => {
    if (s.id !== id) return s;
    const fu = msgs.find(m => m.role === "user");
    let title = s.title;
    if (fu && s.title === "Nouvelle conversation") {
      const rawTitle = fu.content.split("\n").find(l => l.trim() && !l.startsWith("[") && !l.startsWith("📎")) || fu.content;
      title = rawTitle.replace(/[\[\]]/g,"").trim().slice(0,45) + (rawTitle.length>45?"…":"");
    }
    return { ...s, messages: msgs, title, date: Date.now() };
  }));

const handleFile = async (file) => {
  if (!file) return;
  setFileLoading(true);
 
  try {
    // 1. Envoi au backend (validation e-commerce + analyse)
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch("http://localhost:5000/upload-file", {
      method: "POST",
      body: fd,
      credentials: "include",
    });
    const result = await res.json();
 
    const sid = activeId || sessions[0].id;
 
    // 2. Fichier non e-commerce → message de refus dans le chat
    if (result.is_ecommerce === false) {
      updateSession(sid, [
        ...(active?.messages || []),
        {
          role: "assistant",
          content: result.answer,
          time: Date.now(),
        },
      ]);
      return; // pas de fileCtx
    }
 
    // 3. Fichier e-commerce → afficher l'analyse immédiatement
    updateSession(sid, [
      ...(active?.messages || []),
      {
        role: "assistant",
        content: `📎 **${file.name}** analysé avec succès !\n\n${result.answer}`,
        time: Date.now(),
        chart: result.chart || null,
        table: result.table || null,
        suggestions: result.suggestions || [],
        source: "file",
      },
    ]);
 
    // 4. Positionner fileCtx pour que l'utilisateur puisse poser des
    //    questions de suivi sur ce fichier
    setFileCtx({
      name: file.name,
      // On stocke un résumé textuel compact pour les questions de suivi
      content: `[Fichier analysé: ${file.name}]\n${result.answer}`,
    });
 
  } catch (e) {
    const sid = activeId || sessions[0].id;
    updateSession(sid, [
      ...(active?.messages || []),
      {
        role: "assistant",
        content: `❌ Impossible d'analyser le fichier : ${e.message}`,
        time: Date.now(),
      },
    ]);
  } finally {
    setFileLoading(false);
  }
};
// ── MODIFIÉ : handleSend — récupère chart + table du backend ─────────────
  const handleSend = async text => {
    const q = (text || input).trim();
    if (!q || loading) return;
    setInput("");
    const expType = detectExport(q);

    // ── Question nettoyée envoyée à l'API, question originale gardée pour affichage ──
    const cleanedQuery = expType ? cleanExportQuery(q) : q;

    const userContent = fileCtx ? `📎 **${fileCtx.name}**\n${q}` : q;
    const msgs        = [...(active?.messages||[]), { role:"user", content:userContent, time:Date.now() }];
    const sid         = activeId || sessions[0].id;
    updateSession(sid, msgs);
    setLoading(true);

    try {
      // ── Appel API → { answer, needs_chart, chart, table, sql, source, error }
      const res = await apiSend(cleanedQuery, fileCtx?.content || null);

      const answer      = res.answer || "Pas de réponse.";
// ── Si c'est une demande d'export, on n'affiche jamais le graphe dans le chat ──
const chart        = (!expType && res.needs_chart) ? res.chart : null;
const table         = res.table || null;
const suggestions = expType ? [] : (res.suggestions || []);

      // ── Export si demandé
      if (expType) {
        const ts = new Date().toISOString().slice(0, 10);

        const data =
          table ||
          parseTable(answer) ||
          answer.split("\n").map((l, i) => ({
            N: i + 1,
            Texte: l,
          }));

        if (expType === "csv")
          exportCSV(data, `dataolist_${ts}.csv`);

        if (expType === "excel")
          exportExcel(data, `dataolist_${ts}.xlsx`);

        if (expType === "pdf")
          exportPDF(answer, `rapport_${ts}.pdf`);
      }

      // ── Sauvegarder dans l'historique
      updateSession(sid, [
        ...msgs,
        {
          role: "assistant",
          content: answer,
          time: Date.now(),
          chart,
          table,
          suggestions,
          source: res.source || "sql",
        },
      ]);

      setFileCtx(null);

    } catch (error) {
      console.error("API ERROR:", error);

      updateSession(sid, [
        ...msgs,
        {
          role: "assistant",
          content:
            error?.message ||
            "❌ Une erreur est survenue lors du traitement de votre demande.",
          time: Date.now(),
        },
      ]);

    } finally {
      setLoading(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  };

  const createSession = () => { const s=newSession(); setSessions(p=>[s,...p]); setActiveId(s.id); setFileCtx(null); setPanel("history"); };
  const deleteSession = id => setSessions(prev => { const next=prev.filter(s=>s.id!==id); if(!next.length){const s=newSession();setActiveId(s.id);return[s];} if(activeId===id)setActiveId(next[0].id); return next; });
  const toggleStar = id => setStarred(p => p.includes(id)?p.filter(x=>x!==id):[...p,id]);
  const startEdit  = s => { setEditingId(s.id); setEditTitle(s.title); };
  const saveEdit   = id => { setSessions(p=>p.map(s=>s.id===id?{...s,title:editTitle||s.title}:s)); setEditingId(null); };

  const filtered    = sessions.filter(s => !searchQ || s.title.toLowerCase().includes(searchQ.toLowerCase()) || s.messages.some(m=>m.content?.toLowerCase().includes(searchQ.toLowerCase())));
  const starredList = sessions.filter(s => starred.includes(s.id));
  const grouped     = filtered.reduce((acc,s)=>{ const l=fmtDate(s.date); if(!acc[l])acc[l]=[]; acc[l].push(s); return acc; },{});

  const renderContent = t => {
    if (!t) return "";
    let r = t.split("\n").join("<br/>");
    r = r.replace(/[*][*]([^*]+)[*][*]/g, "<strong>$1</strong>");
    return r;
  };

  const NavBtn = ({ id, icon, label }) => (
    <button onClick={()=>setPanel(p=>p===id?null:id)}
      style={{...C.navBtn, background:panel===id?"#e8e5e0":"transparent"}} title={label}>
      <Ic d={IC[icon]} size={18}/>
    </button>
  );
  const SessItem = ({ s }) => (
    <div style={{...C.sessItem, background:s.id===activeId?"#ebe9e4":"transparent"}}>
      {editingId===s.id?(
        <input value={editTitle} onChange={e=>setEditTitle(e.target.value)} onBlur={()=>saveEdit(s.id)} onKeyDown={e=>e.key==="Enter"&&saveEdit(s.id)} autoFocus style={C.editInput}/>
      ):(
        <button style={C.sessBtn} onClick={()=>{setActiveId(s.id);setFileCtx(null);}}>
          <span style={C.sessTitle}>{s.title}</span>
          <span style={C.sessMeta}>{fmtDate(s.date)}</span>
        </button>
      )}
      <div style={C.sessActions}>
        <button style={C.ib} onClick={()=>toggleStar(s.id)}><Ic d={IC.star} size={12} stroke={starred.includes(s.id)?"#f59e0b":"#c0bbb4"} fill={starred.includes(s.id)?"#f59e0b":"none"}/></button>
        <button style={C.ib} onClick={()=>startEdit(s)}><Ic d={IC.edit} size={12}/></button>
        <button style={C.ib} onClick={()=>deleteSession(s.id)}><Ic d={IC.trash} size={12}/></button>
      </div>
    </div>
  );

  return (
    <div style={{...C.root, opacity:mounted?1:0, transition:"opacity .4s ease"}}>
      {/* ── Rail ─────────────────────────────────────────── */}
      <nav style={C.rail}>
        <div style={C.railTop}>
          <div style={C.railLogo}><div style={C.logoDot}/></div>
          <button style={C.newBtn} onClick={createSession} title="Nouvelle conversation"><Ic d={IC.new} size={17}/></button>
          <div style={C.railDiv}/>
          <NavBtn id="history" icon="history" label="Historique"/>
          <NavBtn id="search"  icon="search"  label="Rechercher"/>
          <NavBtn id="starred" icon="star"    label="Favoris"/>
        </div>
        <div style={C.railBottom}>
          <NavBtn id="settings" icon="cog" label="Paramètres"/>
          <button style={C.userAvatar} onClick={()=>setShowLogout(true)} title={session.username}>
            {session.username[0].toUpperCase()}
          </button>
        </div>
      </nav>

      {/* ── Sidebar ───────────────────────────────────────── */}
      {panel && (
        <aside style={C.sidebar}>
          <div style={C.sbHead}>
            <span style={C.sbTitle}>{panel==="history"?"Historique":panel==="search"?"Rechercher":panel==="starred"?"Favoris":"Paramètres"}</span>
            <button style={C.ib} onClick={()=>setPanel(null)}><Ic d={IC.close} size={15}/></button>
          </div>
          {panel==="search" && (
            <div style={{padding:"0 .7rem .5rem"}}>
              <input value={searchQ} onChange={e=>setSearchQ(e.target.value)} placeholder="Rechercher…" autoFocus style={C.searchInput}/>
            </div>
          )}
          <div style={C.sessList}>
            {panel==="history" && (Object.keys(grouped).length===0?<div style={C.empty}>Aucune conversation</div>:Object.entries(grouped).map(([label,list])=>(
              <div key={label}><div style={C.groupLabel}>{label}</div>{list.map(s=><SessItem key={s.id} s={s}/>)}</div>
            )))}
            {panel==="search"  && (filtered.length===0?<div style={C.empty}>Aucun résultat</div>:filtered.map(s=><SessItem key={s.id} s={s}/>))}
            {panel==="starred" && (starredList.length===0?<div style={C.empty}>Étoilez une conversation pour la retrouver ici.</div>:starredList.map(s=><SessItem key={s.id} s={s}/>))}
            {panel==="settings" && (
              <div style={{padding:".5rem .8rem"}}>
                <div style={C.userCard}>
                  <div style={C.ucAvatar}>{session.username[0].toUpperCase()}</div>
                  <div><div style={{fontSize:13,fontWeight:600,color:"#111110"}}>{session.username}</div><div style={{fontSize:11,color:"#a8a39a"}}>{session.email||"local"}</div></div>
                </div>
                {[["Modèle","llama-3.3-70b"],["Backend","Flask · :5000"],["Base","PostgreSQL · Olist"],["Convs",sessions.length]].map(([k,v])=>(
                  <div key={k} style={C.settingRow}><span style={{fontSize:12,color:"#6f6e69"}}>{k}</span><strong style={{fontSize:12}}>{v}</strong></div>
                ))}
                <button style={C.dangerBtn} onClick={()=>{if(window.confirm("Effacer tout l'historique ?")){const s=newSession();setSessions([s]);setActiveId(s.id);}}}>Effacer l'historique</button>
                <button style={{...C.dangerBtn,marginTop:8}} onClick={()=>setShowLogout(true)}><Ic d={IC.logout} size={13} stroke="#dc2626"/> Se déconnecter</button>
              </div>
            )}
          </div>
        </aside>
      )}

      {/* ── Main ──────────────────────────────────────────── */}
      <main style={C.main}>
        <header style={C.header}>
          <div style={C.headerLeft}><div style={C.hDot}/><span style={{fontSize:13,fontWeight:600,letterSpacing:"-0.02em"}}>DataOlist AI</span></div>
          <span style={C.convTitle}>{active?.title!=="Nouvelle conversation"?active?.title:""}</span>
          <div style={C.headerRight}>
            <button style={C.logoutBtn} onClick={()=>setShowLogout(true)} title="Déconnexion"><Ic d={IC.logout} size={15} stroke="#a8a39a"/></button>
          </div>
        </header>

        {/* ── Feed messages ───────────────────────────────── */}
        <div style={C.feed}>
          {(active?.messages||[]).map((msg,i)=>(
            <div key={i} style={{...C.msgRow, justifyContent:msg.role==="user"?"flex-end":"flex-start", alignItems:"flex-start"}}>
              {msg.role==="assistant" && <div style={C.botAv}>AI</div>}

              <div style={{ maxWidth:"82%", display:"flex", flexDirection:"column", gap:6 }}>
                {/* Bulle texte */}
                <div style={{...C.bubble,...(msg.role==="user"?C.uBubble:C.aBubble)}}>
                  <div style={C.bText} dangerouslySetInnerHTML={{__html:renderContent(msg.content)}}/>
                  {msg.time && <div style={C.bTime}>{fmtTime(msg.time)}</div>}
                </div>

                {/* ── NOUVEAU : ChartBlock sous la bulle ── */}
                {msg.role==="assistant" && msg.chart && (
                  <ChartBlock chart={msg.chart}  />
                )}
                {msg.role === "assistant" &&
 msg.suggestions?.length > 0 && (
  <SuggestionsBlock
    suggestions={msg.suggestions}
    onSelect={q => handleSend(q)}
  />
)}
                {/* Badge source RAG */}
                {msg.source==="rag" && (
                  <span style={{fontSize:10,color:"#a8a39a",paddingLeft:2}}>📄 Source : documents indexés</span>
                )}
              </div>
            </div>
          ))}

          {/* Loading */}
          {loading && (
            <div style={{...C.msgRow,justifyContent:"flex-start"}}>
              <div style={C.botAv}>AI</div>
              <div style={{...C.bubble,...C.aBubble}}>
                <div style={C.typing}>{[0,150,300].map(d=><span key={d} style={{...C.dot,animationDelay:`${d}ms`}}/>)}</div>
              </div>
            </div>
          )}

          {/* Suggestions */}
          {active?.messages.length===1 && !loading && (
            <div style={C.suggWrap}>
              {SUGGESTIONS.map((s,i)=>(
                <button key={i} style={C.suggBtn} onClick={()=>handleSend(s)}>{s}</button>
              ))}
            </div>
          )}
          <div ref={bottomRef}/>
        </div>

        {/* Prévisualisation fichier */}
        {fileCtx && (
          <div style={C.filePrev}>
            <Ic d={IC.file} size={14} stroke="#16a34a"/>
            <span style={{fontSize:12.5,color:"#111110",fontWeight:500}}>{fileCtx.name}</span>
            <span style={{fontSize:11,color:"#a8a39a",flex:1}}>prêt à analyser</span>
            <button style={C.ib} onClick={()=>setFileCtx(null)}><Ic d={IC.close} size={13}/></button>
          </div>
        )}

      {/* Barre de saisie */}
        <div style={C.inputBar}>
          <div style={C.inputWrap}>
<button style={C.attachBtn} onClick={()=>fileRef.current?.click()} disabled={fileLoading} title="Joindre CSV/Excel/PDF">
  {fileLoading ? <span style={C.miniSpin}/> : <Ic d={IC.attach} size={17} stroke={fileCtx?"#16a34a":"#6f6e69"}/>}
</button>
<input ref={fileRef} type="file" accept=".csv,.xlsx,.xls,.pdf" style={{display:"none"}}
  onChange={e=>{handleFile(e.target.files[0]);e.target.value="";}}/>            <input ref={inputRef} value={input} onChange={e=>setInput(e.target.value)}
              onKeyDown={e=>e.key==="Enter"&&!e.shiftKey&&handleSend()}
              placeholder="Ex: Montre l'évolution des ventes par mois…"
              style={C.input} disabled={loading}/>
            <button onClick={()=>handleSend()} disabled={(!input.trim()&&!fileCtx)||loading}
              style={{...C.sendBtn,opacity:(!input.trim()&&!fileCtx)||loading?.35:1}}>
              <Ic d={IC.send} size={15} stroke="#fff"/>
            </button>
          </div>
          <div style={C.disclaimer}>Graphes · CSV · Excel · PDF · RAG · DataOlist AI peut faire des erreurs.</div>
        </div>
      </main>

      {/* Modal logout */}
      {showLogout && (
        <div style={C.overlay} onClick={()=>setShowLogout(false)}>
          <div style={C.modal} onClick={e=>e.stopPropagation()}>
            <div style={{fontSize:36,marginBottom:10}}>👋</div>
            <div style={{fontSize:16,fontWeight:700,color:"#111110",marginBottom:5}}>Au revoir, {session.username} !</div>
            <div style={{fontSize:13,color:"#a8a39a",marginBottom:22}}>Votre historique reste sauvegardé.</div>
            <div style={{display:"flex",gap:10}}>
              <button style={C.mCancel} onClick={()=>setShowLogout(false)}>Annuler</button>
              <button style={C.mConfirm} onClick={()=>{setShowLogout(false);onLogout();}}>Déconnecter</button>
            </div>
          </div>
        </div>
      )}

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400&display=swap');
        *{box-sizing:border-box;margin:0;padding:0;}body{font-family:'DM Sans',sans-serif;background:#fafaf8;}
        @keyframes blink{0%,80%,100%{transform:scale(.7);opacity:.4}40%{transform:scale(1);opacity:1}}
        @keyframes spin{to{transform:rotate(360deg)}}
        ::-webkit-scrollbar{width:3px;}::-webkit-scrollbar-thumb{background:#d4cfc8;border-radius:99px;}
        button,input{font-family:inherit;cursor:pointer;}input{cursor:text;}input::placeholder{color:#c0bbb4;}
      `}</style>
    </div>
  );
}
function SuggestionsBlock({ suggestions, onSelect }) {
  if (!suggestions || suggestions.length === 0) return null;

  return (
    <div
      style={{
        marginTop: 8,
        display: "flex",
        flexDirection: "column",
        gap: 6,
      }}
    >
      <span
        style={{
          fontSize: 10,
          fontWeight: 600,
          color: "#a8a39a",
          textTransform: "uppercase",
          letterSpacing: ".05em",
          paddingLeft: 2,
        }}
      >
        💡 Questions suggérées
      </span>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 5,
        }}
      >
        {suggestions.map((q, i) => (
          <button
            key={i}
            onClick={() => onSelect(q)}
            style={{
              background: "#faf9f7",
              border: "1px solid #e8e5e0",
              borderRadius: 10,
              padding: "8px 13px",
              fontSize: 12.5,
              color: "#111110",
              cursor: "pointer",
              textAlign: "left",
              lineHeight: 1.4,
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <span
              style={{
                color: "#a8a39a",
                flexShrink: 0,
                fontSize: 11,
              }}
            >
              →
            </span>
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
const C = {
  root:{display:"flex",height:"100vh",background:"#fafaf8",overflow:"hidden"},
  rail:{width:52,background:"#f3f2ef",borderRight:"1px solid #e8e5e0",display:"flex",flexDirection:"column",alignItems:"center",padding:"10px 0",flexShrink:0,zIndex:10},
  railTop:{display:"flex",flexDirection:"column",alignItems:"center",gap:3,flex:1},
  railBottom:{display:"flex",flexDirection:"column",alignItems:"center",gap:8,paddingBottom:8},
  railLogo:{width:34,height:34,borderRadius:10,background:"#111110",display:"flex",alignItems:"center",justifyContent:"center",marginBottom:6},
  logoDot:{width:8,height:8,borderRadius:"50%",background:"#16a34a"},
  newBtn:{width:34,height:34,borderRadius:8,background:"transparent",border:"1px solid #d4cfc8",color:"#6f6e69",display:"flex",alignItems:"center",justifyContent:"center",marginBottom:4},
  railDiv:{width:24,height:1,background:"#e8e5e0",margin:"4px 0"},
  navBtn:{width:34,height:34,borderRadius:8,border:"none",color:"#6f6e69",display:"flex",alignItems:"center",justifyContent:"center",transition:"background .1s"},
  userAvatar:{width:28,height:28,borderRadius:"50%",background:"#111110",color:"#fff",border:"none",fontSize:11,fontWeight:700,display:"flex",alignItems:"center",justifyContent:"center",cursor:"pointer"},
  sidebar:{width:245,background:"#f9f8f6",borderRight:"1px solid #e8e5e0",display:"flex",flexDirection:"column",flexShrink:0,overflow:"hidden"},
  sbHead:{display:"flex",alignItems:"center",justifyContent:"space-between",padding:".85rem .75rem .5rem",flexShrink:0},
  sbTitle:{fontSize:12,fontWeight:700,color:"#111110",letterSpacing:".04em",textTransform:"uppercase"},
  searchInput:{width:"100%",background:"#fff",border:"1px solid #e8e5e0",borderRadius:8,padding:"6px 10px",fontSize:13,color:"#111110",outline:"none"},
  sessList:{flex:1,overflowY:"auto",padding:"0 .4rem 1rem"},
  groupLabel:{fontSize:10,fontWeight:600,letterSpacing:".06em",color:"#a8a39a",textTransform:"uppercase",padding:".6rem .4rem .2rem"},
  sessItem:{borderRadius:7,marginBottom:1,padding:"1px 3px 1px 1px",display:"flex",alignItems:"center",gap:2,transition:"background .1s"},
  sessBtn:{flex:1,background:"none",border:"none",textAlign:"left",padding:"5px 6px",borderRadius:6,display:"flex",flexDirection:"column",gap:2,minWidth:0},
  sessTitle:{fontSize:12.5,color:"#111110",overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap",display:"block",maxWidth:145},
  sessMeta:{fontSize:10.5,color:"#a8a39a"},
  sessActions:{display:"flex",gap:1,flexShrink:0},
  editInput:{flex:1,border:"1px solid #d4cfc8",borderRadius:5,padding:"3px 6px",fontSize:12.5,outline:"none",background:"#fff"},
  ib:{background:"none",border:"none",color:"#a8a39a",display:"flex",alignItems:"center",justifyContent:"center",width:22,height:22,borderRadius:4,padding:0,cursor:"pointer"},
  empty:{fontSize:12.5,color:"#a8a39a",textAlign:"center",padding:"2rem 1rem",lineHeight:1.6},
  userCard:{display:"flex",alignItems:"center",gap:10,padding:"10px 0 14px",borderBottom:"1px solid #f0ede8",marginBottom:12},
  ucAvatar:{width:34,height:34,borderRadius:"50%",background:"#111110",color:"#fff",display:"flex",alignItems:"center",justifyContent:"center",fontSize:14,fontWeight:700,flexShrink:0},
  settingRow:{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"7px 0",borderBottom:"1px solid #f0ede8"},
  dangerBtn:{marginTop:16,width:"100%",background:"transparent",border:"1px solid #fca5a5",color:"#dc2626",borderRadius:8,padding:"7px 12px",fontSize:12.5,fontWeight:500,display:"flex",alignItems:"center",justifyContent:"center",gap:6,cursor:"pointer"},
  main:{flex:1,display:"flex",flexDirection:"column",overflow:"hidden",background:"#fff"},
  header:{display:"flex",alignItems:"center",gap:10,padding:".6rem 1.25rem",borderBottom:"1px solid #f0ede8",flexShrink:0},
  headerLeft:{display:"flex",alignItems:"center",gap:6,flexShrink:0},
  hDot:{width:7,height:7,borderRadius:"50%",background:"#16a34a"},
  convTitle:{flex:1,textAlign:"center",fontSize:12,color:"#6f6e69",overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap",padding:"0 1rem"},
  headerRight:{display:"flex",alignItems:"center",gap:8,flexShrink:0},
  msgBadge:{fontSize:11,color:"#a8a39a",background:"#f3f2ef",padding:"3px 10px",borderRadius:99,fontWeight:500},
  logoutBtn:{background:"none",border:"none",display:"flex",alignItems:"center",justifyContent:"center",width:28,height:28,borderRadius:6,padding:0,cursor:"pointer"},
  feed:{flex:1,overflowY:"auto",padding:"1.5rem",display:"flex",flexDirection:"column",gap:16,maxWidth:760,width:"100%",margin:"0 auto",alignSelf:"center",boxSizing:"border-box"},
  msgRow:{display:"flex",gap:8},
  botAv:{width:26,height:26,borderRadius:"50%",background:"#111110",color:"#fff",display:"flex",alignItems:"center",justifyContent:"center",fontSize:9,fontWeight:700,flexShrink:0,marginTop:2},
  bubble:{borderRadius:14,padding:".65rem .9rem",lineHeight:1.65},
  uBubble:{background:"#111110",color:"#fff",borderBottomRightRadius:4,alignSelf:"flex-end"},
  aBubble:{background:"#f5f4f1",color:"#111110",borderBottomLeftRadius:4,border:"1px solid #eceae4"},
  bText:{fontSize:13.5,fontWeight:400,letterSpacing:"-0.01em"},
  bTime:{fontSize:10,marginTop:5,opacity:.4,textAlign:"right",fontFamily:"'DM Mono',monospace"},
  typing:{display:"flex",gap:4,padding:"3px 2px",alignItems:"center"},
  dot:{display:"inline-block",width:6,height:6,borderRadius:"50%",background:"#888780",animation:"blink 1.2s infinite ease-in-out"},
  suggWrap:{display:"flex",flexWrap:"wrap",gap:8,marginTop:8},
  suggBtn:{background:"#f5f4f1",border:"1px solid #e8e5e0",borderRadius:20,padding:"6px 14px",fontSize:12.5,color:"#6f6e69",cursor:"pointer"},
  filePrev:{display:"flex",alignItems:"center",gap:8,margin:"0 1.25rem 0",padding:"7px 12px",background:"#f0fdf4",border:"1px solid #bbf7d0",borderRadius:8,flexShrink:0,maxWidth:740,width:"calc(100% - 2.5rem)",alignSelf:"center",boxSizing:"border-box"},
  inputBar:{padding:".6rem 1.25rem .9rem",background:"#fff",borderTop:"1px solid #f0ede8",flexShrink:0,maxWidth:760,width:"100%",alignSelf:"center",boxSizing:"border-box"},
  inputWrap:{display:"flex",gap:7,alignItems:"center",background:"#faf9f7",border:"1.5px solid #e8e5e0",borderRadius:13,padding:"5px 5px 5px 10px"},
  attachBtn:{background:"none",border:"none",display:"flex",alignItems:"center",justifyContent:"center",padding:4,borderRadius:6,flexShrink:0,cursor:"pointer"},
  input:{flex:1,background:"transparent",border:"none",outline:"none",fontSize:13.5,color:"#111110",padding:"4px 0",letterSpacing:"-0.01em"},
  sendBtn:{background:"#111110",color:"#fff",border:"none",borderRadius:8,width:32,height:32,display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0,transition:"opacity .15s",cursor:"pointer"},
  miniSpin:{width:16,height:16,border:"2px solid #e8e5e0",borderTop:"2px solid #6f6e69",borderRadius:"50%",animation:"spin .7s linear infinite",display:"inline-block"},
  disclaimer:{textAlign:"center",fontSize:10.5,color:"#c0bbb4",marginTop:6},
  overlay:{position:"fixed",inset:0,background:"rgba(0,0,0,.3)",display:"flex",alignItems:"center",justifyContent:"center",zIndex:100,backdropFilter:"blur(4px)"},
  modal:{background:"#fff",border:"1px solid #f0ede8",borderRadius:18,padding:"2rem 1.75rem",textAlign:"center",maxWidth:300,width:"90%",boxShadow:"0 20px 60px rgba(0,0,0,.12)"},
  mCancel:{flex:1,background:"transparent",border:"1px solid #e8e5e0",color:"#6f6e69",borderRadius:9,padding:"9px 0",fontSize:13,fontWeight:500,cursor:"pointer"},
  mConfirm:{flex:1,background:"#111110",border:"none",color:"#fff",borderRadius:9,padding:"9px 0",fontSize:13,fontWeight:600,cursor:"pointer"},
};
