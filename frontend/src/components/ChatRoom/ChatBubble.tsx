"use client";

import { motion } from "framer-motion";
import { Advisor, Message } from "@/lib/types";
import Avatar from "./Avatar";

interface Props {
  message: Message;
  advisor?: Advisor;
  avatarColor: string;
  showAvatar: boolean;
}

function ThinkingDots() {
  return (
    <div className="flex gap-1 px-2 py-3">
      {[0, 1, 2].map((i) => (
        <motion.div
          key={i}
          className="w-2 h-2 rounded-full bg-ancient-400/60"
          animate={{ opacity: [0.2, 0.8, 0.2], y: [0, -3, 0] }}
          transition={{ repeat: Infinity, duration: 1.2, delay: i * 0.2 }}
        />
      ))}
    </div>
  );
}

export default function ChatBubble({
  message,
  advisor,
  avatarColor,
  showAvatar,
}: Props) {
  if (message.role === "system") {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex justify-center py-4"
      >
        <span className="text-xs text-ink-600 bg-ink-900/40 px-4 py-1.5 rounded-full">
          {message.content}
        </span>
      </motion.div>
    );
  }

  const isUser = message.role === "user";
  const isStreaming = message.isStreaming && message.content === "";
  const isPartial = message.isStreaming && message.content !== "";

  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, x: 10 }}
        animate={{ opacity: 1, x: 0 }}
        className="flex justify-end py-1.5"
      >
        <div className="max-w-[75%]">
          <motion.div className="bg-gradient-to-r from-ancient-600 to-ancient-700 text-white rounded-2xl rounded-tr-md px-4 py-2.5 text-sm leading-relaxed shadow-md">
            <p className="whitespace-pre-wrap break-words">
              {message.content}
            </p>
          </motion.div>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      className="flex gap-2.5 py-1.5"
    >
      {showAvatar ? (
        <div className="mt-0.5">
          <Avatar
            src={advisor?.avatar || ""}
            name={advisor?.name || "?"}
            size="md"
            colorClass={avatarColor}
          />
        </div>
      ) : (
        <div className="w-9 shrink-0" />
      )}

      <div className="min-w-0 max-w-[75%]">
        {showAvatar && advisor && (
          <div className="flex items-center gap-1.5 mb-0.5 ml-0.5">
            <span className="text-xs font-bold text-ink-300">
              {advisor.name}
            </span>
            {isStreaming && (
              <motion.span
                animate={{ opacity: [0.3, 1, 0.3] }}
                transition={{ repeat: Infinity, duration: 1 }}
                className="text-[10px] text-ancient-400"
              >
                思考中...
              </motion.span>
            )}
          </div>
        )}

        <div
          className={`rounded-2xl rounded-tl-sm px-4 py-2.5 text-sm leading-relaxed bg-ink-900/80 border border-ink-800/40 text-ink-200 shadow-sm`}
        >
          {isStreaming ? (
            <ThinkingDots />
          ) : (
            <p className="whitespace-pre-wrap break-words">
              {message.content}
              {isPartial && (
                <motion.span
                  animate={{ opacity: [1, 0] }}
                  transition={{ repeat: Infinity, duration: 0.5 }}
                  className="inline-block w-1 h-4 bg-ancient-400 ml-0.5 align-middle rounded-sm"
                />
              )}
            </p>
          )}
        </div>
      </div>
    </motion.div>
  );
}
