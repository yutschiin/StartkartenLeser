import React from "react";
import ReactDOM from "react-dom/client";
import { CssBaseline, ThemeProvider, createTheme } from "@mui/material";
import App from "./App";
import { NotificationProvider } from "./Notifications";
import "./styles.css";

const theme = createTheme({
  palette: {
    primary: { main: "#126f72" },
    secondary: { main: "#e76f51" },
    background: { default: "#f5f7fa", paper: "#ffffff" },
    text: { primary: "#172b36", secondary: "#536772" },
    error: { main: "#b42318" },
    success: { main: "#18794e" },
  },
  shape: { borderRadius: 12 },
  typography: {
    fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    button: { textTransform: "none", fontWeight: 650 },
    h1: { fontSize: "clamp(1.7rem, 3vw, 2.35rem)", fontWeight: 750 },
    h2: { fontSize: "1.5rem", fontWeight: 700 },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <NotificationProvider>
        <App />
      </NotificationProvider>
    </ThemeProvider>
  </React.StrictMode>,
);
