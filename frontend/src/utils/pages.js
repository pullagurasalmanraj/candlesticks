import React, { useEffect, useState } from "react";
import { api } from "../utils/api";

function Login() {
  const [loginUrl, setLoginUrl] = useState("");

  useEffect(() => {
    api.get("/login-url").then(res => setLoginUrl(res.data.login_url));
  }, []);

  return (
    <div style={{ textAlign: "center", marginTop: "20%" }}>
      <h1>Upstox Dashboard</h1>
      {loginUrl && (
        <a href={loginUrl}>
          <button>Login with Upstox</button>
        </a>
      )}
    </div>
  );
}

export default Login;
