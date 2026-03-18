import React from "react";
import { useTheme } from "../context/ThemeContext";

export default function SettingsPage() {
  const { theme } = useTheme();
  const isLight = theme === "light";

  return (
    <div className={`p-6 rounded-xl ${isLight ? "bg-white" : "bg-gray-900"}`}>
      <h2 className={`text-3xl font-bold mb-4 ${isLight ? "text-purple-600" : "text-purple-400"}`}>
        ⚙️ Settings
      </h2>
      <p className={isLight ? "text-gray-700" : "text-gray-300"}>
        Customize your preferences, notifications, and account info.
      </p>
    </div>
  );
}
