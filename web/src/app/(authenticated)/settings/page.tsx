import { Suspense } from "react";
import { LoadingState } from "@/components/feedback/loading-state";
import { SettingsView } from "@/features/settings/components/settings-view";

export default function SettingsPage() {
  return (
    <Suspense fallback={<LoadingState fullHeight label="Loading settings…" />}>
      <SettingsView />
    </Suspense>
  );
}
