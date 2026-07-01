"use client";

import { motion } from "framer-motion";
import { Advisor } from "@/lib/types";
import { Check, User } from "lucide-react";

interface Props {
  advisor: Advisor;
  selected: boolean;
  onToggle: () => void;
  disabled: boolean;
}

const CATEGORY_COLORS: Record<string, string> = {
  军事家: "border-red-700/50 hover:border-red-500",
  哲学家: "border-purple-700/50 hover:border-purple-500",
  政治家: "border-amber-700/50 hover:border-amber-500",
  佛学大师: "border-emerald-700/50 hover:border-emerald-500",
  企业家: "border-blue-700/50 hover:border-blue-500",
};

const CATEGORY_GLOW: Record<string, string> = {
  军事家: "shadow-red-500/20",
  哲学家: "shadow-purple-500/20",
  政治家: "shadow-amber-500/20",
  佛学大师: "shadow-emerald-500/20",
  企业家: "shadow-blue-500/20",
};

export default function AdvisorCard({
  advisor,
  selected,
  onToggle,
  disabled,
}: Props) {
  const borderColor =
    CATEGORY_COLORS[advisor.category] || "border-ink-700/50 hover:border-ink-500";
  const glowColor = CATEGORY_GLOW[advisor.category] || "";

  return (
    <motion.button
      layout
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{
        opacity: disabled ? 0.3 : 1,
        pointerEvents: disabled ? "none" : "auto",
        scale: 1,
        borderColor: selected ? "rgb(212,133,44)" : undefined,
      }}
      exit={{ opacity: 0, scale: 0.8 }}
      whileHover={disabled ? undefined : { scale: 1.03, y: -4 }}
      whileTap={disabled ? undefined : { scale: 0.97 }}
      onClick={disabled ? undefined : onToggle}
      disabled={disabled}
      className={`relative w-full p-3 sm:p-5 rounded-xl sm:rounded-2xl border-2 bg-ink-900/60 backdrop-blur-sm ${borderColor} transition-all duration-300 text-left ${
        selected
          ? "border-ancient-500 shadow-lg shadow-ancient-500/20 bg-ink-900/80"
          : ""
      } ${!disabled ? glowColor : ""}`}
    >
      {selected && (
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          className="absolute -top-2 -right-2 w-7 h-7 bg-ancient-500 rounded-full flex items-center justify-center shadow-lg"
        >
          <Check size={14} className="text-white" />
        </motion.div>
      )}

      <motion.div
        className="relative w-16 h-16 sm:w-20 sm:h-20 mx-auto mb-2 sm:mb-4 rounded-full bg-gradient-to-b from-ink-800 to-ink-900 border-2 border-ink-700 flex items-center justify-center overflow-hidden"
        animate={
          selected
            ? {
                boxShadow: [
                  "0 0 10px rgba(212,133,44,0.3)",
                  "0 0 20px rgba(212,133,44,0.5)",
                  "0 0 10px rgba(212,133,44,0.3)",
                ],
              }
            : {}
        }
        transition={{ repeat: Infinity, duration: 3 }}
      >
        <User size={24} className="text-ink-500 sm:scale-100 scale-75" />
      </motion.div>

      <h3 className="text-center text-sm sm:text-lg font-bold text-ink-100 mb-0.5 sm:mb-1 font-display">
        {advisor.name}
      </h3>
      <p className="text-center text-[10px] sm:text-xs text-ancient-400 mb-1 sm:mb-2">
        {advisor.era} · {advisor.title}
      </p>
      <p className="text-center text-[10px] sm:text-xs text-ink-500 line-clamp-2 leading-relaxed">
        {advisor.style}
      </p>

      {selected && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="mt-3 pt-3 border-t border-ancient-700/30"
        >
          <p className="text-xs text-ink-400 italic leading-relaxed">
            &ldquo;{advisor.shortBio}&rdquo;
          </p>
        </motion.div>
      )}
    </motion.button>
  );
}
