import { useState, useEffect, useRef } from "react";

export default function useInstrumentSearch() {

    const [search, setSearch] = useState("");
    const [debouncedSearch, setDebouncedSearch] = useState("");
    const [instruments, setInstruments] = useState([]);
    const [showResults, setShowResults] = useState(false);

    const searchCacheRef = useRef({});

    useEffect(() => {
        const t = setTimeout(() => setDebouncedSearch(search.trim()), 150);
        return () => clearTimeout(t);
    }, [search]);

    useEffect(() => {

        if (debouncedSearch.length < 2) {
            setInstruments([]);
            return;
        }

        if (searchCacheRef.current[debouncedSearch]) {
            setInstruments(searchCacheRef.current[debouncedSearch]);
            return;
        }

        const controller = new AbortController();

        fetch(`/api/instruments?q=${encodeURIComponent(debouncedSearch)}`, {
            signal: controller.signal
        })
            .then(r => r.json())
            .then(d => {

                const results = Array.isArray(d.instruments) ? d.instruments : [];

                searchCacheRef.current[debouncedSearch] = results;

                setInstruments(results);

            })
            .catch(err => {
                if (err.name !== "AbortError") setInstruments([]);
            });

        return () => controller.abort();

    }, [debouncedSearch]);

    return {
        search,
        setSearch,
        instruments,
        showResults,
        setShowResults,
        debouncedSearch
    };
}