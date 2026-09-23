// 作者：zcy
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef6ff",
          100: "#d9ecff",
          200: "#b6dafc",
          300: "#8cc2f7",
          400: "#5ba1ee",
          500: "#2f7de0",
          600: "#2563c8",
          700: "#1e50a0",
          800: "#1b4388",
          900: "#17396f",
        },
        accent: {
          50: "#fdf4ff",
          100: "#fae8ff",
          500: "#d946ef",
          600: "#c026d3",
        },
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06)",
        lift: "0 4px 12px rgba(16,24,40,0.10)",
        glow: "0 0 0 4px rgba(47,125,224,0.12)",
      },
      keyframes: {
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
        fadeIn: {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        pop: {
          "0%": { transform: "scale(0.96)", opacity: "0" },
          "100%": { transform: "scale(1)", opacity: "1" },
        },
      },
      animation: {
        fadeIn: "fadeIn 0.25s ease-out",
        pop: "pop 0.18s ease-out",
      },
    },
  },
  plugins: [],
};
