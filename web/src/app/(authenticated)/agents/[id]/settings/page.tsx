"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { Agent } from "@/types";

interface ACLEntry { id: string; agent_id: string; user_id: string | null; team_id: string | null; role: string; created_at: string; }

export default function AgentSettingsPage() {
  const { user } = useAuth();
  const params = useParams();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [aclEntries, setAclEntries] = useState<ACLEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [newUserId, setNewUserId] = useState("");
  const [newRole, setNewRole] = useState("user");

  useEffect(() => {
    if (!user) return;
    Promise.all([
      apiFetch<Agent>(`/agents/${params.id}`),
      apiFetch<{ items: ACLEntry[] }>(`/agents/${params.id}/acl`),
    ]).then(([a, acl]) => { setAgent(a); setAclEntries(acl.items); }).catch(() => {}).finally(() => setLoading(false));
  }, [user, params.id]);

  if (loading || !agent) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex items-center gap-3 text-muted-foreground">
          <svg className="h-5 w-5 animate-spin" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
          <span className="text-sm">Loading...</span>
        </div>
      </div>
    );
  }

  const handleAddACL = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUserId.trim()) return;
    const entry = await apiFetch<ACLEntry>(`/agents/${agent.id}/acl`, { method: "POST", body: JSON.stringify({ user_id: newUserId, role: newRole }) });
    setAclEntries((prev) => [...prev, entry]);
    setNewUserId("");
  };

  const handleDeleteACL = async (aclId: string) => {
    await apiFetch(`/agents/${agent.id}/acl/${aclId}`, { method: "DELETE" });
    setAclEntries((prev) => prev.filter((a) => a.id !== aclId));
  };

  const roleColors: Record<string, string> = { owner: "bg-primary/10 text-primary", admin: "bg-warning/10 text-warning", user: "bg-success/10 text-success", viewer: "bg-secondary text-muted-foreground" };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-8 py-8">
        <Link href={`/agents/${agent.id}`} className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5"/><polyline points="12 19 5 12 12 5"/></svg>
          {agent.name}
        </Link>
        <h1 className="mt-4 mb-2 text-xl font-bold text-foreground">Settings</h1>
        <p className="mb-8 text-sm text-muted-foreground">Manage access control for {agent.name}</p>

        <div className="space-y-6">
          <Card>
            <CardHeader><CardTitle>Access Control</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              {aclEntries.length > 0 ? (
                <div className="space-y-2">
                  {aclEntries.map((entry) => (
                    <div key={entry.id} className="flex items-center justify-between rounded-lg border border-border/40 bg-secondary/30 p-3">
                      <div className="flex items-center gap-3 text-sm">
                        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary text-xs text-muted-foreground">{entry.user_id ? "U" : "T"}</div>
                        <div>
                          <span className="font-medium text-foreground/90">{entry.user_id || entry.team_id}</span>
                          <p className="text-xs text-muted-foreground">{entry.user_id ? "User" : "Team"}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium capitalize ${roleColors[entry.role] || roleColors.viewer}`}>{entry.role}</span>
                        <Button variant="ghost" size="sm" onClick={() => handleDeleteACL(entry.id)} className="text-muted-foreground hover:text-destructive">
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (<p className="text-sm text-muted-foreground">No access entries. Add users or teams below.</p>)}
              <form onSubmit={handleAddACL} className="flex items-end gap-3 border-t border-border/40 pt-4">
                <div className="flex-1 space-y-2"><Label htmlFor="user_id">User ID</Label><Input id="user_id" value={newUserId} onChange={(e) => setNewUserId(e.target.value)} placeholder="Paste user UUID" /></div>
                <div className="w-32 space-y-2"><Label htmlFor="role">Role</Label><Select id="role" value={newRole} onChange={(e) => setNewRole(e.target.value)}><option value="viewer">Viewer</option><option value="user">User</option><option value="admin">Admin</option><option value="owner">Owner</option></Select></div>
                <Button type="submit">Add</Button>
              </form>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Credentials</CardTitle></CardHeader>
            <CardContent>
              <div className="flex items-center gap-3 rounded-lg bg-secondary/30 p-4">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-muted-foreground"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
                <p className="text-sm text-muted-foreground">Credential management will be available in a future release.</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
