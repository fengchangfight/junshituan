"use client";

import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { BookOpen, Users, Database, ArrowRight } from "lucide-react";

export default function AdminDashboard() {
  const router = useRouter();

  const cards = [
    {
      title: "知识库管理",
      desc: "管理每个军师的著作、言论和解读资料",
      icon: BookOpen,
      href: "/admin/advisors",
      color: "from-emerald-600/20 to-emerald-800/20 border-emerald-700/30",
    },
    {
      title: "用户管理",
      desc: "管理注册用户和权限",
      icon: Users,
      href: "/admin/users",
      color: "from-blue-600/20 to-blue-800/20 border-blue-700/30",
      disabled: true,
    },
    {
      title: "系统监控",
      desc: "查看系统运行状态和统计",
      icon: Database,
      href: "/admin/stats",
      color: "from-purple-600/20 to-purple-800/20 border-purple-700/30",
      disabled: true,
    },
  ];

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-8">
        <h2 className="text-2xl font-display text-ink-200">管理面板</h2>
        <p className="text-sm text-ink-500 mt-1">管理军师团的知识库和系统配置</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((card) => (
          <motion.button
            key={card.href}
            whileHover={card.disabled ? {} : { scale: 1.02, y: -2 }}
            whileTap={card.disabled ? {} : { scale: 0.98 }}
            onClick={() => !card.disabled && router.push(card.href)}
            disabled={card.disabled}
            className={`relative p-6 rounded-2xl border bg-gradient-to-br ${card.color} backdrop-blur-sm text-left transition-all ${
              card.disabled ? "opacity-40 cursor-not-allowed" : "cursor-pointer hover:shadow-lg"
            }`}
          >
            <card.icon size={24} className="text-ink-300 mb-3" />
            <h3 className="text-lg font-bold text-ink-100 mb-1">{card.title}</h3>
            <p className="text-xs text-ink-500">{card.desc}</p>
            {!card.disabled && (
              <ArrowRight size={16} className="absolute bottom-4 right-4 text-ink-600" />
            )}
            {card.disabled && (
              <span className="absolute top-3 right-3 text-[10px] bg-ink-800 text-ink-500 px-2 py-0.5 rounded-full">
                即将推出
              </span>
            )}
          </motion.button>
        ))}
      </div>
    </div>
  );
}
