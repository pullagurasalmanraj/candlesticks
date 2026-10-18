export default function ChangeBadge({ pct, up }) {
    const sign = up ? "+" : "";
    return (
        <span style={{
            fontSize:        "12px",
            fontWeight:      700,
            padding:         "3px 10px",
            borderRadius:    999,
            background:      up ? "var(--glow-green)"  : "var(--glow-red)",
            color:           up ? "var(--accent-up)"       : "var(--accent-down)",
            border:          up ? "1px solid color-mix(in srgb, var(--accent-up) 28%, transparent)" : "1px solid color-mix(in srgb, var(--accent-down) 28%, transparent)",
            fontFamily:      "var(--font-mono)",
            letterSpacing:   "0.02em",
            whiteSpace:      "nowrap",
            boxShadow:       up ? "0 2px 8px var(--glow-green)" : "0 2px 8px var(--glow-red)",
        }}>
            {sign}{pct.toFixed(2)}%
        </span>
    );
}
