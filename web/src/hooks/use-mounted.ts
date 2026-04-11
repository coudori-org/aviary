"use client";

import { useEffect, useRef } from "react";

/** Returns a stable function that reports whether the component is still mounted. */
export function useMounted(): () => boolean {
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  return () => mountedRef.current;
}
