"use client";

import { motion } from "framer-motion";
import { AlertTriangle } from "lucide-react";

interface Props {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmModal({
  open,
  title,
  message,
  confirmLabel = "确认",
  cancelLabel = "取消",
  danger = false,
  onConfirm,
  onCancel,
}: Props) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={onCancel}
    >
      <motion.div
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        onClick={(e) => e.stopPropagation()}
        className="bg-ink-900 border border-ink-700 rounded-2xl p-6 w-full max-w-sm mx-4 shadow-2xl"
      >
        <div className="flex items-start gap-3 mb-4">
          <div className={`p-2 rounded-xl shrink-0 ${danger ? "bg-red-900/30" : "bg-amber-900/30"}`}>
            <AlertTriangle size={20} className={danger ? "text-red-400" : "text-amber-400"} />
          </div>
          <div>
            <h3 className="text-base font-bold text-ink-100">{title}</h3>
            <p className="text-sm text-ink-400 mt-1">{message}</p>
          </div>
        </div>
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 py-2.5 rounded-xl bg-ink-800 hover:bg-ink-700 text-ink-300 text-sm font-medium transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            className={`flex-1 py-2.5 rounded-xl text-sm font-medium transition-all ${
              danger
                ? "bg-red-600/30 hover:bg-red-600/50 border border-red-600/40 text-red-400"
                : "bg-ancient-700 hover:bg-ancient-600 text-white"
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </motion.div>
    </div>
  );
}
