import React from "react";
import InstrumentCard from "./InstrumentCard";

export default function SelectedInstruments({
    selectedInstruments,
    prices,
    selectedSymbol,
    activeSubscriptions,
    normalizeKey,
    setSelectedSymbol,
    setSelectedInstrument,
    setSelectedInstruments,
    subscribeToStock,
}) {
    if (selectedInstruments.length === 0) {
        return (
            <div style={{
                display:        "flex",
                alignItems:     "center",
                justifyContent: "center",
                minHeight:      120,
                color:          "var(--text-muted)",
                fontSize:       "0.8rem",
                fontFamily:     "var(--font-body)",
                textAlign:      "center",
                border:         "1px dashed var(--border-subtle)",
                borderRadius:   10,
            }}>
                Use the search above to add instruments to your working list.
            </div>
        );
    }

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {selectedInstruments.map(item => (
                <InstrumentCard
                    key={item.instrument_key}
                    item={item}
                    prices={prices}
                    selectedSymbol={selectedSymbol}
                    activeSubscriptions={activeSubscriptions}
                    normalizeKey={normalizeKey}
                    setSelectedSymbol={setSelectedSymbol}
                    setSelectedInstrument={setSelectedInstrument}
                    setSelectedInstruments={setSelectedInstruments}
                    subscribeToStock={subscribeToStock}
                />
            ))}
        </div>
    );
}
