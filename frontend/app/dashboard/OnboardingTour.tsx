"use client";

import React, { useEffect, useState } from "react";
import { apiClient } from "@/lib/apiClient";
import "./research-canvas.css";
// Copy is final. It is humanized on purpose: no em dashes, no ellipses.
// Do not rewrite these strings.
export const TOUR_STEPS = [
  {
    title: "Your Sources",
    desc: "Everything starts with your material. Upload PDFs, spreadsheets, slides, and websites, or paste a YouTube link and AtlasLM transcribes it. Every source is indexed and becomes citable.",
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <path d="M14 2v6h6" />
      </svg>
    ),
  },
  {
    title: "Grounded Chat",
    desc: "Ask anything about your sources. AtlasLM answers only from your material; every claim carries a citation chip you can click to jump to the exact page, row, or video timestamp.",
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
      </svg>
    ),
  },
  {
    title: "Source Map",
    desc: "See your notebook as a working map: sources on one side, AtlasLM in the center, and generated outputs on the other. It shows what is ready, what is indexing, and where to go next.",
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="6" cy="6" r="3" />
        <circle cx="18" cy="18" r="3" />
        <path d="M8.5 8.5L15.5 15.5" />
      </svg>
    ),
  },
  {
    title: "Studio",
    desc: "Turn sources into deliverables. Generate study guides, mind maps, quizzes, flashcards, and audio overviews from the material in your notebook.",
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 3l1.9 5.8a2 2 0 0 0 1.3 1.3L21 12l-5.8 1.9a2 2 0 0 0-1.3 1.3L12 21l-1.9-5.8a2 2 0 0 0-1.3-1.3L3 12l5.8-1.9a2 2 0 0 0 1.3-1.3L12 3z" />
      </svg>
    ),
  },
  { final: true },
] as const;

