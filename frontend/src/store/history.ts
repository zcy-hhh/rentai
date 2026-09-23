// 作者：zcy
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { RentRequirement } from "../types";

const MAX = 8;

interface HistoryState {
  items: RentRequirement[];
  add: (req: RentRequirement) => void;
  clear: () => void;
}

// 本地历史搜索记录（去重 + 去空需求，最多保留 MAX 条）
export const useHistory = create<HistoryState>()(
  persist(
    (set, get) => ({
      items: [],
      add: (req) => {
        const key = JSON.stringify(req);
        const rest = get().items.filter((r) => JSON.stringify(r) !== key);
        set({ items: [req, ...rest].slice(0, MAX) });
      },
      clear: () => set({ items: [] }),
    }),
    { name: "rentai-history" },
  ),
);
