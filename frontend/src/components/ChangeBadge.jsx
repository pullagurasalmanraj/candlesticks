export default function ChangeBadge({ pct, up }) {
    const sign = up ? "+" : "";
    return (
        <span style={{
            fontSize:        "12px",
            fontWeight:      700,
            padding:         "3px 10px",
            borderRadius:    999,
            background:      up ? "rgba(0,230,118,0.16)"  : "rgba(255,82,82,0.16)",
            color:           up ? "var(--accent-up)"       : "var(--accent-down)",
            border:          up ? "1px solid rgba(0,230,118,0.32)" : "1px solid rgba(255,82,82,0.32)",
            fontFamily:      "var(--font-mono)",
            letterSpacing:   "0.02em",
            whiteSpace:      "nowrap",
            boxShadow:       up ? "0 2px 8px rgba(0,230,118,0.15)" : "0 2px 8px rgba(255,82,82,0.15)",
        }}>
            {sign}{pct.toFixed(2)}%
        </span>
    );
}
