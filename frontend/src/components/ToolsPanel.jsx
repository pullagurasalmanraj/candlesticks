import React from "react";
import DatePicker from "react-datepicker";
import { startOfDay } from "../utils/dateUtils";

// Shared style tokens — all read from CSS vars
const inputStyle = {
    width:        "100%",
    height:       36,
    borderRadius: "var(--input-radius)",
    border:       "1px solid var(--border-color)",
    background:   "var(--bg-tertiary)",
    color:        "var(--text-primary)",
    padding:      "0 10px",
    fontSize:     "0.8rem",
    fontFamily:   "var(--font-body)",
    outline:      "none",
    boxSizing:    "border-box",
    transition:   "border-color 0.15s ease",
};

const labelStyle = {
    display:       "block",
    fontSize:      "0.68rem",
    fontWeight:    600,
    textTransform: "uppercase",
    letterSpacing: "0.06em",
    color:         "var(--text-muted)",
    fontFamily:    "var(--font-body)",
    marginBottom:  5,
};

const cardStyle = {
    borderRadius: "var(--card-radius)",
    border:       "1px solid var(--border-color)",
    background:   "var(--bg-secondary)",
    boxShadow:    "var(--shadow-card)",
    padding:      16,
};

const cardTitleStyle = {
    fontSize:      "0.8rem",
    fontWeight:    700,
    fontFamily:    "var(--font-display)",
    color:         "var(--text-primary)",
    letterSpacing: "-0.01em",
    marginBottom:  14,
};

function PrimaryButton({ onClick, disabled, color = "blue", children }) {
    const colorMap = {
        blue:   { bg: "var(--accent-blue)",  shadow: "var(--shadow-glow-blue)"  },
        green:  { bg: "var(--accent-up)",    shadow: "var(--shadow-glow-green)" },
        purple: { bg: "#8b5cf6",             shadow: "0 0 14px rgba(139,92,246,0.3)" },
    };
    const c = colorMap[color] || colorMap.blue;

    return (
        <button
            type="button"
            onClick={onClick}
            disabled={disabled}
            style={{
                width:        "100%",
                height:       34,
                borderRadius: "var(--button-radius)",
                border:       "none",
                background:   disabled ? "var(--bg-tertiary)" : c.bg,
                color:        disabled ? "var(--text-muted)"  : "#fff",
                fontSize:     "0.78rem",
                fontWeight:   600,
                fontFamily:   "var(--font-body)",
                cursor:       disabled ? "not-allowed" : "pointer",
                boxShadow:    disabled ? "none" : c.shadow,
                transition:   "all 0.15s ease",
            }}
            onMouseEnter={e => { if (!disabled) e.currentTarget.style.opacity = "0.85"; }}
            onMouseLeave={e => { if (!disabled) e.currentTarget.style.opacity = "1"; }}
        >
            {children}
        </button>
    );
}

