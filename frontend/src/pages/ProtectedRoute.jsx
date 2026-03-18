import React from "react";
import { Navigate } from "react-router-dom";

export default function ProtectedRoute({ children }) {
  // Read token and expiry time from localStorage
  const token = localStorage.getItem("upstox_access_token");
  const expiry = parseInt(localStorage.getItem("upstox_token_expiry") || "0", 10);

  // Check if token exists and is still valid
  const isValid = token && Date.now() < expiry;

  if (!isValid) {
    console.warn("🔒 Token missing or expired — redirecting to login");
    localStorage.removeItem("upstox_access_token");
    localStorage.removeItem("upstox_token_expiry");
    return <Navigate to="/login" replace />;
  }

  // Token is valid — allow access
  return children;
}
