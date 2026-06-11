export const PROFILE_STORAGE_KEY = "userProfile";
export const PROFILE_UPDATED_EVENT = "candlesticks:profile-updated";

export function loadProfile() {
    try {
        const saved = localStorage.getItem(PROFILE_STORAGE_KEY);
        const parsed = saved ? JSON.parse(saved) : {};
        return parsed && typeof parsed === "object" ? parsed : {};
    } catch {
        return {};
    }
}

export function saveProfile(data) {
    const nextProfile = data && typeof data === "object" ? data : {};
    localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(nextProfile));

    if (typeof window !== "undefined") {
        window.dispatchEvent(
            new CustomEvent(PROFILE_UPDATED_EVENT, { detail: nextProfile })
        );
    }
}
