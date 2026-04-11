import { LoadingState } from "./loading-state";

/**
 * PageLoader — full-screen loading shell used for initial page mounts
 * (auth check, session fetch, etc).
 */
function PageLoader({ label }: { label?: string }) {
  return (
    <div className="flex h-screen items-center justify-center">
      <LoadingState label={label} />
    </div>
  );
}

export { PageLoader };
