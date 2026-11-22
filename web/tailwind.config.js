/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0f1115",
        panel: "#151922",
        line: "#262b36",
        bad: "#ff8fa3",
        good: "#7ee2b8",
        warn: "#ffd08a",
        info: "#a9c6ff",
      },
      fontFamily: {
        sans: ["-apple-system", "Segoe UI", "Microsoft YaHei", "sans-serif"],
        mono: ["ui-monospace", "Cascadia Mono", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
