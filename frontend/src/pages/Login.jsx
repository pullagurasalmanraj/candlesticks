import React, { useState, useEffect } from "react";
import CandleBackground from "../components/CandleBackground";
import Navbar from "../components/Navbar";
import { useTheme } from "../context/ThemeContext";

import {
    TextField, Button,
    Typography, Box, Divider,
    InputAdornment, IconButton, LinearProgress,
    Alert, Collapse
} from "@mui/material";

import CheckCircleIcon    from "@mui/icons-material/CheckCircle";
import GoogleIcon         from "@mui/icons-material/Google";
import PersonAddIcon      from "@mui/icons-material/PersonAdd";
import LoginIcon          from "@mui/icons-material/Login";
import VisibilityIcon     from "@mui/icons-material/Visibility";
import VisibilityOffIcon  from "@mui/icons-material/VisibilityOff";
import PersonOutlineIcon  from "@mui/icons-material/PersonOutline";
import LockOutlinedIcon   from "@mui/icons-material/LockOutlined";
import TrendingUpIcon     from "@mui/icons-material/TrendingUp";
import BarChartIcon       from "@mui/icons-material/BarChart";
import BoltIcon           from "@mui/icons-material/Bolt";
import SmartToyIcon       from "@mui/icons-material/SmartToy";

// ── Password strength scorer ─────────────────────────────────────
function getPasswordStrength(pwd) {
    if (!pwd) return { score: 0, label: "", color: "transparent" };
    let score = 0;
    if (pwd.length >= 6)  score++;
    if (pwd.length >= 10) score++;
    if (/[A-Z]/.test(pwd))           score++;
    if (/[0-9]/.test(pwd))           score++;
    if (/[^A-Za-z0-9]/.test(pwd))    score++;
    const map = [
        { label: "",         color: "transparent" },
        { label: "Weak",     color: "#ff5252"      },
        { label: "Fair",     color: "#ffd54f"      },
        { label: "Good",     color: "#4f9eff"      },
        { label: "Strong",   color: "#00e676"      },
        { label: "Excellent",color: "#00e676"      },
    ];
    return { score, ...map[score] };
}

// ── Inline field validator ───────────────────────────────────────
function validate(field, value, confirmValue) {
    if (field === "username") {
        if (!value)           return "Username is required";
        if (value.length < 3) return "At least 3 characters";
        if (!/^[a-zA-Z0-9_]+$/.test(value)) return "Only letters, numbers, underscores";
    }
    if (field === "password") {
        if (!value)           return "Password is required";
        if (value.length < 6) return `${6 - value.length} more character${6 - value.length > 1 ? "s" : ""} needed`;
    }
    if (field === "confirm") {
        if (!value)              return "Please confirm your password";
        if (value !== confirmValue) return "Passwords do not match";
    }
    return "";
}

// ── Feature list ─────────────────────────────────────────────────
const FEATURES = [
    { icon: <BarChartIcon sx={{ fontSize: 18 }} />,  text: "Real-time market ticks"      },
    { icon: <TrendingUpIcon sx={{ fontSize: 18 }} />, text: "Advanced indicator engine"  },
    { icon: <BoltIcon sx={{ fontSize: 18 }} />,       text: "Strategy backtesting"        },
    { icon: <SmartToyIcon sx={{ fontSize: 18 }} />,   text: "AI powered predictions"      },
];

import { Navigate, useNavigate } from "react-router-dom";

