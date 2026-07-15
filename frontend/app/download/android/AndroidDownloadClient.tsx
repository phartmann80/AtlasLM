"use client";

import React from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import Header from "../../../components/layout/header";
import Footer from "../../../components/layout/footer";

// SVG Icons (no emojis, professional)
const AndroidIcon = () => (
  <svg className="w-8 h-8 text-green-500" fill="currentColor" viewBox="0 0 24 24">
    <path d="M17.523 15.3c-.551 0-1.002-.445-1.002-.996 0-.552.451-1 .1-1 .552 0 1 .448 1 1 0 .551-.448.996-.998.996zm-11.046 0c-.551 0-1-.445-1-.996 0-.552.449-1 .998-1 .552 0 1 .448 1 1 0 .551-.448.996-.998.996zm11.417-6.071l2.003-3.472a.498.498 0 0 0-.183-.681.498.498 0 0 0-.681.183l-2.018 3.498a10.937 10.937 0 0 0-7.036 0L5.964 5.257a.496.496 0 0 0-.68-.183.498.498 0 0 0-.183.681l2.002 3.472C3.216 11.237 1 14.364 1 18h22c0-3.636-2.216-6.763-6.096-8.771z" />
  </svg>
);

const ArrowLeft = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
    <path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
  </svg>
);

const ShieldIcon = () => (
  <svg className="w-5 h-5 text-orange-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
  </svg>
);

const TerminalIcon = () => (
  <svg className="w-5 h-5 text-orange-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
    <path strokeLinecap="round" strokeLinejoin="round" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
  </svg>
);

const CpuIcon = () => (
  <svg className="w-5 h-5 text-orange-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 5h10a2 2 0 012 2v10a2 2 0 01-2 2H7a2 2 0 01-2-2V7a2 2 0 012-2z" />
  </svg>
);

