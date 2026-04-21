import React, { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import CandleBackground from "../components/CandleBackground";
import Navbar from "../components/Navbar";
import { useTheme } from "../context/ThemeContext";

import {
    Alert,
    Box,
    Button,
    Collapse,
    Divider,
    IconButton,
    InputAdornment,
    LinearProgress,
    TextField,
    Typography,
} from "@mui/material";

import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import PersonAddIcon from "@mui/icons-material/PersonAdd";
import LoginIcon from "@mui/icons-material/Login";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import LockOutlinedIcon from "@mui/icons-material/LockOutlined";

function GoogleLogoIcon() {
    return (
        <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true" focusable="false">
            <path
                fill="#4285F4"
                d="M17.64 9.2045c0-.6382-.0573-1.2518-.1636-1.8409H9v3.4818h4.8436c-.2086 1.125-.8427 2.0782-1.7973 2.7155v2.2582h2.9082c1.7018-1.5664 2.6855-3.8741 2.6855-6.6146Z"
            />
            <path
                fill="#34A853"
                d="M9 18c2.43 0 4.4673-.8064 5.9564-2.1805l-2.9082-2.2582c-.8064.54-1.8377.8591-3.0482.8591-2.3468 0-4.3341-1.5845-5.0432-3.7132H.9573v2.3327C2.4382 15.9827 5.4818 18 9 18Z"
            />
            <path
                fill="#FBBC05"
                d="M3.9568 10.7073A5.409 5.409 0 0 1 3.6745 9c0-.5927.1023-1.1673.2823-1.7073V4.96H.9573A8.996 8.996 0 0 0 0 9c0 1.4523.3477 2.8277.9573 4.04l2.9995-2.3327Z"
            />
            <path
                fill="#EA4335"
                d="M9 3.5795c1.3214 0 2.5077.4541 3.4405 1.3459l2.5814-2.5814C13.4632.8918 11.4259 0 9 0 5.4818 0 2.4382 2.0173.9573 4.96l2.9995 2.3327c.7091-2.1286 2.6964-3.7132 5.0432-3.7132Z"
            />
        </svg>
    );
}

function getPasswordStrength(password) {
    if (!password) return { score: 0, label: "", color: "transparent" };

    let score = 0;
    if (password.length >= 6) score += 1;
    if (password.length >= 10) score += 1;
    if (/[A-Z]/.test(password)) score += 1;
    if (/[0-9]/.test(password)) score += 1;
    if (/[^A-Za-z0-9]/.test(password)) score += 1;

    const map = [
        { label: "", color: "transparent" },
        { label: "Weak", color: "#ff5252" },
        { label: "Fair", color: "#ffd54f" },
        { label: "Good", color: "#4f9eff" },
        { label: "Strong", color: "#00e676" },
        { label: "Excellent", color: "#00e676" },
    ];

    return { score, ...map[score] };
}

function validate(field, value, confirmValue) {
    if (field === "username") {
        if (!value) return "Username is required";
        if (value.length < 3) return "At least 3 characters";
        if (!/^[a-zA-Z0-9_]+$/.test(value)) return "Only letters, numbers, underscores";
    }

    if (field === "password") {
        if (!value) return "Password is required";
        if (value.length < 6) {
            const remaining = 6 - value.length;
            return `${remaining} more character${remaining > 1 ? "s" : ""} needed`;
        }
    }

    if (field === "confirm") {
        if (!value) return "Please confirm your password";
        if (value !== confirmValue) return "Passwords do not match";
    }

    return "";
}

const PROJECT_POINTS = [
    "Unified console for dashboard, watchlist, portfolio, and options workflows",
    "Live feed ingestion, analytics, broker connectivity, and low-latency cache",
    "Built-in strategy lab for rule testing and model-assisted decision support",
];

const PROJECT_STATS = [
    { value: "1.2B+", label: "Ticks processed daily" },
    { value: "85M+", label: "Candles indexed" },
    { value: "20+", label: "Core API routes" },
    { value: "<12ms", label: "Cache response latency" },
];

function AuthCard({
    tab,
    theme,
    username,
    setUsername,
    password,
    setPassword,
    confirm,
    setConfirm,
    showPassword,
    setShowPassword,
    showConfirm,
    setShowConfirm,
    errors,
    touch,
    handleKeyDown,
    strength,
    handleLogin,
    handleSignup,
    loading,
    apiError,
    setApiError,
    loginGoogle,
    isReturningUser,
}) {
    if (!tab) {
        return (
            <div
                style={{
                    background: "var(--bg-secondary)",
                    border: "1px solid var(--border-color)",
                    borderRadius: 16,
                    boxShadow:
                        theme === "dark"
                            ? "0 14px 36px rgba(3, 8, 20, 0.34)"
                            : "0 10px 26px rgba(15, 23, 42, 0.10)",
                    padding: "30px 28px",
                }}
            >
                <Typography
                    sx={{
                        fontFamily: "var(--font-display)",
                        fontSize: "1.55rem",
                        fontWeight: 700,
                        letterSpacing: "-0.02em",
                        color: "var(--text-primary)",
                        lineHeight: 1.15,
                        mb: 1,
                    }}
                >
                    Project brief is visible
                </Typography>
                <Typography sx={{ color: "var(--text-secondary)", lineHeight: 1.7, fontSize: "0.94rem", mb: 2 }}>
                    Use the navbar buttons to open Login or Sign Up.
                    The auth form appears only after you click.
                </Typography>
                <Typography sx={{ color: "var(--text-muted)", fontSize: "0.78rem", letterSpacing: "0.04em" }}>
                    SELECT AN ACTION FROM THE TOP NAVIGATION
                </Typography>
            </div>
        );
    }

    return (
        <div
            style={{
                background: "var(--bg-secondary)",
                border: "1px solid var(--border-color)",
                borderRadius: 16,
                boxShadow:
                    theme === "dark"
                        ? "0 14px 36px rgba(3, 8, 20, 0.40)"
                        : "0 10px 26px rgba(15, 23, 42, 0.11)",
                overflow: "hidden",
            }}
        >
            <div
                style={{
                    height: 3,
                    background: "linear-gradient(90deg, var(--accent-blue), var(--accent-up))",
                }}
            />

            <div style={{ padding: "24px 26px 22px" }}>
                <div style={{ marginBottom: 16 }}>
                    <Typography
                        sx={{
                            fontFamily: "var(--font-display)",
                            fontSize: "1.6rem",
                            fontWeight: 700,
                            letterSpacing: "-0.02em",
                            color: "var(--text-primary)",
                            lineHeight: 1.12,
                            mb: 0.5,
                        }}
                    >
                        {tab === "login" ? "Welcome back" : "Create account"}
                    </Typography>
                    <Typography sx={{ color: "var(--text-muted)", fontSize: "0.88rem" }}>
                        {tab === "login"
                            ? "Sign in to continue to the trading console."
                            : "Sign up to activate your console access."}
                    </Typography>
                    {isReturningUser && tab === "login" && (
                        <Typography sx={{ mt: 1, color: "var(--text-muted)", fontSize: "0.76rem" }}>
                            Returning user detected.
                        </Typography>
                    )}
                </div>

                <Collapse in={!!apiError}>
                    <Alert
                        severity="error"
                        sx={{ mb: 2, borderRadius: "var(--input-radius)", fontSize: "0.78rem" }}
                        onClose={() => setApiError("")}
                    >
                        {apiError}
                    </Alert>
                </Collapse>

                <Box display="flex" flexDirection="column" gap={1.65}>
                    <TextField
                        label="Username"
                        value={username}
                        onChange={(event) => setUsername(event.target.value)}
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

                    <Box>
                        <TextField
                            label="Password"
                            type={showPassword ? "text" : "password"}
                            value={password}
                            onChange={(event) => setPassword(event.target.value)}
                            onBlur={() => touch("password")}
                            onKeyDown={handleKeyDown}
                            error={!!errors.password}
                            helperText={
                                errors.password || (tab === "signup" && password
                                    ? `Strength: ${strength.label}` : "")
                            }
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
                                                : <VisibilityIcon sx={{ fontSize: 18 }} />}
                                        </IconButton>
                                    </InputAdornment>
                                ),
                            }}
                        />
                        {tab === "signup" && password && (
                            <Box mt={0.65} px={0.25}>
                                <LinearProgress
                                    variant="determinate"
                                    value={(strength.score / 5) * 100}
                                    sx={{
                                        height: 3,
                                        borderRadius: 2,
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

                    {tab === "signup" && (
                        <TextField
                            label="Confirm Password"
                            type={showConfirm ? "text" : "password"}
                            value={confirm}
                            onChange={(event) => setConfirm(event.target.value)}
                            onBlur={() => touch("confirm")}
                            onKeyDown={handleKeyDown}
                            error={!!errors.confirm}
                            helperText={errors.confirm || (confirm && confirm === password ? "Passwords match" : "")}
                            FormHelperTextProps={{
                                sx: { color: confirm && confirm === password ? "var(--accent-up)" : undefined },
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
                                                : <VisibilityIcon sx={{ fontSize: 18 }} />}
                                        </IconButton>
                                    </InputAdornment>
                                ),
                            }}
                        />
                    )}

                    <Button
                        variant="contained"
                        startIcon={tab === "login" ? <LoginIcon /> : <PersonAddIcon />}
                        onClick={tab === "login" ? handleLogin : handleSignup}
                        disabled={loading}
                        fullWidth
                        sx={{ height: 42, mt: 0.2, fontWeight: 600, fontSize: "0.88rem" }}
                    >
                        {loading
                            ? (tab === "login" ? "Signing in..." : "Creating account...")
                            : (tab === "login" ? "Sign In" : "Create Account")}
                    </Button>

                    <Divider sx={{ my: 0.2 }}>
                        <Typography variant="caption" sx={{ color: "var(--text-muted)", px: 1 }}>
                            OR CONTINUE WITH
                        </Typography>
                    </Divider>

                    <button
                        type="button"
                        onClick={loginGoogle}
                        style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            gap: 12,
                            width: "100%",
                            height: 48,
                            background: "#ffffff",
                            border: "1px solid #dadce0",
                            borderRadius: 6,
                            color: "#3c4043",
                            fontFamily: "\"Roboto\", \"Segoe UI\", Arial, sans-serif",
                            fontSize: "0.875rem",
                            fontWeight: 500,
                            letterSpacing: "0.2px",
                            cursor: "pointer",
                            transition: "all 0.2s ease",
                        }}
                        onMouseEnter={(event) => {
                            event.currentTarget.style.borderColor = "#d2e3fc";
                            event.currentTarget.style.background = "#f8f9fa";
                        }}
                        onMouseLeave={(event) => {
                            event.currentTarget.style.borderColor = "#dadce0";
                            event.currentTarget.style.background = "#ffffff";
                        }}
                    >
                        <GoogleLogoIcon />
                        Continue with Google
                    </button>
                </Box>
            </div>
        </div>
    );
}

