export default function ChangeBadge({ pct, up }) {
    const sign = up ? "+" : "";
    return (
        <span style={{
            fontSize:        "11px",
            fontWeight:      600,
            padding:         "2px 8px",
            borderRadius:    999,
            background:      up ? "rgba(0,230,118,0.12)"  : "rgba(255,82,82,0.12)",
            color:           up ? "var(--accent-up)"       : "var(--accent-down)",
            border:          up ? "1px solid rgba(0,230,118,0.25)" : "1px solid rgba(255,82,82,0.25)",
            fontFamily:      "var(--font-mono)",
            letterSpacing:   "0.02em",
            whiteSpace:      "nowrap",
        }}>
            {sign}{pct.toFixed(2)}%
        </span>
    );
}
