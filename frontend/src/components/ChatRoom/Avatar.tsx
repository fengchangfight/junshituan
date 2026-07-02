"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";

interface Props {
  src: string;
  name: string;
  size?: "sm" | "md" | "lg";
  colorClass: string;
}

const SIZE_MAP = {
  sm: "w-6 h-6 text-[10px]",
  md: "w-9 h-9 text-sm",
  lg: "w-10 h-10 text-sm",
};

export default function Avatar({ src, name, size = "md", colorClass }: Props) {
  const [error, setError] = useState(false);
  const firstChar = name?.[0] || "?";
  const sizeClass = SIZE_MAP[size];

  // Reset error state when src changes (e.g. advisor avatar URL updates)
  useEffect(() => { setError(false); }, [src]);

  if (!src || error) {
    return (
      <motion.div
        initial={{ scale: 0.8 }}
        animate={{ scale: 1 }}
        className={`shrink-0 ${sizeClass} rounded-full bg-gradient-to-br ${colorClass} flex items-center justify-center text-white font-bold shadow-md`}
      >
        {firstChar}
      </motion.div>
    );
  }

  return (
    <motion.img
      initial={{ scale: 0.8 }}
      animate={{ scale: 1 }}
      src={src}
      alt={name}
      className={`shrink-0 ${sizeClass} rounded-full object-cover bg-ink-800 shadow-md`}
      onError={() => setError(true)}
    />
  );
}
