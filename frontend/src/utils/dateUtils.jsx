import { format } from "date-fns";
export const startOfDay = (date) => {
    if (!date) return null;

    const d = new Date(date);
    d.setHours(0, 0, 0, 0);

    return d;
};

export const formatYMD = (d) => {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
};

export const normalizeDate = (d) => format(d, "yyyy-MM-dd");




export function generateMonthlyRanges(years) {

    const months = years * 12;

    const ranges = [];

    let today = new Date();
    let year = today.getFullYear();
    let month = today.getMonth();

    for (let i = 0; i < months; i++) {

        const start = new Date(year, month, 1);
        const end = new Date(year, month + 1, 0);

        ranges.push({
            start: formatYMD(start),
            end: formatYMD(end)
        });

        month--;

        if (month < 0) {
            month = 11;
            year--;
        }

    }

    return ranges;
}