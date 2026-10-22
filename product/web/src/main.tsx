import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import { PeriodProvider } from "./period";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 0,
      refetchOnWindowFocus: false,
      staleTime: 10_000,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: "#2f6bff",
          colorLink: "#2f6bff",
          colorText: "#1a2233",
          colorTextSecondary: "#667082",
          colorBorder: "#e8ecf1",
          borderRadius: 8,
          fontFamily:
            '"Noto Sans SC", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif',
          fontSize: 14,
        },
      }}
    >
      <QueryClientProvider client={queryClient}>
        <PeriodProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </PeriodProvider>
      </QueryClientProvider>
    </ConfigProvider>
  </StrictMode>,
);
