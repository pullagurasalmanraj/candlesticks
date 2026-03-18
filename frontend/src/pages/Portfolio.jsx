import React from "react";
import { useTheme } from "../context/ThemeContext";

export default function Portfolio() {
  const { theme } = useTheme();
  const isLight = theme === "light";

  return (
    <div className={`p-6 rounded-xl ${isLight ? "bg-white" : "bg-gray-900"}`}>
      <h2 className={`text-3xl font-bold mb-4 ${isLight ? "text-green-600" : "text-green-400"}`}>
        💼 My Portfolio
      </h2>
      <p className={isLight ? "text-gray-700" : "text-gray-300"}>
        Review your holdings, profit/loss, and investment summary.
      </p>
    </div>
  );
}