export default function AuthPage() {
    const { theme } = useTheme();
    const navigate  = useNavigate();

    // ── Returning user detection ───────────────────────────────
    // hasRegistered is set to "true" after first successful signup/login
    // Once set, signup tab is hidden and logged-in users skip this page
    const isReturningUser = !!localStorage.getItem("hasRegistered");
    const isLoggedIn      = !!localStorage.getItem("user");

    // Already logged in → skip straight to brokers
    if (isLoggedIn) return <Navigate to="/brokers" replace />;

    const [tab,           setTab]           = useState("login");
    const [username,      setUsername]      = useState("");
    const [password,      setPassword]      = useState("");
    const [confirm,       setConfirm]       = useState("");
    const [showPassword,  setShowPassword]  = useState(false);
    const [showConfirm,   setShowConfirm]   = useState(false);
    const [touched,       setTouched]       = useState({});
    const [loading,       setLoading]       = useState(false);
    const [apiError,      setApiError]      = useState("");

    const strength = getPasswordStrength(password);

    // Errors only shown after field is touched
    const errors = {
        username: touched.username ? validate("username", username)        : "",
        password: touched.password ? validate("password", password)        : "",
        confirm:  touched.confirm  ? validate("confirm",  confirm, password) : "",
    };

    const isLoginValid  = !errors.username && !errors.password && username && password;
    const isSignupValid = isLoginValid && !errors.confirm && confirm;

    const touch = (field) => setTouched((p) => ({ ...p, [field]: true }));

    const handleTabChange = (_, v) => {
        setTab(v);
        setTouched({});
        setApiError("");
        setConfirm("");
    };

    // ── Login ──────────────────────────────────────────────────
    const handleLogin = async () => {
        setTouched({ username: true, password: true });
        if (!isLoginValid) return;
        setLoading(true);
        setApiError("");
        try {
            const res  = await fetch("/api/login", {
                method:  "POST",
                headers: { "Content-Type": "application/json" },
                body:    JSON.stringify({ username, password }),
            });
            const data = await res.json();
            if (!res.ok) { setApiError(data.error || "Login failed"); return; }
            localStorage.setItem("user", username);
            localStorage.setItem("hasRegistered", "true");
            navigate("/brokers", { replace: true });
        } catch {
            setApiError("Network error. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    // ── Signup ─────────────────────────────────────────────────
    const handleSignup = async () => {
        setTouched({ username: true, password: true, confirm: true });
        if (!isSignupValid) return;
        setLoading(true);
        setApiError("");
        try {
            const res  = await fetch("/api/signup", {
                method:  "POST",
                headers: { "Content-Type": "application/json" },
                body:    JSON.stringify({ username, password }),
            });
            const data = await res.json();
            if (!res.ok) { setApiError(data.error || "Signup failed"); return; }
            localStorage.setItem("user",          username);
            localStorage.setItem("hasRegistered", "true");
            navigate("/brokers", { replace: true });
        } catch {
            setApiError("Network error. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    // ── Show error if Google OAuth failed and redirected back ───
    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        if (params.get("error") === "google_failed") {
            setApiError("Google sign-in failed. Please try again.");
            // Clean the URL so refreshing doesn't re-show the error
            window.history.replaceState({}, "", "/login");
        }
    }, []);

    // ── Google OAuth ─────────────────────────────────────────────
    const loginGoogle = () => {
        window.location.href = "/auth/google";
    };

    // ── Enter key support ──────────────────────────────────────
    const handleKeyDown = (e) => {
        if (e.key === "Enter") tab === "login" ? handleLogin() : handleSignup();
    };

    return (
        <div
            className="relative w-full min-h-screen"
            style={{ background: "var(--bg-primary)", color: "var(--text-primary)" }}
        >
            <CandleBackground />
            <Navbar />

            <div
                className="grid grid-cols-1 lg:grid-cols-2"
                style={{ minHeight: "calc(100vh - var(--navbar-height))" }}
            >
                {/* ── HERO ───────────────────────────────────── */}
                <div className="relative z-10 flex flex-col justify-center px-12 xl:px-20 py-16"
                    style={{ color: "var(--text-primary)" }}
                >

                    {/* Pill badge */}
                    <div style={{
                        display: "inline-flex", alignItems: "center", gap: 6,
                        background: "var(--accent-blue-muted)",
                        border: "1px solid var(--accent-blue)",
                        borderRadius: 999, padding: "4px 14px",
                        width: "fit-content", marginBottom: 24,
                    }}>
                        <span style={{
                            width: 7, height: 7, borderRadius: "50%",
                            background: "var(--accent-blue)",
                            boxShadow: "0 0 8px var(--accent-blue)",
                            animation: "pulse 2s infinite"
                        }} />
                        <span style={{ fontSize: 12, color: "var(--accent-blue)", fontWeight: 600, letterSpacing: "0.05em" }}>
                            LIVE MARKETS
                        </span>
                    </div>

                    <h1 style={{
                        fontFamily: "var(--font-display)",
                        fontSize: "clamp(2.4rem, 4vw, 3.5rem)",
                        fontWeight: 700,
                        color: "var(--text-primary)",
                        letterSpacing: "-0.03em",
                        lineHeight: 1.1,
                        marginBottom: 20,
                    }}>
                        Trade smarter.<br />
                        <span style={{ color: "var(--accent-blue)" }}>React faster.</span>
                    </h1>

                    <p style={{
                        fontSize: "1rem",
                        color: "var(--text-secondary)",
                        maxWidth: 420,
                        lineHeight: 1.7,
                        marginBottom: 40,
                    }}>
                        Professional trading analytics powered by real-time market data,
                        algorithmic indicators, and AI-driven insights.
                    </p>

                    {/* Feature list */}
                    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                        {FEATURES.map(({ icon, text }) => (
                            <div key={text} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                                <div style={{
                                    width: 34, height: 34, borderRadius: 8,
                                    background: "var(--accent-blue-muted)",
                                    border: "1px solid var(--border-subtle)",
                                    display: "flex", alignItems: "center", justifyContent: "center",
                                    color: "var(--accent-blue)", flexShrink: 0,
                                }}>
                                    {icon}
                                </div>
                                <span style={{ fontSize: "0.9rem", color: "var(--text-secondary)" }}>
                                    {text}
                                </span>
                            </div>
                        ))}
                    </div>

                    {/* Stats row */}
                    <div style={{
                        display: "flex", gap: 32, marginTop: 48,
                        paddingTop: 32, borderTop: "1px solid var(--border-subtle)"
                    }}>
                        {[["50K+", "Active traders"], ["1.2M+", "Trades daily"], ["99.9%", "Uptime"]].map(([val, label]) => (
                            <div key={label}>
                                <div style={{ fontFamily: "var(--font-mono)", fontSize: "1.3rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                    {val}
                                </div>
                                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: 2 }}>
                                    {label}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* ── AUTH CARD ──────────────────────────────── */}
                <div className="relative z-10 flex items-center justify-center px-6 py-16">
                    <div style={{ width: "100%", maxWidth: 440 }}>

                        {/* Card */}
                        <div style={{
                            background: "var(--bg-secondary)",
                            border: "1px solid var(--border-color)",
                            borderRadius: 16,
                            boxShadow: theme === "dark"
                                ? "0 24px 64px rgba(0,0,0,0.5), 0 0 0 1px var(--border-subtle)"
                                : "0 24px 64px rgba(0,0,0,0.1)",
                            overflow: "hidden",
                        }}>

                            {/* Top accent bar */}
                            <div style={{
                                height: 3,
                                background: "linear-gradient(90deg, var(--accent-blue), var(--accent-up))",
                            }} />

                            <div style={{ padding: "32px 32px 28px" }}>

                                {/* Header */}
                                <div style={{ marginBottom: 24 }}>
                                    <Typography variant="h5" sx={{
                                        fontFamily: "var(--font-display)",
                                        fontWeight: 700,
                                        color: "var(--text-primary)",
                                        letterSpacing: "-0.02em",
                                        mb: 0.5,
                                    }}>
                                        {isReturningUser ? "Welcome back" : (tab === "login" ? "Welcome back" : "Create account")}
                                    </Typography>
                                    <Typography variant="body2" sx={{ color: "var(--text-muted)" }}>
                                        {isReturningUser
                                            ? "Sign in to your trading dashboard"
                                            : tab === "login"
                                                ? "Sign in to your trading dashboard"
                                                : "Start trading in minutes"}
                                    </Typography>
                                </div>

                                {/* Tabs — hidden for returning users, they only see Sign In */}
                                {!isReturningUser && (
                                    <div style={{
                                        display: "flex",
                                        background: "var(--bg-tertiary)",
                                        borderRadius: 10,
                                        padding: 4,
                                        marginBottom: 24,
                                    }}>
                                        {["login", "signup"].map((t) => (
                                            <button
                                                type="button"
                                                key={t}
                                                onClick={() => handleTabChange(null, t)}
                                                style={{
                                                    flex: 1, padding: "8px 0",
                                                    borderRadius: 8, border: "none",
                                                    cursor: "pointer",
                                                    fontFamily: "var(--font-body)",
                                                    fontWeight: 600, fontSize: "0.875rem",
                                                    transition: "all 0.2s ease",
                                                    background: tab === t ? "var(--bg-secondary)" : "transparent",
                                                    color: tab === t ? "var(--text-primary)" : "var(--text-muted)",
                                                    boxShadow: tab === t ? "0 1px 4px rgba(0,0,0,0.15)" : "none",
                                                }}
                                            >
                                                {t === "login" ? "Sign In" : "Sign Up"}
                                            </button>
                                        ))}
                                    </div>
                                )}

                                {/* API Error */}
                                <Collapse in={!!apiError}>
                                    <Alert
                                        severity="error"
                                        sx={{ mb: 2, borderRadius: "var(--input-radius)", fontSize: "0.8rem" }}
                                        onClose={() => setApiError("")}
                                    >
                                        {apiError}
                                    </Alert>
                                </Collapse>

                                {/* Fields */}
                                <Box display="flex" flexDirection="column" gap={2}>

                                    {/* Username */}
                                    <TextField
                                        label="Username"
                                        value={username}
                                        onChange={(e) => setUsername(e.target.value)}
                                        onBlur={() => touch("username")}
                                        onKeyDown={handleKeyDown}
                                        error={!!errors.username}
                                        helperText={errors.username}
                                        fullWidth
                                        size="small"
                                        InputProps={{
                                            startAdornment: (
                                                <InputAdornment position="start">
                                                    <PersonOutlineIcon sx={{ fontSize: 18, color: "var(--text-muted)" }} />
                                                </InputAdornment>
                                            ),
                                        }}
                                    />

                                    {/* Password */}
                                    <Box>
                                        <TextField
                                            label="Password"
                                            type={showPassword ? "text" : "password"}
                                            value={password}
                                            onChange={(e) => setPassword(e.target.value)}
                                            onBlur={() => touch("password")}
                                            onKeyDown={handleKeyDown}
                                            error={!!errors.password}
                                            helperText={errors.password || (tab === "signup" && password
                                                ? `Strength: ${strength.label}` : "")}
                                            fullWidth
                                            size="small"
                                            InputProps={{
                                                startAdornment: (
                                                    <InputAdornment position="start">
                                                        <LockOutlinedIcon sx={{ fontSize: 18, color: "var(--text-muted)" }} />
                                                    </InputAdornment>
                                                ),
                                                endAdornment: (
                                                    <InputAdornment position="end">
                                                        <IconButton size="small" onClick={() => setShowPassword(!showPassword)} edge="end">
                                                            {showPassword
                                                                ? <VisibilityOffIcon sx={{ fontSize: 18 }} />
                                                                : <VisibilityIcon    sx={{ fontSize: 18 }} />}
                                                        </IconButton>
                                                    </InputAdornment>
                                                ),
                                            }}
                                        />
                                        {/* Strength bar — signup only */}
                                        {tab === "signup" && password && (
                                            <Box mt={0.75} px={0.25}>
                                                <LinearProgress
                                                    variant="determinate"
                                                    value={(strength.score / 5) * 100}
                                                    sx={{
                                                        height: 3, borderRadius: 2,
                                                        backgroundColor: "var(--bg-tertiary)",
                                                        "& .MuiLinearProgress-bar": {
                                                            backgroundColor: strength.color,
                                                            transition: "all 0.3s ease",
                                                        },
                                                    }}
                                                />
                                            </Box>
                                        )}
                                    </Box>

                                    {/* Confirm password — signup only */}
                                    {tab === "signup" && (
                                        <TextField
                                            label="Confirm Password"
                                            type={showConfirm ? "text" : "password"}
                                            value={confirm}
                                            onChange={(e) => setConfirm(e.target.value)}
                                            onBlur={() => touch("confirm")}
                                            onKeyDown={handleKeyDown}
                                            error={!!errors.confirm}
                                            helperText={errors.confirm || (confirm && confirm === password ? "✓ Passwords match" : "")}
                                            FormHelperTextProps={{
                                                sx: { color: confirm && confirm === password ? "var(--accent-up)" : undefined }
                                            }}
                                            fullWidth
                                            size="small"
                                            InputProps={{
                                                startAdornment: (
                                                    <InputAdornment position="start">
                                                        <LockOutlinedIcon sx={{ fontSize: 18, color: "var(--text-muted)" }} />
                                                    </InputAdornment>
                                                ),
                                                endAdornment: (
                                                    <InputAdornment position="end">
                                                        <IconButton size="small" onClick={() => setShowConfirm(!showConfirm)} edge="end">
                                                            {showConfirm
                                                                ? <VisibilityOffIcon sx={{ fontSize: 18 }} />
                                                                : <VisibilityIcon    sx={{ fontSize: 18 }} />}
                                                        </IconButton>
                                                    </InputAdornment>
                                                ),
                                            }}
                                        />
                                    )}

                                    {/* Primary CTA */}
                                    <Button
                                        variant="contained"
                                        startIcon={tab === "login" ? <LoginIcon /> : <PersonAddIcon />}
                                        onClick={tab === "login" ? handleLogin : handleSignup}
                                        disabled={loading}
                                        fullWidth
                                        sx={{
                                            height: 44, mt: 0.5,
                                            fontWeight: 600, fontSize: "0.9rem",
                                        }}
                                    >
                                        {loading
                                            ? (tab === "login" ? "Signing in…" : "Creating account…")
                                            : (tab === "login" ? "Sign In"      : "Create Account")}
                                    </Button>

                                    <Divider sx={{ my: 0.5 }}>
                                        <Typography variant="caption" sx={{ color: "var(--text-muted)", px: 1 }}>
                                            OR CONTINUE WITH
                                        </Typography>
                                    </Divider>

                                    {/* Google button */}
                                    <button
                                        type="button"
                                        onClick={loginGoogle}
                                        style={{
                                            display: "flex", alignItems: "center", justifyContent: "center",
                                            gap: 10, width: "100%", height: 44,
                                            background: "var(--bg-tertiary)",
                                            border: "1px solid var(--border-color)",
                                            borderRadius: "var(--input-radius)",
                                            color: "var(--text-primary)",
                                            fontFamily: "var(--font-body)",
                                            fontSize: "0.875rem", fontWeight: 600,
                                            cursor: "pointer",
                                            transition: "all 0.2s ease",
                                        }}
                                        onMouseEnter={(e) => {
                                            e.currentTarget.style.borderColor = "var(--accent-blue)";
                                            e.currentTarget.style.background  = "var(--accent-blue-muted)";
                                        }}
                                        onMouseLeave={(e) => {
                                            e.currentTarget.style.borderColor = "var(--border-color)";
                                            e.currentTarget.style.background  = "var(--bg-tertiary)";
                                        }}
                                    >
                                        {/* Google colour logo */}
                                        <svg width="18" height="18" viewBox="0 0 24 24">
                                            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                                            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                                            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
                                            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                                        </svg>
                                        Continue with Google
                                    </button>

                                </Box>

                                {/* Footer note */}
                                {tab === "signup" && (
                                    <Typography variant="caption" sx={{
                                        display: "block", textAlign: "center",
                                        mt: 2, color: "var(--text-muted)", lineHeight: 1.5
                                    }}>
                                        By creating an account you agree to our{" "}
                                        <span style={{ color: "var(--accent-blue)", cursor: "pointer" }}>Terms of Service</span>
                                        {" "}and{" "}
                                        <span style={{ color: "var(--accent-blue)", cursor: "pointer" }}>Privacy Policy</span>
                                    </Typography>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Pulse animation for live dot */}
            <style>{`
                @keyframes pulse {
                    0%, 100% { opacity: 1; transform: scale(1); }
                    50%       { opacity: 0.6; transform: scale(1.3); }
                }
            `}</style>
        </div>
    );
}
