import React from "react";

function Bone({ width = "100%", height = 20, radius = 8, style = {} }) {
    return (
        <div style={{
            width, height,
            borderRadius:    radius,
            background:      "var(--bg-tertiary)",
            animation:       "skeletonPulse 1.5s ease-in-out infinite",
            ...style,
        }} />
    );
}

export default function SkeletonLoader() {
    return (
        <div style={{
            maxWidth: "var(--max-width)",
            margin:   "0 auto",
            padding:  "var(--content-padding)",
            display:  "flex",
            flexDirection: "column",
            gap:      24,
        }}>
            {/* Search + status row */}
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
                <Bone width={440} height={40} radius={999} />
                <Bone width={160} height={36} radius={8} />
            </div>

            {/* Index strip */}
            <div style={{ display: "flex", gap: 12, overflow: "hidden" }}>
                {[...Array(4)].map((_, i) => (
                    <Bone key={i} width={170} height={58} radius={10}
                        style={{ flexShrink: 0, animationDelay: `${i * 0.08}s` }} />
                ))}
            </div>

            {/* Main grid */}
            <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 24 }}>
                {/* Instrument cards */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                    {[...Array(6)].map((_, i) => (
                        <Bone key={i} height={90} radius={12}
                            style={{ animationDelay: `${i * 0.06}s` }} />
                    ))}
                </div>

                {/* Tools panel */}
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    <Bone height={140} radius={12} style={{ animationDelay: "0.1s" }} />
                    <Bone height={280} radius={12} style={{ animationDelay: "0.2s" }} />
                </div>
            </div>

            <style>{`
                @keyframes skeletonPulse {
                    0%,100% { opacity: 1;   }
                    50%     { opacity: 0.35; }
                }
            `}</style>
        </div>
    );
}
