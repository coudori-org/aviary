"use client";

import * as React from "react";

interface PageHeaderContextValue {
  crumb: React.ReactNode | null;
  setCrumb: (node: React.ReactNode | null) => void;
}

const PageHeaderContext = React.createContext<PageHeaderContextValue | null>(null);

/**
 * Provides a slot the active page can fill with a compact breadcrumb /
 * page identity. Lives in AppShell so the Header reads it without prop
 * drilling and pages can stay pure.
 */
export function PageHeaderProvider({ children }: { children: React.ReactNode }) {
  const [crumb, setCrumb] = React.useState<React.ReactNode | null>(null);
  const value = React.useMemo(() => ({ crumb, setCrumb }), [crumb]);
  return <PageHeaderContext.Provider value={value}>{children}</PageHeaderContext.Provider>;
}

export function usePageHeader(): PageHeaderContextValue {
  const ctx = React.useContext(PageHeaderContext);
  if (!ctx) throw new Error("usePageHeader must be used within PageHeaderProvider");
  return ctx;
}

/**
 * Page-side hook: declaratively own the AppShell breadcrumb. Cleared on
 * unmount only — intermediate node changes simply replace the slot,
 * avoiding a flash-of-null between dependency transitions.
 */
export function usePageCrumb(node: React.ReactNode | null) {
  const { setCrumb } = usePageHeader();
  React.useEffect(() => {
    setCrumb(node);
  }, [node, setCrumb]);
  React.useEffect(() => {
    return () => setCrumb(null);
  }, [setCrumb]);
}
