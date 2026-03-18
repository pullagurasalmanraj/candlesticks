import React, { useState, useRef, useEffect } from "react";
import { useTheme } from "../context/ThemeContext";

// ── Helpers ──────────────────────────────────────────────────────
function getInitials(name) {
    if (!name) return "??";
    return name.trim().split(/\s+/).map(w => w[0]).join("").slice(0, 2).toUpperCase();
}

function loadProfile() {
    try {
        const saved = localStorage.getItem("userProfile");
        return saved ? JSON.parse(saved) : {};
    } catch { return {}; }
}

function saveProfile(data) {
    localStorage.setItem("userProfile", JSON.stringify(data));
}

// ── Avatar display (shared between drawer + header) ──────────────
export function Avatar({ size = 34, onClick, style = {} }) {
    const profile  = loadProfile();
    const username = localStorage.getItem("user") || "Trader";
    const initials = getInitials(profile.displayName || username);
    const photo    = profile.photo || null;

    return (
        <div
            onClick={onClick}
            title="View profile"
            style={{
                width:          size, height: size,
                borderRadius:   "50%",
                background:     photo ? "transparent"
                    : "linear-gradient(135deg, var(--accent-blue), var(--accent-up))",
                display:        "flex",
                alignItems:     "center",
                justifyContent: "center",
                fontSize:       size * 0.3 + "px",
                fontWeight:     700,
                color:          "#fff",
                fontFamily:     "var(--font-display)",
                cursor:         onClick ? "pointer" : "default",
                flexShrink:     0,
                overflow:       "hidden",
                border:         "2px solid var(--border-color)",
                transition:     "border-color 0.15s ease",
                ...style,
            }}
            onMouseEnter={e => { if (onClick) e.currentTarget.style.borderColor = "var(--accent-blue)"; }}
            onMouseLeave={e => { if (onClick) e.currentTarget.style.borderColor = "var(--border-color)"; }}
        >
            {photo
                ? <img src={photo} alt="avatar" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                : initials
            }
        </div>
    );
}

// ── Field row ────────────────────────────────────────────────────
function Field({ label, value, onChange, type = "text", placeholder, readOnly }) {
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            <label style={{
                fontSize:      "0.65rem",
                fontWeight:    700,
                textTransform: "uppercase",
                letterSpacing: "0.07em",
                color:         "var(--text-muted)",
                fontFamily:    "var(--font-body)",
            }}>
                {label}
            </label>
            <input
                type={type}
                value={value}
                onChange={onChange}
                placeholder={placeholder}
                readOnly={readOnly}
                style={{
                    width:        "100%",
                    height:       36,
                    borderRadius: "var(--input-radius)",
                    border:       "1px solid var(--border-color)",
                    background:   readOnly ? "var(--bg-tertiary)" : "var(--bg-tertiary)",
                    color:        readOnly ? "var(--text-muted)"  : "var(--text-primary)",
                    padding:      "0 12px",
                    fontSize:     "0.82rem",
                    fontFamily:   "var(--font-body)",
                    outline:      "none",
                    boxSizing:    "border-box",
                    transition:   "border-color 0.15s ease",
                    cursor:       readOnly ? "not-allowed" : "text",
                }}
                onFocus={e  => { if (!readOnly) e.target.style.borderColor = "var(--accent-blue)"; }}
                onBlur={e   => e.target.style.borderColor = "var(--border-color)"}
            />
        </div>
    );
}

