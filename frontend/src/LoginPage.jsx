import { useState, useEffect, useRef } from "react";

const USERS_KEY = "dataolist_users";
const SESSION_KEY = "dataolist_auth";

function getUsers() {
  try {
    const u = JSON.parse(localStorage.getItem(USERS_KEY) || "[]");
    if (!u.find(x => x.username === "admin")) {
      u.push({ username: "admin", password: "admin123", email: "admin@olist.com", createdAt: Date.now() });
      localStorage.setItem(USERS_KEY, JSON.stringify(u));
    }
    return u;
  } catch { return []; }
}

function saveUser(user) {
  const users = getUsers();
  if (users.find(u => u.username === user.username || u.email === user.email))
    return { ok: false, error: "Nom d'utilisateur ou email déjà utilisé." };
  users.push({ ...user, createdAt: Date.now() });
  localStorage.setItem(USERS_KEY, JSON.stringify(users));
  return { ok: true };
}

function loginUser(username, password) {
  const users = getUsers();
  const user = users.find(u => u.username === username && u.password === password);
  if (!user) return { ok: false, error: "Identifiants incorrects." };
  const session = { username: user.username, email: user.email, loginAt: Date.now() };
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  return { ok: true, session };
}

export function getSession() {
  try { return JSON.parse(localStorage.getItem(SESSION_KEY)); } catch { return null; }
}

export function logout() {
  localStorage.removeItem(SESSION_KEY);
}

function Particles() {
  return (
    <div style={G.particlesWrap} aria-hidden="true">
      {Array.from({ length: 18 }).map((_, i) => (
        <div key={i} style={{
          ...G.particle,
          left: `${(i * 17 + 5) % 100}%`,
          top: `${(i * 23 + 10) % 100}%`,
          animationDelay: `${(i * 0.4) % 4}s`,
          animationDuration: `${5 + (i % 5)}s`,
          width: i % 3 === 0 ? 6 : i % 3 === 1 ? 4 : 3,
          height: i % 3 === 0 ? 6 : i % 3 === 1 ? 4 : 3,
          opacity: 0.15 + (i % 4) * 0.08,
        }} />
      ))}
    </div>
  );
}

