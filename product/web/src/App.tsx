import { useEffect, useState } from "react";
import { Button, DatePicker, Input, Modal, Space, Tag, Typography } from "antd";
import { NavLink, Route, Routes } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs, { type Dayjs } from "dayjs";

import { getOverview, setPin, setPinHandler, sync } from "./api";
import { usePeriod } from "./period";
import { Today } from "./pages/Today";
import { Loss } from "./pages/Loss";
import { Ads } from "./pages/Ads";
import { Ask } from "./pages/Ask";
import { Data } from "./pages/Data";

const NAV = [
  { to: "/", label: "今日", end: true },
  { to: "/loss", label: "亏损商品", end: false },
  { to: "/ads", label: "广告浪费", end: false },
  { to: "/ask", label: "问一句", end: false },
  { to: "/data", label: "数据与同步", end: false },
];

function PeriodSync() {
  const { range, setRange } = usePeriod();
  const overview = useQuery({
    queryKey: ["overview", range],
    queryFn: () => getOverview(range),
  });
  useEffect(() => {
    if (range === null && overview.data) setRange(overview.data.period);
  }, [range, overview.data, setRange]);
  return null;
}

function navClass({ isActive }: { isActive: boolean }) {
  return [
    "rounded-lg px-3 py-2 text-sm transition-colors whitespace-nowrap",
    isActive
      ? "bg-white/10 text-white"
      : "text-white/60 hover:bg-white/5 hover:text-white/90",
  ].join(" ");
}

export function App() {
  const { range, setRange } = usePeriod();
  const client = useQueryClient();
  const [picker, setPicker] = useState<[Dayjs, Dayjs] | null>(null);
  const [pinOpen, setPinOpen] = useState(false);
  const [pinValue, setPinValue] = useState("");

  useEffect(() => {
    setPinHandler(() => setPinOpen(true));
  }, []);

  useEffect(() => {
    if (range) setPicker([dayjs(range.start), dayjs(range.end)]);
  }, [range]);

  const syncMutation = useMutation({
    mutationFn: sync,
    onSuccess: () => client.invalidateQueries(),
  });

  const applyPreset = (kind: "7" | "30" | "month") => {
    const today = dayjs();
    let start = today;
    let end = today;
    if (kind === "month") {
      start = today.startOf("month");
      end = today.endOf("month");
    } else {
      start = today.subtract(Number(kind) - 1, "day");
    }
    setRange({ start: start.format("YYYY-MM-DD"), end: end.format("YYYY-MM-DD") });
  };

  return (
    <div className="min-h-screen xl:flex">
      <PeriodSync />
      <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col bg-[var(--color-spine)] xl:flex">
        <div className="flex items-center gap-2 px-5 pb-6 pt-5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-brand)] text-base font-semibold text-white">
            L
          </span>
          <span className="text-base font-semibold text-white">Lira</span>
          <Tag color="default" className="!border-white/10 !bg-white/10 !text-white/70">
            利润诊断
          </Tag>
        </div>
        <nav className="flex flex-col gap-1 px-3">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={navClass}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto px-5 pb-6">
          <div className="rounded-lg bg-white/5 px-3 py-2 text-xs text-white/50">
            <div className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              本机运行
            </div>
            <div className="mt-2 text-white/30">
              全部计算在本机完成，不联网、不上传。
            </div>
          </div>
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-20 border-b border-[var(--color-line)] bg-white/95 backdrop-blur">
          <div className="flex flex-wrap items-center gap-3 px-4 py-3">
            <span className="text-sm font-semibold xl:hidden">Lira · 利润诊断</span>
            <div className="ml-auto flex flex-wrap items-center gap-2">
              <DatePicker.RangePicker
                size="small"
                value={picker}
                allowClear={false}
                onChange={(dates) => {
                  if (dates?.[0] && dates[1]) {
                    setRange({
                      start: dates[0].format("YYYY-MM-DD"),
                      end: dates[1].format("YYYY-MM-DD"),
                    });
                  }
                }}
              />
              <Button size="small" onClick={() => applyPreset("7")}>近7天</Button>
              <Button size="small" onClick={() => applyPreset("30")}>近30天</Button>
              <Button size="small" onClick={() => applyPreset("month")}>本月</Button>
              <Button
                size="small"
                type="primary"
                loading={syncMutation.isPending}
                onClick={() => syncMutation.mutate()}
              >
                重新同步
              </Button>
            </div>
          </div>
          <nav className="flex gap-1 overflow-x-auto px-3 pb-2 xl:hidden">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  [
                    "rounded-lg px-3 py-1.5 text-sm whitespace-nowrap",
                    isActive
                      ? "bg-[var(--color-ground)] text-[var(--color-ink)]"
                      : "text-[var(--color-ink-soft)]",
                  ].join(" ")
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </header>

        <main className="mx-auto max-w-[1200px] px-4 py-5">
          <Routes>
            <Route path="/" element={<Today />} />
            <Route path="/loss" element={<Loss />} />
            <Route path="/ads" element={<Ads />} />
            <Route path="/ask" element={<Ask />} />
            <Route path="/data" element={<Data />} />
          </Routes>
        </main>
      </div>

      <Modal
        open={pinOpen}
        title="需要访问 PIN"
        okText="进入"
        cancelText="取消"
        onCancel={() => setPinOpen(false)}
        onOk={() => {
          if (!pinValue.trim()) return;
          setPin(pinValue.trim());
          setPinOpen(false);
          setPinValue("");
          client.invalidateQueries();
        }}
      >
        <Typography.Paragraph type="secondary">
          局域网访问已开启，请输入本机设置的 PIN。
        </Typography.Paragraph>
        <Input.Password
          value={pinValue}
          onChange={(event) => setPinValue(event.target.value)}
          onPressEnter={() => {
            if (!pinValue.trim()) return;
            setPin(pinValue.trim());
            setPinOpen(false);
            setPinValue("");
            client.invalidateQueries();
          }}
          placeholder="PIN"
        />
      </Modal>
    </div>
  );
}