export default function AndroidDownloadPage() {
  return (
    <div className="relative min-h-screen bg-zinc-950 flex flex-col justify-between overflow-hidden">
      {/* Background glow effects */}
      <div className="absolute inset-0 radial-glow pointer-events-none" />
      <div className="absolute inset-0 radial-glow-purple pointer-events-none" />

      <Header />

      <main className="flex-grow pt-32 pb-24 px-6 max-w-6xl mx-auto relative z-10 w-full flex flex-col items-center">

        {/* Back Link */}
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-zinc-500 hover:text-white transition-colors duration-200 self-start mb-8 text-sm group"
        >
          <span className="transform group-hover:-translate-x-1 transition-transform"><ArrowLeft /></span>
          Back to home
        </Link>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center w-full">

          {/* Left Column: Premium App Description */}
          <div className="flex flex-col text-left">
            <motion.div
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-green-500/30 bg-green-950/20 text-xs font-semibold text-green-400 mb-6 w-fit"
            >
              <AndroidIcon />
              <span className="ml-1 text-[11px] uppercase tracking-wider font-bold">Android Native Client</span>
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1 }}
              className="text-4xl md:text-5xl font-extrabold tracking-tight text-white mb-6 leading-tight"
            >
              AtlasLM for Android <br />
              <span className="bg-clip-text text-transparent bg-gradient-to-r from-green-400 via-emerald-500 to-teal-500">
                APK COMING SOON
              </span>
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.2 }}
              className="text-zinc-400 leading-relaxed mb-8 text-sm md:text-base"
            >
              Take your source-grounded research workspaces anywhere. The upcoming fully native Android application delivers high-performance, private AI notebooks directly to your pocket. Connect securely to your personal staging deployment or utilize local model networks on the fly.
            </motion.p>

            {/* Premium CTA Buttons */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.3 }}
              className="flex flex-col sm:flex-row gap-4 mb-8"
            >
              {/* Intentional Placeholder Download Button */}
              <div className="flex flex-col gap-1.5 w-full sm:w-auto">
                <button
                  disabled
                  className="px-6 py-4 rounded-xl font-bold bg-zinc-900 border border-zinc-800 text-zinc-500 cursor-not-allowed flex items-center justify-center gap-3 transition-all duration-200"
                >
                  <svg className="w-5 h-5 text-zinc-600" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clipRule="evenodd" />
                  </svg>
                  Install Android App
                </button>
                <span className="text-[10px] text-zinc-600 font-medium text-center sm:text-left">
                  APK Installer coming soon • v1.0.0-beta
                </span>
              </div>

              <Link
                href="/about"
                className="px-6 py-4 rounded-xl font-bold border border-zinc-800 bg-zinc-950 text-zinc-400 hover:text-white hover:bg-zinc-900/60 text-center flex items-center justify-center transition-all duration-200"
              >
                Meet the Founders
              </Link>
            </motion.div>

            {/* Architecture Commitments List */}
            <div className="border-t border-zinc-900 pt-8 flex flex-col gap-4">
              <div className="flex items-start gap-4">
                <div className="p-2 bg-orange-950/20 border border-orange-500/20 rounded-lg text-orange-500">
                  <ShieldIcon />
                </div>
                <div>
                  <h4 className="text-sm font-bold text-white mb-1">Zero Secrets Kept Locally</h4>
                  <p className="text-xs text-zinc-500 leading-relaxed">
                    Unlike naive client implementations, the Android app stores no API keys, secrets, or provider credentials. All routing and keys reside securely inside your isolated staging backend.
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-4">
                <div className="p-2 bg-orange-950/20 border border-orange-500/20 rounded-lg text-orange-500">
                  <CpuIcon />
                </div>
                <div>
                  <h4 className="text-sm font-bold text-white mb-1">Same Robust Provider Stack</h4>
                  <p className="text-xs text-zinc-500 leading-relaxed">
                    Connect seamlessly to premium AI providers, Blackbox AI, OpenRouter, and custom local endpoints with streaming SSE and full-speed page parsing.
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-4">
                <div className="p-2 bg-orange-950/20 border border-orange-500/20 rounded-lg text-orange-500">
                  <TerminalIcon />
                  </div>
                <div>
                  <h4 className="text-sm font-bold text-white mb-1">100% Fully Native Engine</h4>
                  <p className="text-xs text-zinc-500 leading-relaxed">
                    No low-performance WebView containers. The app is crafted with a high-fidelity native canvas, boasting hardware-accelerated animations and an adaptive dark theme.
                  </p>
                </div>
              </div>
            </div>

          </div>

          {/* Right Column: High-Fidelity Mobile App Device Simulation mockup */}
          <div className="flex justify-center w-full relative">
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.7, delay: 0.2 }}
              className="w-[280px] h-[560px] rounded-[36px] border-[6px] border-zinc-800 bg-zinc-950 shadow-2xl relative overflow-hidden flex flex-col p-4 shadow-black/80 ring-4 ring-zinc-900"
            >
              {/* Speaker notch */}
              <div className="absolute top-2 left-1/2 -translate-x-1/2 w-16 h-3.5 bg-zinc-850 rounded-full flex items-center justify-center border border-zinc-800">
                <div className="w-1.5 h-1.5 rounded-full bg-zinc-700" />
              </div>

              {/* Status bar */}
              <div className="flex justify-between items-center px-2 pt-1 text-[8px] font-mono text-zinc-500 mb-6 mt-1">
                <span>14:02</span>
                <div className="flex items-center gap-1.5">
                  <span>5G</span>
                  <div className="w-3.5 h-2 border border-zinc-500 rounded-sm p-0.5 flex">
                    <div className="h-full w-full bg-zinc-500 rounded-2xs" />
                  </div>
                </div>
              </div>

              {/* Simulated UI Header */}
              <div className="flex justify-between items-center border-b border-zinc-900 pb-3 mb-4">
                <div className="flex items-center gap-1.5">
                  <div className="w-4 h-4 rounded bg-orange-600 flex items-center justify-center font-extrabold text-[8px] text-white">A</div>
                  <span className="text-[10px] font-bold text-white">AtlasLM Mobile</span>
                </div>
                <div className="px-2 py-0.5 rounded-full bg-zinc-900 border border-zinc-800 text-[6px] font-bold text-zinc-400">
                  Staging: active
                </div>
              </div>

              {/* Simulated UI Body */}
              <div className="flex-grow flex flex-col justify-between">
                <div className="flex flex-col gap-4">
                  {/* Upload card */}
                  <div className="rounded-xl border border-zinc-900 bg-zinc-900/40 p-3 text-left">
                    <div className="flex justify-between items-center mb-2">
                      <span className="text-[8px] text-zinc-400 font-semibold">Active Notebook</span>
                      <span className="text-[6px] text-orange-400 bg-orange-950/40 border border-orange-500/20 px-1 py-0.2 rounded font-semibold uppercase">PDF</span>
                    </div>
                    <p className="text-[10px] text-white font-bold leading-tight truncate">attention-all-you-need.pdf</p>
                    <div className="w-full bg-zinc-850 h-1 rounded-full mt-2 overflow-hidden">
                      <div className="bg-orange-500 h-full w-[85%]" />
                    </div>
                  </div>

                  {/* Grounded chat message bubbles */}
                  <div className="flex flex-col gap-2.5">
                    <div className="self-end bg-zinc-900 border border-zinc-800/80 rounded-xl rounded-br-none p-2.5 max-w-[85%] text-left">
                      <p className="text-[8px] text-zinc-300">How does AtlasLM ensure absolute source grounding?</p>
                    </div>

                    <div className="self-start bg-orange-950/10 border border-orange-500/10 rounded-xl rounded-bl-none p-2.5 max-w-[90%] text-left relative">
                      <p className="text-[8px] text-zinc-300 leading-normal">
                        AtlasLM splits source PDFs into deterministic chunks with offset metadata. The vector database restricts queries strictly to these chunks, enforcing inline page citations <span className="inline-flex px-1 bg-orange-500/25 border border-orange-500/30 text-orange-400 rounded text-[6px] font-bold">p.4</span> to ensure verifiable accuracy.
                      </p>
                    </div>
                  </div>
                </div>

                {/* Simulated Input field */}
                <div className="border-t border-zinc-900 pt-3">
                  <div className="rounded-lg bg-zinc-900 border border-zinc-800/80 p-2 flex items-center justify-between">
                    <span className="text-[8px] text-zinc-650">Ask your notebook...</span>
                    <div className="p-1 rounded-md bg-orange-600 text-white">
                      <svg className="w-2.5 h-2.5" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10.293 3.293a1 1 0 011.414 0l6 6a1 1 0 010 1.414l-6 6a1 1 0 01-1.414-1.414L14.586 11H3a1 1 0 110-2h11.586l-4.293-4.293a1 1 0 010-1.414z" clipRule="evenodd" />
                      </svg>
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>

            {/* Glowing neon green accent around mockup to symbolize android */}
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[340px] h-[620px] bg-green-500/5 rounded-[48px] blur-2xl pointer-events-none -z-10" />
          </div>

        </div>

      </main>

      <Footer />
    </div>
  );
}
