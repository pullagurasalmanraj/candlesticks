import React from "react";

export default function MarketSummary({ marketSummary, asOf }) {
    return (
        <div style={{ textAlign: "right", fontFamily: "var(--font-body)" }}>
            <div style={{
                fontSize:   "0.75rem",
                fontWeight: 600,
                color:      "var(--text-secondary)",
            }}>
                {marketSummary?.title ?? "Market summary"}
            </div>
            <div style={{
                fontSize:   "0.7rem",
                color:      "var(--text-muted)",
                fontFamily: "var(--font-mono)",
                marginTop:  2,
            }}>
                {asOf ? `Updated ${new Date(asOf).toLocaleTimeString()}` : ""}
            </div>
        </div>
    );
}
