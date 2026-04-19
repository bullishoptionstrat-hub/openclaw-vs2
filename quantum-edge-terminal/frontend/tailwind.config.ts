import type { Config } from "next";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        "qt-dark": "#0a0e27",
        "qt-darker": "#050814",
        "qt-accent": "#00d9ff",
        "qt-accent-alt": "#8b5cf6",
        "qt-buy": "#00ff41",
        "qt-sell": "#ff375f",
      },
      fontFamily: {
        mono: ["Monaco", "Courier New", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
