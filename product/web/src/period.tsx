import { createContext, useContext, useState, type ReactNode } from "react";

import type { TimeRange } from "./types";

interface PeriodValue {
  range: TimeRange | null;
  setRange: (range: TimeRange) => void;
}

const PeriodContext = createContext<PeriodValue | null>(null);

export function PeriodProvider({ children }: { children: ReactNode }) {
  const [range, setRange] = useState<TimeRange | null>(null);
  return (
    <PeriodContext.Provider value={{ range, setRange }}>
      {children}
    </PeriodContext.Provider>
  );
}

export function usePeriod(): PeriodValue {
  const value = useContext(PeriodContext);
  if (value === null) throw new Error("usePeriod 必须在 PeriodProvider 内使用");
  return value;
}
