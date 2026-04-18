"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";

/**
 * Thin progress bar at the top of the viewport during route transitions.
 * Detects navigation by watching pathname changes — starts on click of any
 * internal link, completes when pathname actually changes.
 */
export function NavigationProgress() {
  const pathname = usePathname();
  const [progress, setProgress] = useState(0);
  const [visible, setVisible] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval>>(undefined);
  const prevPathRef = useRef(pathname);

  // Start progress on any click that triggers navigation
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      const anchor = (e.target as HTMLElement).closest("a");
      if (!anchor) return;
      const href = anchor.getAttribute("href");
      if (!href || href.startsWith("http") || href.startsWith("#")) return;
      // Normalise away query + hash before comparing — a same-page
      // "?runId=X" swap doesn't change pathname, so the completion
      // effect below would never fire and the bar would hang at 90%.
      const hrefPath = href.split("?")[0].split("#")[0];
      if (hrefPath === pathname) return;

      setVisible(true);
      setProgress(20);

      clearInterval(timerRef.current);
      timerRef.current = setInterval(() => {
        setProgress((p) => {
          if (p >= 90) {
            clearInterval(timerRef.current);
            return 90;
          }
          return p + (90 - p) * 0.1;
        });
      }, 100);
    };

    document.addEventListener("click", handler, true);
    return () => document.removeEventListener("click", handler, true);
  }, [pathname]);

  // Complete on pathname change
  useEffect(() => {
    if (pathname !== prevPathRef.current) {
      prevPathRef.current = pathname;
      if (visible) {
        clearInterval(timerRef.current);
        setProgress(100);
        setTimeout(() => {
          setVisible(false);
          setProgress(0);
        }, 200);
      }
    }
  }, [pathname, visible]);

  if (!visible) return null;

  return (
    <div className="fixed top-0 left-0 right-0 z-[9999] h-[2px]">
      <div
        className="h-full bg-brand transition-all duration-200 ease-out"
        style={{ width: `${progress}%` }}
      />
    </div>
  );
}
