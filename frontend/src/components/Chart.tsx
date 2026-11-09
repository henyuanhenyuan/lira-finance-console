import { BarChart, LineChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";
import type { EChartsOption } from "echarts";

// 只注册实际用到的图表与组件，避免把整个 echarts 打进包里
echarts.use([
  LineChart,
  BarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  CanvasRenderer,
]);

export default function Chart({
  option,
  height = 260,
}: {
  option: EChartsOption;
  height?: number | string;
}) {
  const el = useRef<HTMLDivElement | null>(null);
  const inst = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!el.current) return;
    inst.current = echarts.init(el.current, undefined, { renderer: "canvas" });
    const onResize = () => inst.current?.resize();
    window.addEventListener("resize", onResize);
    const ro = new ResizeObserver(() => inst.current?.resize());
    ro.observe(el.current);
    return () => {
      window.removeEventListener("resize", onResize);
      ro.disconnect();
      inst.current?.dispose();
      inst.current = null;
    };
  }, []);

  useEffect(() => {
    inst.current?.setOption(option, true);
  }, [option]);

  return <div ref={el} style={{ width: "100%", height }} />;
}

export const chartBase: EChartsOption = {
  backgroundColor: "transparent",
  textStyle: { color: "#8b97b8", fontFamily: "Inter, PingFang SC, sans-serif" },
  grid: { left: 8, right: 12, top: 26, bottom: 6, containLabel: true },
  tooltip: {
    trigger: "axis",
    backgroundColor: "rgba(8,12,24,.94)",
    borderColor: "rgba(255,255,255,.14)",
    borderWidth: 1,
    textStyle: { color: "#e9efff", fontSize: 12 },
    axisPointer: { lineStyle: { color: "rgba(91,225,255,.4)" } },
  },
};