export default function LoginPage({ onLogin }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ username: "", password: "", email: "", confirm: "" });
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [focused, setFocused] = useState(null);
  const firstRef = useRef(null);

  useEffect(() => {
    setTimeout(() => setMounted(true), 60);
    setTimeout(() => firstRef.current?.focus(), 500);
  }, []);

  useEffect(() => {
    setError(""); setSuccess("");
    setForm({ username: "", password: "", email: "", confirm: "" });
    setTimeout(() => firstRef.current?.focus(), 100);
  }, [mode]);

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }));

  const handleLogin = async () => {
    if (!form.username || !form.password) return setError("Remplissez tous les champs.");
    setLoading(true); setError("");
    await new Promise(r => setTimeout(r, 650));
    const res = loginUser(form.username, form.password);
    setLoading(false);
    if (!res.ok) return setError(res.error);
    onLogin(res.session);
  };

  const handleRegister = async () => {
    if (!form.username || !form.email || !form.password || !form.confirm) return setError("Remplissez tous les champs.");
    if (form.password.length < 6) return setError("Mot de passe trop court (6 caractères min).");
    if (form.password !== form.confirm) return setError("Les mots de passe ne correspondent pas.");
    if (!form.email.includes("@")) return setError("Email invalide.");
    setLoading(true); setError("");
    await new Promise(r => setTimeout(r, 650));
    const res = saveUser({ username: form.username, email: form.email, password: form.password });
    setLoading(false);
    if (!res.ok) return setError(res.error);
    setSuccess("Compte créé ! Connectez-vous.");
    setMode("login");
  };

  const onKey = (e) => e.key === "Enter" && (mode === "login" ? handleLogin() : handleRegister());

  return (
    <div style={G.root}>
      {/* Gradient mesh background */}
      <div style={G.bgMesh} />
      <div style={G.bgGlow1} />
      <div style={G.bgGlow2} />
      <div style={G.bgGlow3} />
      <Particles />

      {/* Left panel — branding */}
      <div style={{ ...G.leftPanel, opacity: mounted ? 1 : 0, transform: mounted ? "translateX(0)" : "translateX(-30px)" }}>
        <div style={G.leftInner}>
          <div style={G.brandMark}>
            <div style={G.brandRing} />
            <div style={G.brandDot} />
          </div>
          <div style={G.brandName}>DataOlist<br />AI</div>
          <div style={G.brandTagline}>Assistant intelligent<br />pour l'analyse e-commerce</div>
          <div style={G.statsGrid}>
            {[["99K+","Commandes analysées"],["7","Tables SQL"],["3","Années de données"]].map(([n,l]) => (
              <div key={n} style={G.statItem}>
                <div style={G.statNum}>{n}</div>
                <div style={G.statLabel}>{l}</div>
              </div>
            ))}
          </div>
          <div style={G.techStack}>
            {["Groq","PostgreSQL","React","Flask"].map(t => (
              <span key={t} style={G.techBadge}>{t}</span>
            ))}
          </div>
        </div>
      </div>

      {/* Right panel — form */}
      <div style={G.rightPanel}>
        <div style={{ ...G.card, opacity: mounted ? 1 : 0, transform: mounted ? "translateY(0)" : "translateY(20px)" }}>
          {/* Mobile logo */}
          <div style={G.mobileLogo}>
            <div style={G.mobileLogoDot} />
            <span style={G.mobileLogoName}>DataOlist AI</span>
          </div>

          <div style={G.cardHeader}>
            <div style={G.cardTitle}>{mode === "login" ? "Bon retour 👋" : "Créer un compte"}</div>
            <div style={G.cardSub}>{mode === "login" ? "Connectez-vous pour continuer" : "Rejoignez DataOlist AI"}</div>
          </div>

          {/* Tabs */}
          <div style={G.tabs}>
            {["login","register"].map(m => (
              <button key={m} style={{ ...G.tab, ...(mode === m ? G.tabActive : {}) }} onClick={() => setMode(m)}>
                {m === "login" ? "Connexion" : "Inscription"}
              </button>
            ))}
          </div>

          <div style={G.form}>
            {mode === "register" && (
              <Field label="Email" type="email" value={form.email} onChange={set("email")} onKey={onKey}
                placeholder="vous@email.com" focused={focused} setFocused={setFocused} id="email" />
            )}
            <Field ref={firstRef} label="Nom d'utilisateur" type="text" value={form.username} onChange={set("username")} onKey={onKey}
              placeholder={mode === "login" ? "admin" : "votre_nom"} focused={focused} setFocused={setFocused} id="username" />
            <Field label="Mot de passe" type="password" value={form.password} onChange={set("password")} onKey={onKey}
              placeholder="••••••••" focused={focused} setFocused={setFocused} id="password" />
            {mode === "register" && (
              <Field label="Confirmer le mot de passe" type="password" value={form.confirm} onChange={set("confirm")} onKey={onKey}
                placeholder="••••••••" focused={focused} setFocused={setFocused} id="confirm" />
            )}

            {error && <div style={G.errorBox}><span>⚠</span>{error}</div>}
            {success && <div style={G.successBox}><span>✓</span>{success}</div>}

            <button style={{ ...G.submitBtn, opacity: loading ? 0.85 : 1 }}
              onClick={mode === "login" ? handleLogin : handleRegister} disabled={loading}>
              {loading
                ? <><span style={G.spinner} /> Vérification…</>
                : mode === "login" ? "Se connecter →" : "Créer mon compte →"
              }
            </button>

            {mode === "login" && (
              <div style={G.hint}>
                Compte démo : <code style={G.code}>admin</code> / <code style={G.code}>admin123</code>
              </div>
            )}
          </div>
        </div>
      </div>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500;600&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'DM Sans', sans-serif; }
        @keyframes float { 0%,100%{transform:translate(0,0)} 33%{transform:translate(12px,-18px)} 66%{transform:translate(-8px,12px)} }
        @keyframes spin { to{transform:rotate(360deg)} }
        @keyframes pulse { 0%,100%{transform:scale(1);opacity:0.7} 50%{transform:scale(2);opacity:0} }
        @keyframes particleDrift { 0%,100%{transform:translateY(0) scale(1);opacity:0.15} 50%{transform:translateY(-20px) scale(1.2);opacity:0.35} }
        @keyframes shimmer { 0%{background-position:200% center} 100%{background-position:-200% center} }
        input::placeholder { color: #9ca3af; }
        input:focus { outline: none; }
        button { cursor: pointer; font-family: inherit; }
      `}</style>
    </div>
  );
}

const Field = ({ label, type, value, onChange, onKey, placeholder, focused, setFocused, id }) => (
  <div style={G.fieldWrap}>
    <label style={G.label}>{label}</label>
    <input type={type} value={value} onChange={onChange} onKeyDown={onKey} placeholder={placeholder}
      onFocus={() => setFocused(id)} onBlur={() => setFocused(null)}
      style={{ ...G.input, ...(focused === id ? G.inputFocused : {}) }} />
  </div>
);

const G = {
  root: { position: "fixed", inset: 0, display: "flex", fontFamily: "'DM Sans',sans-serif", overflow: "hidden", background: "#f0f4ff" },

  // Background
  bgMesh: { position: "absolute", inset: 0, background: "linear-gradient(135deg, #e8f0fe 0%, #f0f4ff 30%, #fef3f2 60%, #f0fdf4 100%)", zIndex: 0 },
  bgGlow1: { position: "absolute", width: 600, height: 600, borderRadius: "50%", background: "radial-gradient(circle, rgba(99,102,241,0.12) 0%, transparent 70%)", top: -150, left: "20%", zIndex: 0, animation: "float 10s ease-in-out infinite" },
  bgGlow2: { position: "absolute", width: 400, height: 400, borderRadius: "50%", background: "radial-gradient(circle, rgba(16,185,129,0.1) 0%, transparent 70%)", bottom: -80, right: "10%", zIndex: 0, animation: "float 13s ease-in-out infinite", animationDelay: "2s" },
  bgGlow3: { position: "absolute", width: 300, height: 300, borderRadius: "50%", background: "radial-gradient(circle, rgba(245,101,101,0.08) 0%, transparent 70%)", top: "40%", left: "5%", zIndex: 0, animation: "float 8s ease-in-out infinite", animationDelay: "1s" },

  // Particles
  particlesWrap: { position: "absolute", inset: 0, pointerEvents: "none", zIndex: 1 },
  particle: { position: "absolute", borderRadius: "50%", background: "#6366f1", animation: "particleDrift 5s ease-in-out infinite" },

  // Left panel
  leftPanel: { width: "45%", display: "flex", alignItems: "center", justifyContent: "center", position: "relative", zIndex: 2, transition: "all 0.7s cubic-bezier(0.34,1.56,0.64,1)", padding: "2rem" },
  leftInner: { maxWidth: 380 },
  brandMark: { width: 64, height: 64, position: "relative", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: "1.5rem" },
  brandRing: { position: "absolute", width: 64, height: 64, borderRadius: "50%", background: "rgba(99,102,241,0.15)", animation: "pulse 3s ease-out infinite" },
  brandDot: { width: 22, height: 22, borderRadius: "50%", background: "linear-gradient(135deg, #6366f1, #8b5cf6)", boxShadow: "0 0 20px rgba(99,102,241,0.5)", zIndex: 1 },
  brandName: { fontFamily: "'Syne',sans-serif", fontSize: 52, fontWeight: 800, color: "#111827", lineHeight: 1.0, letterSpacing: "-0.04em", marginBottom: "1rem" },
  brandTagline: { fontSize: 16, color: "#6b7280", lineHeight: 1.6, marginBottom: "2.5rem", fontWeight: 300 },
  statsGrid: { display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: "2rem" },
  statItem: { background: "rgba(255,255,255,0.7)", borderRadius: 12, padding: "14px 12px", backdropFilter: "blur(8px)", border: "1px solid rgba(255,255,255,0.9)" },
  statNum: { fontFamily: "'Syne',sans-serif", fontSize: 22, fontWeight: 800, color: "#111827", letterSpacing: "-0.03em" },
  statLabel: { fontSize: 11, color: "#9ca3af", marginTop: 3, lineHeight: 1.3 },
  techStack: { display: "flex", gap: 8, flexWrap: "wrap" },
  techBadge: { fontSize: 11, fontWeight: 600, color: "#6366f1", background: "rgba(99,102,241,0.1)", border: "1px solid rgba(99,102,241,0.2)", borderRadius: 99, padding: "4px 10px", letterSpacing: "0.02em" },

  // Right panel
  rightPanel: { width: "55%", display: "flex", alignItems: "center", justifyContent: "center", position: "relative", zIndex: 2, padding: "2rem" },
  card: { width: "100%", maxWidth: 440, background: "rgba(255,255,255,0.85)", borderRadius: 24, padding: "2.5rem 2.25rem 2rem", backdropFilter: "blur(20px)", border: "1px solid rgba(255,255,255,0.9)", boxShadow: "0 4px 6px rgba(0,0,0,0.04), 0 20px 60px rgba(99,102,241,0.08), 0 0 0 1px rgba(255,255,255,0.5)", transition: "opacity 0.6s ease, transform 0.6s ease" },

  // Mobile logo (hidden on desktop via inline)
  mobileLogo: { display: "none" },
  mobileLogoDot: {},
  mobileLogoName: {},

  cardHeader: { marginBottom: "1.5rem" },
  cardTitle: { fontFamily: "'Syne',sans-serif", fontSize: 26, fontWeight: 800, color: "#111827", letterSpacing: "-0.03em", marginBottom: 6 },
  cardSub: { fontSize: 14, color: "#9ca3af", fontWeight: 300 },

  tabs: { display: "flex", background: "#f3f4f6", borderRadius: 12, padding: 4, marginBottom: "1.5rem", gap: 4 },
  tab: { flex: 1, background: "transparent", border: "none", color: "#9ca3af", fontSize: 13.5, fontWeight: 500, padding: "8px 0", borderRadius: 9, transition: "all 0.2s" },
  tabActive: { background: "#fff", color: "#111827", boxShadow: "0 1px 4px rgba(0,0,0,0.08)" },

  form: { display: "flex", flexDirection: "column", gap: 14 },
  fieldWrap: { display: "flex", flexDirection: "column", gap: 5 },
  label: { fontSize: 12, fontWeight: 600, color: "#374151", letterSpacing: "0.01em" },
  input: { background: "#f9fafb", border: "1.5px solid #e5e7eb", borderRadius: 10, padding: "11px 14px", fontSize: 14, color: "#111827", transition: "all 0.2s", fontFamily: "'DM Sans',sans-serif" },
  inputFocused: { border: "1.5px solid #6366f1", background: "#fafafe", boxShadow: "0 0 0 3px rgba(99,102,241,0.1)" },

  errorBox: { background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 10, padding: "10px 14px", fontSize: 13, color: "#dc2626", display: "flex", gap: 8, alignItems: "center" },
  successBox: { background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 10, padding: "10px 14px", fontSize: 13, color: "#16a34a", display: "flex", gap: 8, alignItems: "center" },

  submitBtn: { background: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)", color: "#fff", border: "none", borderRadius: 12, padding: "13px 0", fontSize: 14, fontWeight: 600, cursor: "pointer", fontFamily: "'Syne',sans-serif", letterSpacing: "-0.01em", transition: "all 0.2s", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, marginTop: 4, boxShadow: "0 4px 20px rgba(99,102,241,0.35)" },
  spinner: { width: 16, height: 16, border: "2px solid rgba(255,255,255,0.35)", borderTop: "2px solid #fff", borderRadius: "50%", animation: "spin 0.7s linear infinite", display: "inline-block", flexShrink: 0 },
  hint: { textAlign: "center", fontSize: 12, color: "#9ca3af" },
  code: { background: "#f3f4f6", padding: "2px 7px", borderRadius: 5, fontSize: 12, fontFamily: "monospace", color: "#374151", border: "1px solid #e5e7eb" },
};