// ── Main drawer ──────────────────────────────────────────────────
export default function ProfileDrawer({ open, onClose }) {
    const { theme, toggleTheme } = useTheme();
    const fileRef   = useRef(null);
    const drawerRef = useRef(null);

    const username = localStorage.getItem("user") || "Trader";
    const profile  = loadProfile();

    const [form, setForm] = useState({
        displayName: profile.displayName || username,
        email:       profile.email       || (username.includes("@") ? username : ""),
        phone:       profile.phone       || "",
        broker:      profile.broker      || "",
        photo:       profile.photo       || null,
    });

    const [saved,    setSaved]    = useState(false);
    const [photoErr, setPhotoErr] = useState("");

    // Close on outside click
    useEffect(() => {
        if (!open) return;
        function handler(e) {
            if (drawerRef.current && !drawerRef.current.contains(e.target)) {
                onClose();
            }
        }
        document.addEventListener("mousedown", handler);
        return () => document.removeEventListener("mousedown", handler);
    }, [open, onClose]);

    // Close on Escape
    useEffect(() => {
        if (!open) return;
        function handler(e) { if (e.key === "Escape") onClose(); }
        document.addEventListener("keydown", handler);
        return () => document.removeEventListener("keydown", handler);
    }, [open, onClose]);

    const handlePhoto = (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        if (file.size > 2 * 1024 * 1024) {
            setPhotoErr("Max file size is 2MB");
            return;
        }
        setPhotoErr("");
        const reader = new FileReader();
        reader.onload = (ev) => setForm(p => ({ ...p, photo: ev.target.result }));
        reader.readAsDataURL(file);
    };

    const handleSave = () => {
        saveProfile(form);
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
    };

    const handleSignOut = () => {
        localStorage.clear();
        window.location.href = "/login";
    };

    const initials = getInitials(form.displayName || username);

    if (!open) return null;

    return (
        <>
            {/* Backdrop */}
            <div style={{
                position:   "fixed",
                inset:      0,
                background: "rgba(0,0,0,0.4)",
                zIndex:     998,
                animation:  "fadeInBd 0.2s ease",
            }} />

            {/* Drawer */}
            <div
                ref={drawerRef}
                style={{
                    position:      "fixed",
                    top:           0,
                    right:         0,
                    bottom:        0,
                    width:         360,
                    background:    "var(--bg-secondary)",
                    borderLeft:    "1px solid var(--border-color)",
                    zIndex:        999,
                    display:       "flex",
                    flexDirection: "column",
                    boxShadow:     "-8px 0 32px rgba(0,0,0,0.3)",
                    animation:     "slideInDrawer 0.25s ease",
                }}
            >
                {/* ── Top accent bar */}
                <div style={{
                    height:     3,
                    background: "linear-gradient(90deg, var(--accent-blue), var(--accent-up))",
                    flexShrink: 0,
                }} />

                {/* ── Header */}
                <div style={{
                    display:        "flex",
                    alignItems:     "center",
                    justifyContent: "space-between",
                    padding:        "16px 20px",
                    borderBottom:   "1px solid var(--border-color)",
                    flexShrink:     0,
                }}>
                    <div>
                        <div style={{
                            fontSize:      "1rem",
                            fontWeight:    700,
                            fontFamily:    "var(--font-display)",
                            color:         "var(--text-primary)",
                            letterSpacing: "-0.01em",
                        }}>
                            Profile
                        </div>
                        <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", fontFamily: "var(--font-body)" }}>
                            Manage your account
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        style={{
                            width: 30, height: 30, borderRadius: 7,
                            border:     "1px solid var(--border-color)",
                            background: "transparent",
                            color:      "var(--text-muted)",
                            cursor:     "pointer",
                            fontSize:   "1rem",
                            display:    "flex", alignItems: "center", justifyContent: "center",
                        }}
                        onMouseEnter={e => e.currentTarget.style.background = "var(--bg-tertiary)"}
                        onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                    >
                        ✕
                    </button>
                </div>

                {/* ── Scrollable body */}
                <div style={{ flex: 1, overflowY: "auto", padding: "20px" }}>

                    {/* Avatar section */}
                    <div style={{
                        display:        "flex",
                        flexDirection:  "column",
                        alignItems:     "center",
                        gap:            12,
                        padding:        "20px 0 24px",
                        borderBottom:   "1px solid var(--border-subtle)",
                        marginBottom:   20,
                    }}>
                        {/* Photo circle */}
                        <div
                            onClick={() => fileRef.current?.click()}
                            style={{
                                width:          80, height: 80,
                                borderRadius:   "50%",
                                background:     form.photo ? "transparent"
                                    : "linear-gradient(135deg, var(--accent-blue), var(--accent-up))",
                                display:        "flex",
                                alignItems:     "center",
                                justifyContent: "center",
                                fontSize:       "1.8rem",
                                fontWeight:     700,
                                color:          "#fff",
                                fontFamily:     "var(--font-display)",
                                cursor:         "pointer",
                                overflow:       "hidden",
                                border:         "3px solid var(--border-color)",
                                position:       "relative",
                                transition:     "border-color 0.15s ease",
                            }}
                            onMouseEnter={e => e.currentTarget.style.borderColor = "var(--accent-blue)"}
                            onMouseLeave={e => e.currentTarget.style.borderColor = "var(--border-color)"}
                        >
                            {form.photo
                                ? <img src={form.photo} alt="avatar"
                                    style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                                : initials
                            }
                            {/* Hover overlay */}
                            <div style={{
                                position:       "absolute",
                                inset:          0,
                                background:     "rgba(0,0,0,0.45)",
                                display:        "flex",
                                alignItems:     "center",
                                justifyContent: "center",
                                opacity:        0,
                                transition:     "opacity 0.15s ease",
                                fontSize:       "0.7rem",
                                fontFamily:     "var(--font-body)",
                                fontWeight:     600,
                                color:          "#fff",
                                borderRadius:   "50%",
                            }}
                            onMouseEnter={e => e.currentTarget.style.opacity = "1"}
                            onMouseLeave={e => e.currentTarget.style.opacity = "0"}
                            >
                                📷 Change
                            </div>
                        </div>

                        <input
                            ref={fileRef}
                            type="file"
                            accept="image/*"
                            style={{ display: "none" }}
                            onChange={handlePhoto}
                        />

                        {photoErr && (
                            <span style={{ fontSize: "0.72rem", color: "var(--accent-down)", fontFamily: "var(--font-body)" }}>
                                {photoErr}
                            </span>
                        )}

                        <div style={{ textAlign: "center" }}>
                            <div style={{
                                fontSize:      "1rem",
                                fontWeight:    700,
                                fontFamily:    "var(--font-display)",
                                color:         "var(--text-primary)",
                                letterSpacing: "-0.01em",
                            }}>
                                {form.displayName || username}
                            </div>
                            <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)", marginTop: 3 }}>
                                {username}
                            </div>
                        </div>

                        {/* Remove photo */}
                        {form.photo && (
                            <button
                                onClick={() => setForm(p => ({ ...p, photo: null }))}
                                style={{
                                    fontSize:     "0.72rem",
                                    padding:      "4px 12px",
                                    borderRadius: 6,
                                    border:       "1px solid rgba(255,82,82,0.3)",
                                    background:   "rgba(255,82,82,0.08)",
                                    color:        "var(--accent-down)",
                                    cursor:       "pointer",
                                    fontFamily:   "var(--font-body)",
                                    fontWeight:   600,
                                }}
                            >
                                Remove photo
                            </button>
                        )}
                    </div>

                    {/* Form fields */}
                    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>

                        <Field
                            label="Display Name"
                            value={form.displayName}
                            onChange={e => setForm(p => ({ ...p, displayName: e.target.value }))}
                            placeholder="Your name"
                        />
                        <Field
                            label="Username / Login"
                            value={username}
                            readOnly
                            placeholder="Username"
                        />
                        <Field
                            label="Email"
                            type="email"
                            value={form.email}
                            onChange={e => setForm(p => ({ ...p, email: e.target.value }))}
                            placeholder="you@email.com"
                        />
                        <Field
                            label="Phone"
                            type="tel"
                            value={form.phone}
                            onChange={e => setForm(p => ({ ...p, phone: e.target.value }))}
                            placeholder="+91 9876543210"
                        />
                        <Field
                            label="Preferred Broker"
                            value={form.broker}
                            onChange={e => setForm(p => ({ ...p, broker: e.target.value }))}
                            placeholder="e.g. Upstox"
                        />

                        {/* Theme toggle */}
                        <div style={{
                            display:        "flex",
                            alignItems:     "center",
                            justifyContent: "space-between",
                            padding:        "12px 14px",
                            borderRadius:   "var(--input-radius)",
                            background:     "var(--bg-tertiary)",
                            border:         "1px solid var(--border-subtle)",
                            marginTop:      4,
                        }}>
                            <div>
                                <div style={{ fontSize: "0.82rem", fontWeight: 600, color: "var(--text-primary)", fontFamily: "var(--font-body)" }}>
                                    {theme === "dark" ? "🌙 Dark Mode" : "☀️ Light Mode"}
                                </div>
                                <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", fontFamily: "var(--font-body)" }}>
                                    Switch app theme
                                </div>
                            </div>
                            <button
                                onClick={toggleTheme}
                                style={{
                                    width:        44, height: 24,
                                    borderRadius: 999,
                                    border:       "none",
                                    background:   theme === "dark" ? "var(--accent-blue)" : "var(--bg-secondary)",
                                    cursor:       "pointer",
                                    position:     "relative",
                                    transition:   "background 0.2s ease",
                                    boxShadow:    "inset 0 0 0 1px var(--border-color)",
                                }}
                            >
                                <div style={{
                                    position:   "absolute",
                                    top:        3, left: theme === "dark" ? 23 : 3,
                                    width:      18, height: 18,
                                    borderRadius:"50%",
                                    background: theme === "dark" ? "#fff" : "var(--accent-blue)",
                                    transition: "left 0.2s ease",
                                }} />
                            </button>
                        </div>
                    </div>
                </div>

                {/* ── Footer actions */}
                <div style={{
                    padding:      "16px 20px",
                    borderTop:    "1px solid var(--border-color)",
                    display:      "flex",
                    flexDirection:"column",
                    gap:          8,
                    flexShrink:   0,
                }}>
                    {/* Save button */}
                    <button
                        onClick={handleSave}
                        style={{
                            width:        "100%",
                            height:       38,
                            borderRadius: "var(--button-radius)",
                            border:       "none",
                            background:   saved ? "var(--accent-up)" : "var(--accent-blue)",
                            color:        "#fff",
                            fontSize:     "0.875rem",
                            fontWeight:   600,
                            fontFamily:   "var(--font-body)",
                            cursor:       "pointer",
                            transition:   "all 0.2s ease",
                            boxShadow:    saved ? "var(--shadow-glow-green)" : "var(--shadow-glow-blue)",
                        }}
                    >
                        {saved ? "✓ Saved!" : "Save Changes"}
                    </button>

                    {/* Sign out */}
                    <button
                        onClick={handleSignOut}
                        style={{
                            width:        "100%",
                            height:       36,
                            borderRadius: "var(--button-radius)",
                            border:       "1px solid rgba(255,82,82,0.3)",
                            background:   "rgba(255,82,82,0.06)",
                            color:        "var(--accent-down)",
                            fontSize:     "0.82rem",
                            fontWeight:   600,
                            fontFamily:   "var(--font-body)",
                            cursor:       "pointer",
                            transition:   "all 0.15s ease",
                        }}
                        onMouseEnter={e => e.currentTarget.style.background = "rgba(255,82,82,0.14)"}
                        onMouseLeave={e => e.currentTarget.style.background = "rgba(255,82,82,0.06)"}
                    >
                        Sign Out
                    </button>
                </div>
            </div>

            <style>{`
                @keyframes fadeInBd     { from { opacity: 0; } to { opacity: 1; } }
                @keyframes slideInDrawer {
                    from { transform: translateX(100%); opacity: 0; }
                    to   { transform: translateX(0);    opacity: 1; }
                }
            `}</style>
        </>
    );
}
