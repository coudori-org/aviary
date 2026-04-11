/**
 * ActivityIndicator — three bouncing dots shown while the agent is
 * streaming. Lives outside any block so it stays visible during
 * tool execution gaps.
 */
export function ActivityIndicator() {
  return (
    <div className="flex h-8 items-center gap-1.5 px-4">
      {[0, 150, 300].map((d) => (
        <span
          key={d}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-info"
          style={{ animationDelay: `${d}ms`, animationDuration: "0.6s" }}
        />
      ))}
    </div>
  );
}
