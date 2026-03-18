export async function fetchTimeframes() {
    return [
        { value: "1", label: "1m" },
        { value: "3", label: "3m" },
        { value: "5", label: "5m" },
        { value: "15", label: "15m" },
        { value: "30", label: "30m" },
        { value: "60", label: "1h" },
    ];
}