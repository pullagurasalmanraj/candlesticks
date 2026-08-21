import React from "react";
import ToolsPanel from "./ToolsPanel";
import StockLogo from "./StockLogo";

export default function DataToolsDrawer({
    isOpen,
    onClose,
    selectedSymbol,
    setSelectedSymbol,
    selectedInstrument,
    startDate,
    endDate,
    setStartDate,
    setEndDate,
    histStart,
    histEnd,
    setHistStart,
    setHistEnd,
    timeframe,
    setTimeframe,
    timeframes,
    years,
    setYears,
    isApplyingIndicators,
    runBulkFetch,
    applyIndicators,
    fetchHistoricalCandles,
    downloadExcel,
    force,
    setForce,
}) {
    if (!isOpen) return null;

    return (
        <div style={{
            position: "fixed",
            top: 0, left: 0, right: 0, bottom: 0,
            zIndex: 9999,
            display: "flex",
            justifyContent: "flex-end",
            background: "rgba(0, 0, 0, 0.65)",
            backdropFilter: "blur(6px)",
            animation: "fadeIn 0.2s ease-out",
        }}>
            {/* Backdrop click to close */}
            <div
                style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0 }}
                onClick={onClose}
            />

            {/* Slide-out drawer panel */}
            <div style={{
                position: "relative",
                width: "100%",
                maxWidth: "460px",
                height: "100vh",
                background: "var(--bg-secondary)",
                borderLeft: "1px solid var(--border-color)",
                boxShadow: "-10px 0 30px rgba(0, 0, 0, 0.5)",
                display: "flex",
                flexDirection: "column",
                zIndex: 1,
                animation: "slideInRight 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
                overflow: "hidden",
            }}>
                {/* Header */}
                <div style={{
                    padding: "20px 24px",
                    borderBottom: "1px solid var(--border-color)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    background: "var(--bg-tertiary)",
                }}>
                    <div>
                        <div style={{
                            fontSize: "0.68rem",
                            fontWeight: 700,
                            letterSpacing: "0.08em",
                            textTransform: "uppercase",
                            color: "var(--accent-blue)",
                            fontFamily: "var(--font-body)",
                            marginBottom: 2,
                        }}>
                            Contextual Data Tools
                        </div>
                        <div style={{
                            fontSize: "1.15rem",
                            fontWeight: 700,
                            fontFamily: "var(--font-display)",
                            color: "var(--text-primary)",
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                        }}>
                            ⚡ Market Data Workbench
                        </div>
                    </div>

                    <button
                        onClick={onClose}
                        style={{
                            width: 32,
                            height: 32,
                            borderRadius: 8,
                            border: "1px solid var(--border-color)",
                            background: "var(--bg-secondary)",
                            color: "var(--text-muted)",
                            fontSize: "0.85rem",
                            cursor: "pointer",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            transition: "all 0.15s ease",
                        }}
                        onMouseEnter={(e) => {
                            e.currentTarget.style.color = "var(--text-primary)";
                            e.currentTarget.style.borderColor = "var(--accent-blue)";
                        }}
                        onMouseLeave={(e) => {
                            e.currentTarget.style.color = "var(--text-muted)";
                            e.currentTarget.style.borderColor = "var(--border-color)";
                        }}
                    >
                        ✕
                    </button>
                </div>

                {/* Target Stock Active Badge */}
                {selectedSymbol && (
                    <div style={{
                        padding: "12px 24px",
                        background: "rgba(59,130,246,0.12)",
                        borderBottom: "1px solid rgba(59,130,246,0.25)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                    }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                            <StockLogo symbol={selectedSymbol} size={28} borderRadius={6} />
                            <div>
                                <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", fontFamily: "var(--font-body)" }}>
                                    Active Target Symbol:
                                </div>
                                <div style={{ fontSize: "0.95rem", fontWeight: 700, fontFamily: "var(--font-display)", color: "var(--accent-blue)" }}>
                                    {selectedSymbol}
                                </div>
                            </div>
                        </div>
                        <span style={{
                            fontSize: "0.68rem",
                            fontFamily: "var(--font-mono)",
                            background: "var(--bg-secondary)",
                            border: "1px solid var(--border-color)",
                            borderRadius: 4,
                            padding: "2px 8px",
                            color: "var(--text-primary)",
                        }}>
                            {selectedInstrument?.instrument_key ? "Key bound" : "Custom symbol"}
                        </span>
                    </div>
                )}

                {/* Body Content — Scrollable Tools Panel */}
                <div style={{
                    flex: 1,
                    overflowY: "auto",
                    padding: "20px 24px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 16,
                }}>
                    <ToolsPanel
                        selectedSymbol={selectedSymbol}
                        setSelectedSymbol={setSelectedSymbol}
                        startDate={startDate}
                        endDate={endDate}
                        setStartDate={setStartDate}
                        setEndDate={setEndDate}
                        histStart={histStart}
                        histEnd={histEnd}
                        setHistStart={setHistStart}
                        setHistEnd={setHistEnd}
                        timeframe={timeframe}
                        setTimeframe={setTimeframe}
                        timeframes={timeframes}
                        years={years}
                        setYears={setYears}
                        isApplyingIndicators={isApplyingIndicators}
                        runBulkFetch={runBulkFetch}
                        applyIndicators={applyIndicators}
                        fetchHistoricalCandles={fetchHistoricalCandles}
                        downloadExcel={downloadExcel}
                        force={force}
                        setForce={setForce}
                    />
                </div>
            </div>

            <style>{`
                @keyframes slideInRight {
                    from { transform: translateX(100%); opacity: 0; }
                    to { transform: translateX(0); opacity: 1; }
                }
            `}</style>
        </div>
    );
}