// No isLight prop — all colours from CSS vars
export default function ToolsPanel({
    selectedSymbol, setSelectedSymbol,
    startDate, endDate, setStartDate, setEndDate,
    histStart, histEnd, setHistStart, setHistEnd,
    timeframe, setTimeframe, timeframes,
    years, setYears,
    isApplyingIndicators,
    runBulkFetch, applyIndicators,
    fetchHistoricalCandles, downloadExcel,
}) {
    const datepickerInputStyle = {
        ...inputStyle,
        textAlign: "center",
        padding:   "0 6px",
        width:     "100%",
    };

    return (
        <section style={{ display: "flex", flexDirection: "column", gap: 16 }}>

            {/* ── Download daily ───────────────────────── */}
            <div style={cardStyle}>
                <h3 style={cardTitleStyle}>Download historical (daily)</h3>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>

                    <input
                        value={selectedSymbol}
                        onChange={e => setSelectedSymbol(e.target.value.toUpperCase())}
                        placeholder="Symbol (e.g. TCS)"
                        style={inputStyle}
                        onFocus={e  => e.target.style.borderColor = "var(--accent-blue)"}
                        onBlur={e   => e.target.style.borderColor = "var(--border-color)"}
                    />

                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                        <DatePicker
                            fixedHeight selected={startDate}
                            onChange={d => setStartDate(startOfDay(d))}
                            maxDate={startOfDay(new Date())}
                            showMonthDropdown showYearDropdown dropdownMode="select"
                            dateFormat="dd/MM/yyyy" placeholderText="Start date"
                            popperPlacement="bottom-start" portalId="datepicker-portal"
                            className="dp-input"
                        />
                        <DatePicker
                            fixedHeight selected={endDate}
                            onChange={d => setEndDate(startOfDay(d))}
                            minDate={startDate ? startOfDay(startDate) : null}
                            maxDate={startOfDay(new Date())}
                            showMonthDropdown showYearDropdown dropdownMode="select"
                            dateFormat="dd/MM/yyyy" placeholderText="End date"
                            popperPlacement="bottom-start" portalId="datepicker-portal"
                            className="dp-input"
                        />
                    </div>

                    <div style={{ display: "flex", justifyContent: "flex-end" }}>
                        <PrimaryButton color="green" onClick={downloadExcel}
                            disabled={!selectedSymbol || !startDate || !endDate}>
                            Download Excel
                        </PrimaryButton>
                    </div>
                </div>
            </div>

            {/* ── Intraday + indicators ────────────────── */}
            <div style={cardStyle}>
                <h3 style={cardTitleStyle}>Intraday history & indicators</h3>
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>

                    {/* Timeframe */}
                    <div>
                        <label style={labelStyle}>Timeframe</label>
                        <select
                            value={timeframe}
                            onChange={e => setTimeframe(e.target.value)}
                            style={inputStyle}
                            onFocus={e => e.target.style.borderColor = "var(--accent-blue)"}
                            onBlur={e  => e.target.style.borderColor = "var(--border-color)"}
                        >
                            <option value="">Select timeframe</option>
                            {timeframes.map(tf => (
                                <option key={tf.value} value={tf.value}>{tf.label}</option>
                            ))}
                        </select>
                    </div>

                    {/* Bulk years */}
                    <div>
                        <label style={labelStyle}>Bulk fetch range (years)</label>
                        <select
                            value={years}
                            onChange={e => setYears(e.target.value)}
                            style={inputStyle}
                            onFocus={e => e.target.style.borderColor = "var(--accent-blue)"}
                            onBlur={e  => e.target.style.borderColor = "var(--border-color)"}
                        >
                            <option value="">Select</option>
                            <option value="1">1 Year</option>
                            <option value="2">2 Years</option>
                            <option value="3">3 Years</option>
                            <option value="5">5 Years</option>
                        </select>
                    </div>

                    {/* Manual date range */}
                    <div>
                        <label style={labelStyle}>Manual date range</label>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                            <DatePicker
                                fixedHeight selected={histStart}
                                onChange={d => setHistStart(startOfDay(d))}
                                maxDate={startOfDay(new Date())}
                                showMonthDropdown showYearDropdown dropdownMode="select"
                                dateFormat="dd/MM/yyyy" placeholderText="Start date"
                                popperPlacement="bottom-start" portalId="datepicker-portal"
                                className="dp-input"
                            />
                            <DatePicker
                                fixedHeight selected={histEnd}
                                onChange={d => setHistEnd(startOfDay(d))}
                                minDate={histStart ? startOfDay(histStart) : null}
                                maxDate={startOfDay(new Date())}
                                showMonthDropdown showYearDropdown dropdownMode="select"
                                dateFormat="dd/MM/yyyy" placeholderText="End date"
                                popperPlacement="bottom-start" portalId="datepicker-portal"
                                className="dp-input"
                            />
                        </div>
                    </div>

                    {/* Action buttons */}
                    <div style={{ display: "flex", flexDirection: "column", gap: 8, paddingTop: 4 }}>
                        <PrimaryButton color="blue" onClick={runBulkFetch}
                            disabled={!selectedSymbol || !timeframe || !years}>
                            Fetch full history {years ? `(${years}Y)` : ""}
                        </PrimaryButton>

                        <PrimaryButton color="green" onClick={applyIndicators}
                            disabled={!selectedSymbol || !timeframe || isApplyingIndicators}>
                            {isApplyingIndicators ? "Processing…" : "Generate indicators"}
                        </PrimaryButton>

                        <PrimaryButton color="purple" onClick={fetchHistoricalCandles}
                            disabled={!selectedSymbol || !timeframe || !histStart || !histEnd}>
                            Fetch historical (store to DB)
                        </PrimaryButton>
                    </div>
                </div>
            </div>

            {/* DatePicker input global style — reads CSS vars */}
            <style>{`
                .dp-input {
                    width: 100%;
                    height: 36px;
                    border-radius: var(--input-radius);
                    border: 1px solid var(--border-color);
                    background: var(--bg-tertiary);
                    color: var(--text-primary);
                    padding: 0 6px;
                    text-align: center;
                    font-size: 0.8rem;
                    font-family: var(--font-body);
                    outline: none;
                    box-sizing: border-box;
                }
                .dp-input:focus { border-color: var(--accent-blue); }
            `}</style>
        </section>
    );
}