export default function AuthPage() {
    const { theme } = useTheme();
    const navigate = useNavigate();

    const isLoggedIn = !!localStorage.getItem("user");
    const isReturningUser = !!localStorage.getItem("hasRegistered");

    if (isLoggedIn) return <Navigate to="/brokers" replace />;

    const [tab, setTab] = useState(null);
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [confirm, setConfirm] = useState("");
    const [showPassword, setShowPassword] = useState(false);
    const [showConfirm, setShowConfirm] = useState(false);
    const [touched, setTouched] = useState({});
    const [loading, setLoading] = useState(false);
    const [apiError, setApiError] = useState("");

    const strength = getPasswordStrength(password);

    const errors = {
        username: touched.username ? validate("username", username) : "",
        password: touched.password ? validate("password", password) : "",
        confirm: touched.confirm ? validate("confirm", confirm, password) : "",
    };

    const isLoginValid = !errors.username && !errors.password && username && password;
    const isSignupValid = isLoginValid && !errors.confirm && confirm;

    const touch = (field) => setTouched((prev) => ({ ...prev, [field]: true }));

    const handleTabChange = (nextTab) => {
        setTab(nextTab);
        setTouched({});
        setApiError("");
        if (nextTab !== "signup") setConfirm("");
    };

    const handleLogin = async () => {
        setTouched({ username: true, password: true });
        if (!isLoginValid) return;

        setLoading(true);
        setApiError("");
        try {
            const res = await fetch("/api/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password }),
            });
            const data = await res.json();
            if (!res.ok) {
                setApiError(data.error || "Login failed");
                return;
            }
            localStorage.setItem("user", username);
            localStorage.setItem("hasRegistered", "true");
            navigate("/brokers", { replace: true });
        } catch {
            setApiError("Network error. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    const handleSignup = async () => {
        setTouched({ username: true, password: true, confirm: true });
        if (!isSignupValid) return;

        setLoading(true);
        setApiError("");
        try {
            const res = await fetch("/api/signup", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, password }),
            });
            const data = await res.json();
            if (!res.ok) {
                setApiError(data.error || "Signup failed");
                return;
            }
            localStorage.setItem("user", username);
            localStorage.setItem("hasRegistered", "true");
            navigate("/brokers", { replace: true });
        } catch {
            setApiError("Network error. Please try again.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        if (params.get("error") === "google_failed") {
            setApiError("Google sign-in failed. Please try again.");
            window.history.replaceState({}, "", "/login");
            setTab("login");
        }
    }, []);

    const loginGoogle = () => {
        window.location.href = "/auth/google";
    };

    const handleKeyDown = (event) => {
        if (event.key !== "Enter") return;
        if (tab === "login") {
            handleLogin();
            return;
        }
        if (tab === "signup") handleSignup();
    };

    const pageOverlay =
        theme === "dark"
            ? "radial-gradient(circle at 12% 20%, rgba(79, 158, 255, 0.14), transparent 56%), radial-gradient(circle at 86% 78%, rgba(0, 230, 118, 0.08), transparent 52%), linear-gradient(180deg, rgba(6, 11, 24, 0.05) 0%, rgba(6, 11, 24, 0.22) 100%)"
            : "radial-gradient(circle at 12% 20%, rgba(59, 130, 246, 0.10), transparent 56%), radial-gradient(circle at 86% 78%, rgba(16, 185, 129, 0.06), transparent 52%), linear-gradient(180deg, rgba(248, 250, 252, 0.05) 0%, rgba(241, 245, 249, 0.18) 100%)";

    const statsCardSurface =
        theme === "dark" ? "rgba(13, 21, 38, 0.58)" : "rgba(255, 255, 255, 0.82)";

    return (
        <div
            className="relative w-full h-screen overflow-hidden"
            style={{ background: "var(--bg-primary)", color: "var(--text-primary)" }}
        >
            <CandleBackground />

            <div
                style={{
                    position: "absolute",
                    inset: 0,
                    zIndex: 1,
                    pointerEvents: "none",
                    background: pageOverlay,
                }}
            />

            <Navbar authMode authTab={tab} onAuthTabChange={handleTabChange} />

            <div
                className="relative z-10 grid grid-cols-1 lg:grid-cols-[1.1fr_0.9fr]"
                style={{ height: "calc(100vh - var(--navbar-height))" }}
            >
                <div
                    className="relative z-10 flex flex-col justify-center px-8 lg:px-14 xl:px-20"
                    style={{ color: "var(--text-primary)" }}
                >
                    <div
                        style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 6,
                            background: "var(--accent-blue-muted)",
                            border: "1px solid var(--accent-blue)",
                            borderRadius: 999,
                            padding: "4px 12px",
                            width: "fit-content",
                            marginBottom: 16,
                        }}
                    >
                        <span
                            style={{
                                width: 7,
                                height: 7,
                                borderRadius: "50%",
                                background: "var(--accent-blue)",
                                boxShadow: "0 0 8px var(--accent-blue)",
                                animation: "pulse 2s infinite",
                            }}
                        />
                        <span
                            style={{
                                fontSize: 11,
                                color: "var(--accent-blue)",
                                fontWeight: 700,
                                letterSpacing: "0.06em",
                            }}
                        >
                            PROJECT OVERVIEW
                        </span>
                    </div>

                    <h1
                        style={{
                            fontFamily: "var(--font-display)",
                            fontSize: "clamp(2.5rem, 6vw, 4.4rem)",
                            fontWeight: 700,
                            color: "var(--text-primary)",
                            letterSpacing: "-0.04em",
                            lineHeight: 0.98,
                            marginBottom: 12,
                            maxWidth: 700,
                        }}
                    >
                        Trade Intelligence
                        <br />
                        <span style={{ color: "var(--accent-blue)" }}>At Data Scale</span>
                    </h1>

                    <p
                        style={{
                            fontSize: "0.95rem",
                            color: "var(--text-secondary)",
                            maxWidth: 640,
                            lineHeight: 1.62,
                            marginBottom: 16,
                        }}
                    >
                        High-frequency market workflows with live ingestion, indicator analytics,
                        strategy tooling, and broker execution from a single console.
                    </p>

                    <div
                        style={{
                            display: "grid",
                            gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
                            gap: 10,
                            maxWidth: 760,
                            marginBottom: 14,
                        }}
                    >
                        {PROJECT_STATS.map((item) => (
                            <div
                                key={item.label}
                                style={{
                                    background: statsCardSurface,
                                    border: "1px solid var(--border-color)",
                                    borderRadius: 12,
                                    padding: "12px 13px",
                                    backdropFilter: "blur(4px)",
                                }}
                            >
                                <div
                                    style={{
                                        fontFamily: "var(--font-mono)",
                                        fontSize: "clamp(1.2rem, 2.1vw, 1.85rem)",
                                        fontWeight: 700,
                                        color: "var(--text-primary)",
                                        lineHeight: 1.1,
                                    }}
                                >
                                    {item.value}
                                </div>
                                <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: 3 }}>
                                    {item.label}
                                </div>
                            </div>
                        ))}
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        {PROJECT_POINTS.map((text) => (
                            <div key={text} style={{ display: "flex", alignItems: "flex-start", gap: 9 }}>
                                <CheckCircleIcon sx={{ fontSize: 17, color: "var(--accent-up)", mt: "2px", flexShrink: 0 }} />
                                <span style={{ fontSize: "0.9rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                                    {text}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>

                <div className="relative z-10 flex items-center justify-center px-6">
                    <div style={{ width: "100%", maxWidth: 430 }}>
                        <AuthCard
                            tab={tab}
                            theme={theme}
                            username={username}
                            setUsername={setUsername}
                            password={password}
                            setPassword={setPassword}
                            confirm={confirm}
                            setConfirm={setConfirm}
                            showPassword={showPassword}
                            setShowPassword={setShowPassword}
                            showConfirm={showConfirm}
                            setShowConfirm={setShowConfirm}
                            errors={errors}
                            touch={touch}
                            handleKeyDown={handleKeyDown}
                            strength={strength}
                            handleLogin={handleLogin}
                            handleSignup={handleSignup}
                            loading={loading}
                            apiError={apiError}
                            setApiError={setApiError}
                            loginGoogle={loginGoogle}
                            isReturningUser={isReturningUser}
                        />
                    </div>
                </div>
            </div>

            <style>{`
                @keyframes pulse {
                    0%, 100% { opacity: 1; transform: scale(1); }
                    50% { opacity: 0.65; transform: scale(1.2); }
                }
            `}</style>
        </div>
    );
}
