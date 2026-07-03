"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { BookOpen, Users, Database, ArrowRight } from "lucide-react";

export default function AdminDashboard() {
  const router = useRouter();

  useEffect(() => {
    // Auto-redirect to advisors management for all users
    router.push("/admin/advisors");
  }, []);

  return (
    <div className="max-w-4xl mx-auto flex items-center justify-center py-20">
      <p className="text-ink-500">跳转中...</p>
    </div>
  );
}
