// 作者：zcy
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { CandidateListing } from "../types";

interface FavoritesState {
  byId: Record<string, CandidateListing>;
  order: string[];
  toggle: (c: CandidateListing) => void;
  clear: () => void;
}

// 本地收藏夹：id -> 房源，保持加入顺序
export const useFavorites = create<FavoritesState>()(
  persist(
    (set, get) => ({
      byId: {},
      order: [],
      toggle: (c) => {
        const { byId, order } = get();
        if (byId[c.id]) {
          const next = { ...byId };
          delete next[c.id];
          set({ byId: next, order: order.filter((id) => id !== c.id) });
        } else {
          set({ byId: { ...byId, [c.id]: c }, order: [...order, c.id] });
        }
      },
      clear: () => set({ byId: {}, order: [] }),
    }),
    { name: "rentai-favorites" },
  ),
);
