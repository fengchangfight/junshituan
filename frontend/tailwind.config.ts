import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ancient: {
          50: "#fdf8f0",
          100: "#f9eddb",
          200: "#f2d7b0",
          300: "#e9bb7b",
          400: "#df9d4a",
          500: "#d4852c",
          600: "#b86b22",
          700: "#96521e",
          800: "#7a4220",
          900: "#64381d",
          950: "#3a1c0e",
        },
        jade: {
          50: "#f0f9f4",
          500: "#2d8a56",
          600: "#1f6e43",
          700: "#195837",
        },
        ink: {
          50: "#f7f5f0",
          100: "#ede8db",
          200: "#dcd1b7",
          300: "#c7b58c",
          400: "#b59d6b",
          500: "#a68b58",
          600: "#8f724a",
          700: "#745a3e",
          800: "#624c38",
          900: "#2a1f15",
          950: "#1a120b",
        },
      },
      fontFamily: {
        serif: ["Noto Serif SC", "STSong", "SimSun", "serif"],
        display: ["ZCOOL KuaiLe", "cursive"],
      },
      animation: {
        "pulse-soft": "pulseSoft 3s ease-in-out infinite",
        "float": "float 6s ease-in-out infinite",
        "glow": "glow 2s ease-in-out infinite alternate",
        "typewriter": "typewriter 0.05s steps(1) forwards",
      },
      keyframes: {
        pulseSoft: {
          "0%, 100%": { opacity: "0.6" },
          "50%": { opacity: "1" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-10px)" },
        },
        glow: {
          "0%": { boxShadow: "0 0 5px rgba(212,133,44,0.3)" },
          "100%": { boxShadow: "0 0 20px rgba(212,133,44,0.6)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
