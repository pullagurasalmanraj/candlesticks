import React from "react";

const baseCardStyle = {
    background: "var(--bg-secondary)",
    border: "1px solid var(--border-color)",
    borderRadius: "var(--card-radius)",
    boxShadow: "var(--shadow-card)",
};

export function Card({ children, style }) {
    return (
        <div style={{ ...baseCardStyle, ...style }}>
            {children}
        </div>
    );
}

export function CardHeader({ title, subtitle, right, icon }) {
    return (
        <div style={{
            padding: "18px 18px 14px",
            borderBottom: "1px solid var(--border-subtle)",
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: 12,
        }}>
            <div style={{ minWidth: 0 }}>
                {subtitle && (
                    <div style={{
                        fontSize: "0.68rem",
                        fontWeight: 800,
                        letterSpacing: "0.08em",
                        textTransform: "uppercase",
                        color: "var(--text-muted)",
                        marginBottom: 4,
                    }}>
                        {subtitle}
                    </div>
                )}
                <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                    {icon ? (
                        <div style={{
                            width: 32,
                            height: 32,
                            borderRadius: 10,
                            background: "linear-gradient(135deg, var(--accent-blue), var(--accent-up))",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            flexShrink: 0,
                        }}>
                            {icon}
                        </div>
                    ) : null}
                    <div style={{
                        fontSize: "1rem",
                        fontWeight: 900,
                        fontFamily: "var(--font-display)",
                        letterSpacing: "-0.01em",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        color: "var(--text-primary)",
                    }}>
                        {title}
                    </div>
                </div>
            </div>
            {right}
        </div>
    );
}

export function Chip({ label, tone = "neutral" }) {
    const tones = {
        neutral: { bg: "var(--bg-tertiary)", border: "var(--border-color)", fg: "var(--text-secondary)" },
        good: { bg: "rgba(0,230,118,0.12)", border: "rgba(0,230,118,0.25)", fg: "var(--accent-up)" },
        bad: { bg: "rgba(255,82,82,0.12)", border: "rgba(255,82,82,0.25)", fg: "var(--accent-down)" },
        info: { bg: "var(--accent-blue-muted)", border: "rgba(79,158,255,0.35)", fg: "var(--accent-blue)" },
        warn: { bg: "rgba(255,213,79,0.16)", border: "rgba(255,213,79,0.28)", fg: "var(--accent-gold)" },
    };
    const t = tones[tone] || tones.neutral;

    return (
        <span style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            padding: "5px 10px",
            borderRadius: 999,
            fontSize: "0.7rem",
            fontWeight: 800,
            fontFamily: "var(--font-mono)",
            background: t.bg,
            border: `1px solid ${t.border}`,
            color: t.fg,
            whiteSpace: "nowrap",
        }}>
            {label}
        </span>
    );
}

export function FieldLabel({ children }) {
    return (
        <div style={{
            fontSize: "0.72rem",
            color: "var(--text-secondary)",
            fontWeight: 700,
            marginBottom: 6,
            fontFamily: "var(--font-body)",
        }}>
            {children}
        </div>
    );
}

export function Input({ style, ...props }) {
    return (
        <input
            {...props}
            style={{
                width: "100%",
                height: 42,
                padding: "0 12px",
                borderRadius: "var(--input-radius)",
                border: "1px solid var(--border-color)",
                background: "var(--bg-tertiary)",
                color: "var(--text-primary)",
                outline: "none",
                fontSize: "0.9rem",
                fontFamily: "var(--font-body)",
                ...style,
            }}
        />
    );
}

export function Select({ style, children, ...props }) {
    return (
        <select
            {...props}
            style={{
                width: "100%",
                height: 42,
                padding: "0 12px",
                borderRadius: "var(--input-radius)",
                border: "1px solid var(--border-color)",
                background: "var(--bg-tertiary)",
                color: "var(--text-primary)",
                outline: "none",
                fontSize: "0.9rem",
                fontFamily: "var(--font-body)",
                ...style,
            }}
        >
            {children}
        </select>
    );
}

export function PrimaryButton({ children, disabled, onClick, icon, style }) {
    return (
        <button
            type="button"
            onClick={onClick}
            disabled={disabled}
            style={{
                height: 42,
                padding: "0 14px",
                borderRadius: "var(--button-radius)",
                border: "1px solid rgba(79,158,255,0.35)",
                background: disabled ? "var(--bg-tertiary)" : "var(--accent-blue)",
                color: disabled ? "var(--text-muted)" : "#fff",
                boxShadow: disabled ? "none" : "var(--shadow-glow-blue)",
                cursor: disabled ? "not-allowed" : "pointer",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                fontWeight: 900,
                fontSize: "0.86rem",
                fontFamily: "var(--font-body)",
                transition: "all 0.15s ease",
                whiteSpace: "nowrap",
                ...style,
            }}
        >
            {icon}
            {children}
        </button>
    );
}

export function SubtleButton({ children, disabled, onClick, style }) {
    return (
        <button
            type="button"
            onClick={onClick}
            disabled={disabled}
            style={{
                height: 34,
                padding: "0 12px",
                borderRadius: 8,
                border: "1px solid var(--border-color)",
                background: "transparent",
                color: disabled ? "var(--text-muted)" : "var(--text-primary)",
                cursor: disabled ? "not-allowed" : "pointer",
                fontWeight: 800,
                fontSize: "0.78rem",
                fontFamily: "var(--font-body)",
                ...style,
            }}
        >
            {children}
        </button>
    );
}