export function OnboardingTour() {
  const [visible, setVisible] = useState(false);
  const [step, setStep] = useState(0);
  const [optIn, setOptIn] = useState(false);

  // Gate: only first-time users see the tour, after the intro animation ends.
  useEffect(() => {
    (async () => {
      try {
        const flags = await apiClient.get<any>("/api/v1/me/onboarding");
        if (!flags.tour_completed) {
          // listen for the intro's completion event, then show
          const show = () => setVisible(true);
          window.addEventListener("atlaslm:intro-done", show, { once: true });
          
          // fallback if intro is skipped/cached
          const t = setTimeout(show, 2500);
          return () => {
            clearTimeout(t);
            window.removeEventListener("atlaslm:intro-done", show);
          };
        }
      } catch (err) {
        console.error("Failed to fetch onboarding flags:", err);
      }
    })();
  }, []);

  async function finish() {
    setVisible(false);
    try {
      await apiClient.patch("/api/v1/me/onboarding", {
        tour_completed: true,
        marketing_opt_in: optIn,
      });
    } catch (err) {
      console.error("Failed to update onboarding flags:", err);
    }
  }

  // Keyboard: Enter/ArrowRight next, ArrowLeft back, Escape skip (also finish()).
  useEffect(() => {
    if (!visible) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Enter" || e.key === "ArrowRight") {
        setStep((s) => {
          if (s < TOUR_STEPS.length - 1) {
            return s + 1;
          } else {
            finish();
            return s;
          }
        });
      }
      if (e.key === "ArrowLeft") {
        setStep((s) => Math.max(0, s - 1));
      }
      if (e.key === "Escape") {
        finish();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [visible, optIn]); // eslint-disable-line

  if (!visible) return null;

  const currentStep = TOUR_STEPS[step];
  const isFinalStep = "final" in currentStep && currentStep.final;

  return (
    <div className={`tour-backdrop ${visible ? "show" : ""}`}>
      <div className={`tour ${isFinalStep ? "final-mode" : ""}`} id="tourBox">
        <div className="tour-aurora" />
        <span className="tour-step-badge" id="tourBadge">
          {step + 1} of {TOUR_STEPS.length}
        </span>
        <button className="tour-close" onClick={finish} title="Skip tour">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>

        {/* LEFT: copy */}
        {!isFinalStep && (
          <div className="tour-left">
            <div className="tour-icon" id="tourIcon">
              {"icon" in currentStep ? currentStep.icon : null}
            </div>
            <h2 id="tourTitle">{"title" in currentStep ? currentStep.title : ""}</h2>
            <p id="tourDesc">{"desc" in currentStep ? currentStep.desc : ""}</p>
            
            <div className="tour-cta-row">
              <button
                className="tour-next"
                id="tourNextBtn"
                onClick={() => setStep((s) => s + 1)}
              >
                Continue
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 12h14M12 5l7 7-7 7" />
                </svg>
              </button>
              {step > 0 && (
                <button
                  className="tour-back"
                  id="tourBackBtn"
                  onClick={() => setStep((s) => s - 1)}
                >
                  Back
                </button>
              )}
            </div>
          </div>
        )}

        {/* RIGHT: live preview */}
        {!isFinalStep && (
          <div className="tour-right">
            {/* STEP 1: Sources */}
            {step === 0 && (
              <div className="tour-slide on">
                <h3>Sources</h3>
                <div className="pv-row">
                  <div className="pv-ic">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#f87171" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <path d="M14 2v6h6" />
                    </svg>
                  </div>
                  <div>
                    <div className="t">Market_Report_2026.pdf</div>
                    <div className="s">PDF · 42 pages</div>
                  </div>
                  <span className="badge">INDEXED</span>
                </div>
                <div className="pv-row">
                  <div className="pv-ic">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#4ade80" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="3" width="18" height="18" rx="2" />
                      <path d="M3 9h18M9 3v18" />
                    </svg>
                  </div>
                  <div>
                    <div className="t">competitor_pricing.xlsx</div>
                    <div className="s">Spreadsheet · 6 sheets</div>
                  </div>
                  <span className="badge">INDEXED</span>
                </div>
                <div className="pv-row">
                  <div className="pv-ic">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="2" y="5" width="20" height="14" rx="4" />
                      <path d="M10 9.5v5l4.5-2.5z" fill="#ef4444" stroke="none" />
                    </svg>
                  </div>
                  <div>
                    <div className="t">CEO Keynote Q2</div>
                    <div className="s">YouTube · transcript · 38:12</div>
                  </div>
                  <span className="badge">INDEXED</span>
                </div>
                <div className="pv-row">
                  <div className="pv-ic">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#60a5fa" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="9" />
                      <path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18" />
                    </svg>
                  </div>
                  <div>
                    <div className="t">techcrunch.com/article</div>
                    <div className="s">Website · clean extraction</div>
                  </div>
                  <span className="badge">INDEXED</span>
                </div>
              </div>
            )}

            {/* STEP 2: Grounded Chat */}
            {step === 1 && (
              <div className="tour-slide on">
                <h3>Grounded Chat</h3>
                <div className="pv-bubble-user">What did the CEO say about pricing for next quarter?</div>
                <div className="pv-bubble-ai">
                  The CEO outlined a tiered pricing shift starting Q3, moving the entry plan to usage-based billing
                  <span className="cite-chip">1</span> and holding enterprise rates flat through year-end
                  <span className="cite-chip">2</span>. The keynote framed this as a response to competitor pricing pressure
                  documented in the market report <span className="cite-chip">3</span>.
                </div>
                <div style={{ display: "flex", gap: "7px", marginTop: "12px" }}>
                  <span className="cite-chip" style={{ fontSize: "9.5px", padding: "4px 9px" }}>
                    1 · CEO Keynote @ 12:41
                  </span>
                  <span className="cite-chip" style={{ fontSize: "9.5px", padding: "4px 9px" }}>
                    2 · Keynote @ 14:05
                  </span>
                  <span className="cite-chip" style={{ fontSize: "9.5px", padding: "4px 9px" }}>
                    3 · Market Report p.18
                  </span>
                </div>
              </div>
            )}

            {/* STEP 3: Source Map */}
            {step === 2 && (
              <div className="tour-slide on">
                <h3>Source Map</h3>
                <div className="pv-canvas">
                  <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} fill="none">
                    <path d="M 128 62 C 168 62, 168 110, 208 110" stroke="#22c55e" strokeWidth="1.5" opacity=".8" />
                    <path d="M 128 178 C 168 178, 168 124, 208 124" stroke="#22c55e" strokeWidth="1.5" opacity=".8" />
                    <circle r="2.5" fill="#22c55e">
                      <animateMotion dur="2.4s" repeatCount="indefinite" path="M 128 62 C 168 62, 168 110, 208 110" />
                    </circle>
                  </svg>
                  <div className="pv-node" style={{ top: "34px", left: "12px" }}>
                    <div className="h">
                      <i style={{ backgroundColor: "#f87171", width: "5px", height: "5px", borderRadius: "50%", display: "inline-block", marginRight: "5px" }}></i>
                      PDF SOURCE
                    </div>
                    <div className="b">
                      <i />
                      <i />
                      <i />
                    </div>
                  </div>
                  <div className="pv-node" style={{ top: "150px", left: "12px" }}>
                    <div className="h">
                      <i style={{ backgroundColor: "#4ade80", width: "5px", height: "5px", borderRadius: "50%", display: "inline-block", marginRight: "5px" }}></i>
                      SPREADSHEET
                    </div>
                    <div className="b">
                      <i />
                      <i />
                      <i />
                    </div>
                  </div>
                  <div className="pv-node" style={{ top: "88px", left: "208px", width: "132px" }}>
                    <div className="h">
                      <i style={{ backgroundColor: "#22c55e", width: "5px", height: "5px", borderRadius: "50%", display: "inline-block", marginRight: "5px" }}></i>
                      SYNTHESIS
                    </div>
                    <div className="b">
                      <i />
                      <i />
                      <i />
                      <i style={{ width: "50%" }} />
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* STEP 4: Studio */}
            {step === 3 && (
              <div className="tour-slide on">
                <h3>Studio</h3>
                <div className="pv-studio-grid">
                  <div className="pv-studio-card">
                    <div className="ic">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                        <path d="M14 2v6h6M8 13h8M8 17h5" />
                      </svg>
                    </div>
                    <div className="t">Report</div>
                    <div className="s">Deep grounded analysis with citations on every claim</div>
                  </div>
                  <div className="pv-studio-card">
                    <div className="ic">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M4 6h16M4 12h10M4 18h7" />
                      </svg>
                    </div>
                    <div className="t">Executive Summary</div>
                    <div className="s">The essentials in under 600 words, fully cited</div>
                  </div>
                  <div className="pv-studio-card" style={{ opacity: ".55" }}>
                    <div className="ic">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="12" cy="12" r="3" />
                        <path d="M12 2v4M12 18v4M2 12h4M18 12h4" />
                      </svg>
                    </div>
                    <div className="t">Mind Map</div>
                    <div className="s">Coming soon</div>
                  </div>
                  <div className="pv-studio-card" style={{ opacity: ".55" }}>
                    <div className="ic">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z" />
                        <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                      </svg>
                    </div>
                    <div className="t">Audio Overview</div>
                    <div className="s">Coming soon</div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* FINAL: centered */}
        {isFinalStep && (
          <div className="tour-final">
            <div className="big-ic">
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <path d="M22 4L12 14.01l-3-3" />
              </svg>
            </div>
            <h2>You&apos;re ready to research</h2>
            <p>
              Add your first source, ask anything, and generate outputs when the source is ready. Every answer stays grounded
              in your material, with citations you can verify.
            </p>
            <div
              className={`tour-optin ${optIn ? "checked" : ""}`}
              onClick={() => setOptIn(!optIn)}
            >
              <span className="cb">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 6L9 17l-5-5" />
                </svg>
              </span>
              Yes, send me occasional product updates and research tips. No spam, ever.
            </div>
            <div className="tour-final-cta">
              <button className="tour-skip" onClick={finish}>
                Maybe later
              </button>
              <button className="tour-next" onClick={finish}>
                Start exploring
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 12h14M12 5l7 7-7 7" />
                </svg>
              </button>
            </div>
          </div>
        )}

        {/* Bottom dots */}
        <div className="tour-dots" id="tourDots">
          {TOUR_STEPS.map((_, i) => (
            <span
              key={i}
              className={`tour-dot ${i === step ? "on" : ""}`}
              onClick={() => setStep(i)}
              style={{ cursor: "pointer" }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
