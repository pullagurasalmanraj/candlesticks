import React, { useState, useEffect } from "react";
import { useTheme } from "../context/ThemeContext";

const TRADING_MOTIVATIONS = [
    { text: "Plan your trade, trade your plan. Consistency breeds compounding.", author: "Discipline" },
    { text: "Risk management isn't avoiding risk — it's mastering asymmetric reward.", author: "Capital Preservation" },
    { text: "Patience is your greatest edge. Let high-probability setups come to you.", author: "Patience" },
    { text: "Cut losers ruthlessly, let winners ride. Protect your psychological capital.", author: "Execution" },
    { text: "The goal is not to win every trade, but to make money over 100 trades.", author: "Probability" },
    { text: "Focus on flawless process execution; profits naturally follow discipline.", author: "Process Over Outcome" },
    { text: "Every master trader was once a disaster who refused to give up.", author: "Resilience" },
    { text: "The market pays you for sitting on your hands until the right moment.", author: "Timing" },
];

export default function TradingMotivationBanner() {
    const { theme } = useTheme();
    const isDark = theme === "dark";

    const [quoteIndex, setQuoteIndex] = useState(() => Math.floor(Math.random() * TRADING_MOTIVATIONS.length));
    const [fade, setFade] = useState(true);

    const nextQuote = () => {
        setFade(false);
        setTimeout(() => {
            setQuoteIndex((prev) => (prev + 1) % TRADING_MOTIVATIONS.length);
            setFade(true);
        }, 200);
    };

    // Auto rotate every 30 seconds
    useEffect(() => {
        const interval = setInterval(nextQuote, 30000);
        return () => clearInterval(interval);
    }, []);

    const current = TRADING_MOTIVATIONS[quoteIndex];

    return (
        <div
            onClick={nextQuote}
            style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 10,
                padding: "6px 14px",
                borderRadius: "var(--button-radius, 8px)",
                background: "var(--bg-tertiary)",
                border: "1px solid var(--border-color)",
                cursor: "pointer",
                transition: "all 0.2s ease",
                userSelect: "none",
                flex: "1 1 auto",
                minWidth: 280,
                maxWidth: 650,
            }}
            title="Click for another trading motivation"
            onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = "var(--accent-blue)";
                e.currentTarget.style.background = isDark ? "rgba(59, 130, 246, 0.14)" : "rgba(59, 130, 246, 0.08)";
            }}
            onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = "var(--border-color)";
                e.currentTarget.style.background = "var(--bg-tertiary)";
            }}
        >
            <div style={{
                display: "flex",
                alignItems: "center",
                gap: 4,
                fontSize: "0.68rem",
                fontWeight: 800,
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                color: "var(--accent-blue)",
                background: "rgba(59, 130, 246, 0.15)",
                padding: "3px 8px",
                borderRadius: 4,
                flexShrink: 0,
            }}>
                <span>✨</span>
                <span>Mindset</span>
            </div>

            <div style={{
                fontSize: "0.78rem",
                fontWeight: 600,
                color: "var(--text-primary)",
                fontFamily: "var(--font-sans, Inter, sans-serif)",
                lineHeight: 1.35,
                opacity: fade ? 1 : 0,
                transition: "opacity 0.2s ease-in-out",
            }}>
                "{current.text}"
            </div>
        </div>
    );
}
