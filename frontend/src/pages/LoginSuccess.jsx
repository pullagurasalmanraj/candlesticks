import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

export default function LoginSuccess() {
    const navigate = useNavigate();
    const [status, setStatus] = useState("Signing you in…");

    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        const token  = params.get("token");
        const code   = params.get("code");
        const via    = params.get("via");
        const user   = params.get("user");

        // ── DEBUG: log what params arrived ────────────────────────
        console.log("[LoginSuccess] params →", {
            via, user, token: token ? "present" : null, code: code ? "present" : null
        });

        // ── Google OAuth callback ──────────────────────────────────
        // Arrives here when Flask google_callback does:
        // return redirect(f"/login-success?via=google&user={quote(email)}")
        if (via === "google" && user) {
            setStatus("Google sign-in successful…");
            localStorage.setItem("user",          decodeURIComponent(user));
            localStorage.setItem("hasRegistered", "true");
            navigate("/brokers", { replace: true });
            return;
        }

        // ── Upstox token callback ──────────────────────────────────
        // Arrives here when Flask root_or_callback does:
        // return redirect(f"/login-success?token={data['access_token']}")
        if (token) {
            setStatus("Upstox connected…");
            localStorage.setItem("upstox_access_token", token);
            localStorage.setItem(
                "upstox_token_expiry",
                (Date.now() + 24 * 60 * 60 * 1000).toString()
            );
            navigate("/", { replace: true });
            return;
        }

        // ── Upstox code fallback ───────────────────────────────────
        if (code) {
            window.location.href = `/enter-code?code=${code}`;
            return;
        }

        // ── No params — check what we have and route accordingly ──
        // This happens if Flask still redirects to /login-success without params
        // OR if the user navigates here directly
        console.warn("[LoginSuccess] No OAuth params found in URL. Check app.py google_callback redirect.");
        setStatus("Checking session…");
        const hasToken = localStorage.getItem("upstox_access_token");
        const hasUser  = localStorage.getItem("user");
        navigate(hasToken ? "/" : hasUser ? "/brokers" : "/login", { replace: true });

    }, [navigate]);

    return (
        <div style={{
            position:       "fixed",
            inset:          0,
            display:        "flex",
            alignItems:     "center",
            justifyContent: "center",
            background:     "var(--bg-primary)",
        }}>
            <div style={{
                display:        "flex",
                flexDirection:  "column",
                alignItems:     "center",
                gap:            20,
                padding:        "48px 40px",
                borderRadius:   "var(--card-radius)",
                background:     "var(--bg-secondary)",
                border:         "1px solid var(--border-color)",
                boxShadow:      "var(--shadow-card-hover)",
                minWidth:       320,
                textAlign:      "center",
            }}>
                {/* Logo */}
                <div style={{
                    width: 44, height: 44, borderRadius: 12,
                    background: "linear-gradient(135deg, var(--accent-blue), var(--accent-up))",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: "1.2rem",
                }}>
                    📈
                </div>

                {/* Spinner */}
                <div style={{
                    width: 36, height: 36, borderRadius: "50%",
                    border: "3px solid var(--bg-tertiary)",
                    borderTop: "3px solid var(--accent-blue)",
                    animation: "lsSpin 0.75s linear infinite",
                    boxShadow: "var(--shadow-glow-blue)",
                }} />

                {/* Status text */}
                <div>
                    <div style={{
                        fontSize: "1rem", fontWeight: 700,
                        fontFamily: "var(--font-display)",
                        color: "var(--text-primary)", marginBottom: 6,
                    }}>
                        {status}
                    </div>
                    <div style={{
                        fontSize: "0.78rem", color: "var(--text-muted)",
                        fontFamily: "var(--font-body)",
                    }}>
                        Verifying your credentials, please wait.
                    </div>
                </div>

                {/* Progress bar */}
                <div style={{
                    width: "100%", height: 3, borderRadius: 999,
                    background: "var(--bg-tertiary)", overflow: "hidden",
                }}>
                    <div style={{
                        height: "100%",
                        background: "linear-gradient(90deg, var(--accent-blue), var(--accent-up))",
                        animation: "lsProgress 1.5s ease-in-out infinite",
                        borderRadius: 999,
                    }} />
                </div>
            </div>

            <style>{`
                @keyframes lsSpin    { to { transform: rotate(360deg); } }
                @keyframes lsProgress {
                    0%   { width: 0%;   margin-left: 0;    }
                    50%  { width: 60%;  margin-left: 20%;  }
                    100% { width: 0%;   margin-left: 100%; }
                }
            `}</style>
        </div>
    );
}
