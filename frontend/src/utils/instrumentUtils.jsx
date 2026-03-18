export const normalizeKey = (instOrKey) => {

    if (!instOrKey) return "";

    if (typeof instOrKey === "string") {
        return instOrKey.toUpperCase().trim();
    }

    return (
        (
            instOrKey.instrument_key ||
            instOrKey.instrumentKey ||
            instOrKey.symbol ||
            ""
        )
            .toString()
            .toUpperCase()
            .trim()
    );
};