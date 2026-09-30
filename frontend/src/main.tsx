import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ProveedorFondo } from "./lib/fondo";
import { ProveedorSesion } from "./lib/sesion";
import "./styles/app.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <ProveedorSesion>
        <ProveedorFondo>
          <App />
        </ProveedorFondo>
      </ProveedorSesion>
    </BrowserRouter>
  </React.StrictMode>,
);
