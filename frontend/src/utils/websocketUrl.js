export function getWebSocketUrl() {
    const configuredUrl = import.meta.env.VITE_WS_URL?.trim();
    if (configuredUrl) return configuredUrl;

    const { protocol, hostname, host } = window.location;
    const socketProtocol = protocol === "https:" ? "wss:" : "ws:";

    // Direct Vite development does not pass through the Nginx /ws/ proxy.
    if (import.meta.env.DEV && (hostname === "localhost" || hostname === "127.0.0.1")) {
        return `${socketProtocol}//${hostname}:9000`;
    }

    return `${socketProtocol}//${host}/ws/`;
}
