"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import Header from "../../components/layout/header";
import Footer from "../../components/layout/footer";
import { apiUrl } from "@/lib/apiBase";

export default function ContactPage() {
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    message: "",
    captchaAnswer: "",
  });

  const [captcha, setCaptcha] = useState({ num1: 0, num2: 0, sum: 0 });
  const [submitStatus, setSubmitStatus] = useState<{
    type: "idle" | "loading" | "success" | "error";
    message: string;
  }>({ type: "idle", message: "" });

  // Generate a random math equation on mount or reset
  const generateCaptcha = () => {
    const num1 = Math.floor(Math.random() * 9) + 2; // 2 to 10
    const num2 = Math.floor(Math.random() * 9) + 2; // 2 to 10
    setCaptcha({ num1, num2, sum: num1 + num2 });
    setFormData((prev) => ({ ...prev, captchaAnswer: "" }));
  };

  useEffect(() => {
    generateCaptcha();
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitStatus({ type: "loading", message: "Sending your message..." });

    const answer = parseInt(formData.captchaAnswer, 10);
    if (isNaN(answer) || answer !== captcha.sum) {
      setSubmitStatus({
        type: "error",
        message: "Incorrect Captcha answer. Please try again.",
      });
      generateCaptcha();
      return;
    }

    try {
      const response = await fetch(apiUrl("/contact"), {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          name: formData.name,
          email: formData.email,
          message: formData.message,
          captcha_answer: formData.captchaAnswer,
          captcha_expected: captcha.sum.toString(),
        }).toString(),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Server error");
      }

      setSubmitStatus({
        type: "success",
        message: "Thank you! Your message has been received.",
      });
      setFormData({ name: "", email: "", message: "", captchaAnswer: "" });
      generateCaptcha();
    } catch (err: any) {
      setSubmitStatus({
        type: "error",
        message: err.message || "Failed to reach the API server.",
      });
    }
  };

  return (
    <div className="relative min-h-screen bg-zinc-950 flex flex-col justify-between overflow-hidden">
      {/* Background glow effects */}
      <div className="absolute inset-0 radial-glow pointer-events-none" />
      <div className="absolute inset-0 radial-glow-purple pointer-events-none" />

      <Header />

      <main className="flex-grow pt-32 pb-24 px-6 max-w-lg mx-auto relative z-10 w-full">
        {/* Title */}
        <div className="text-center mb-12">
          <span className="text-xs font-bold uppercase tracking-wider text-orange-500">Get in touch</span>
          <h1 className="text-3xl md:text-5xl font-extrabold tracking-tight text-white mt-2 mb-3">
            Contact AtlasLM
          </h1>
          <p className="text-zinc-500 text-sm leading-relaxed">
            Send us a message about features, custom local integrations, or platform inquiries.
          </p>
        </div>

        {/* Contact Form Container */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="rounded-2xl glass-panel p-8 shadow-xl shadow-black/40 border border-zinc-900 bg-zinc-950/40 relative"
        >
          {/* Status Message Banner */}
          {submitStatus.type !== "idle" && (
            <div
              className={`mb-6 p-4 rounded-lg text-xs font-semibold border ${
                submitStatus.type === "success"
                  ? "bg-green-950/20 border-green-500/30 text-green-400"
                  : submitStatus.type === "error"
                  ? "bg-red-950/20 border-red-500/30 text-red-400"
                  : "bg-zinc-900 border-zinc-800 text-zinc-350"
              }`}
            >
              {submitStatus.message}
            </div>
          )}

          <form onSubmit={handleSubmit} className="flex flex-col gap-6">
            {/* Name Input */}
            <div className="flex flex-col gap-2">
              <label htmlFor="name" className="text-xs font-bold uppercase tracking-wider text-zinc-400">
                Your Name
              </label>
              <input
                type="text"
                id="name"
                name="name"
                required
                value={formData.name}
                onChange={handleChange}
                placeholder="Developer/Builder"
                className="w-full bg-zinc-900 border border-zinc-800 rounded-lg p-3 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-700 transition-colors"
              />
            </div>

            {/* Email Input */}
            <div className="flex flex-col gap-2">
              <label htmlFor="email" className="text-xs font-bold uppercase tracking-wider text-zinc-400">
                Email Address
              </label>
              <input
                type="email"
                id="email"
                name="email"
                required
                value={formData.email}
                onChange={handleChange}
                placeholder="name@domain.com"
                className="w-full bg-zinc-900 border border-zinc-800 rounded-lg p-3 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-700 transition-colors"
              />
            </div>

            {/* Message Area */}
            <div className="flex flex-col gap-2">
              <label htmlFor="message" className="text-xs font-bold uppercase tracking-wider text-zinc-400">
                Message Description
              </label>
              <textarea
                id="message"
                name="message"
                required
                rows={5}
                value={formData.message}
                onChange={handleChange}
                placeholder="Inquire about custom vector structures..."
                className="w-full bg-zinc-900 border border-zinc-800 rounded-lg p-3 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-700 transition-colors resize-none"
              />
            </div>

            {/* Math Developer Captcha */}
            <div className="flex flex-col gap-2 border-t border-zinc-900/60 pt-4">
              <label htmlFor="captchaAnswer" className="text-xs font-bold uppercase tracking-wider text-orange-500">
                Security Question (Math Captcha)
              </label>
              <div className="flex items-center gap-4">
                {/* Visual Math Problem Pill */}
                <div className="bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-3 text-sm text-zinc-200 font-mono select-none">
                  {captcha.num1} + {captcha.num2} =
                </div>
                <input
                  type="text"
                  id="captchaAnswer"
                  name="captchaAnswer"
                  required
                  value={formData.captchaAnswer}
                  onChange={handleChange}
                  placeholder="?"
                  className="w-24 bg-zinc-900 border border-zinc-800 rounded-lg p-3 text-sm text-zinc-200 placeholder-zinc-600 text-center font-mono focus:outline-none focus:border-zinc-700 transition-colors"
                />
              </div>
              <p className="text-[10px] text-zinc-600 mt-1">Lightweight privacy-friendly bot blocker. No trackers used.</p>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={submitStatus.type === "loading"}
              className="w-full bg-gradient-to-r from-orange-600 to-red-600 hover:from-orange-500 hover:to-red-500 text-white font-bold py-3.5 rounded-lg text-xs tracking-wider uppercase transition-all duration-300 shadow-[0_0_15px_rgba(234,88,12,0.3)] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitStatus.type === "loading" ? "Submitting..." : "Send Message"}
            </button>
          </form>
        </motion.div>

        {/* Android Download Card */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
          className="rounded-2xl border border-zinc-900 bg-zinc-950/40 p-6 mt-8 flex items-center justify-between gap-4 relative overflow-hidden"
        >
          {/* Subtle green glow backdrop */}
          <div className="absolute -right-10 -bottom-10 w-24 h-24 bg-green-500/5 rounded-full blur-xl pointer-events-none" />

          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-green-950/20 border border-green-500/20 rounded-xl text-green-400">
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M17.523 15.3c-.551 0-1.002-.445-1.002-.996 0-.552.451-1 .1-1 .552 0 1 .448 1 1 0 .551-.448.996-.998.996zm-11.046 0c-.551 0-1-.445-1-.996 0-.552.449-1 .998-1 .552 0 1 .448 1 1 0 .551-.448.996-.998.996zm11.417-6.071l2.003-3.472a.498.498 0 0 0-.183-.681.498.498 0 0 0-.681.183l-2.018 3.498a10.937 10.937 0 0 0-7.036 0L5.964 5.257a.496.496 0 0 0-.68-.183.498.498 0 0 0-.183.681l2.002 3.472C3.216 11.237 1 14.364 1 18h22c0-3.636-2.216-6.763-6.096-8.771z" />
              </svg>
            </div>
            <div className="text-left">
              <h4 className="text-xs font-bold text-white uppercase tracking-wider">Install Android App</h4>
              <p className="text-[10px] text-zinc-500">Android APK coming soon</p>
            </div>
          </div>
          <Link
            href="/download/android"
            className="px-4 py-2 rounded-lg bg-zinc-900 border border-zinc-800 text-[10px] font-bold text-zinc-350 hover:text-white hover:bg-zinc-850 transition-colors shrink-0"
          >
            Get Beta APK
          </Link>
        </motion.div>
      </main>

      <Footer />
    </div>
  );
}
