"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, X, Lock } from "@/components/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { LoadingState } from "@/components/feedback/loading-state";
import { agentsApi, aclApi, type ACLEntry } from "@/features/agents/api/agents-api";
import { useAuth } from "@/features/auth/providers/auth-provider";
import { routes } from "@/lib/constants/routes";
import type { Agent } from "@/types";

const ROLE_VARIANTS: Record<string, "info" | "warning" | "success" | "muted"> = {
  owner: "info",
  admin: "warning",
  user: "success",
  viewer: "muted",
};

export default function AgentSettingsPage() {
  const { user } = useAuth();
  const params = useParams<{ id: string }>();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [aclEntries, setAclEntries] = useState<ACLEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [newUserId, setNewUserId] = useState("");
  const [newRole, setNewRole] = useState("user");

  useEffect(() => {
    if (!user) return;
    Promise.all([agentsApi.get(params.id), aclApi.list(params.id)])
      .then(([a, acl]) => {
        setAgent(a);
        setAclEntries(acl.items);
      })
      .finally(() => setLoading(false));
  }, [user, params.id]);

  if (loading || !agent) {
    return <LoadingState fullHeight label="Loading…" />;
  }

  const handleAddACL = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUserId.trim()) return;
    const entry = await aclApi.add(agent.id, { user_id: newUserId, role: newRole });
    setAclEntries((prev) => [...prev, entry]);
    setNewUserId("");
  };

  const handleDeleteACL = async (aclId: string) => {
    await aclApi.remove(agent.id, aclId);
    setAclEntries((prev) => prev.filter((a) => a.id !== aclId));
  };

  return (
    <div className="h-full overflow-y-auto bg-canvas">
      <div className="mx-auto max-w-container-sm px-8 py-8">
        <Link
          href={routes.agent(agent.id)}
          className="inline-flex items-center gap-1.5 type-caption text-fg-muted hover:text-fg-primary transition-colors"
        >
          <ArrowLeft size={12} strokeWidth={2} />
          {agent.name}
        </Link>
        <h1 className="mt-4 type-heading text-fg-primary">Settings</h1>
        <p className="mt-1 mb-8 type-caption text-fg-muted">
          Manage access control for {agent.name}
        </p>

        <div className="space-y-6">
          <Card variant="elevated">
            <CardHeader>
              <CardTitle>Access Control</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {aclEntries.length > 0 ? (
                <div className="space-y-2">
                  {aclEntries.map((entry) => (
                    <div
                      key={entry.id}
                      className="flex items-center justify-between rounded-md bg-canvas px-3 py-2.5"
                    >
                      <div className="flex items-center gap-3 type-body-tight">
                        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-raised type-caption text-fg-muted">
                          {entry.user_id ? "U" : "T"}
                        </div>
                        <div>
                          <span className="text-fg-secondary">
                            {entry.user_id || entry.team_id}
                          </span>
                          <p className="type-caption text-fg-muted">
                            {entry.user_id ? "User" : "Team"}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant={ROLE_VARIANTS[entry.role] || "muted"}>
                          {entry.role}
                        </Badge>
                        <button
                          type="button"
                          onClick={() => handleDeleteACL(entry.id)}
                          className="flex h-6 w-6 items-center justify-center rounded-xs text-fg-muted hover:text-danger transition-colors"
                          aria-label="Remove access entry"
                        >
                          <X size={12} strokeWidth={2} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="type-caption text-fg-muted">
                  No access entries. Add users or teams below.
                </p>
              )}

              <form
                onSubmit={handleAddACL}
                className="flex items-end gap-3 border-t border-white/[0.06] pt-4"
              >
                <div className="flex-1 space-y-2">
                  <Label htmlFor="user_id">User ID</Label>
                  <Input
                    id="user_id"
                    value={newUserId}
                    onChange={(e) => setNewUserId(e.target.value)}
                    placeholder="Paste user UUID"
                  />
                </div>
                <div className="w-32 space-y-2">
                  <Label htmlFor="role">Role</Label>
                  <Select
                    id="role"
                    value={newRole}
                    onChange={(e) => setNewRole(e.target.value)}
                  >
                    <option value="viewer">Viewer</option>
                    <option value="user">User</option>
                    <option value="admin">Admin</option>
                    <option value="owner">Owner</option>
                  </Select>
                </div>
                <Button type="submit">Add</Button>
              </form>
            </CardContent>
          </Card>

          <Card variant="elevated">
            <CardHeader>
              <CardTitle>Credentials</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-3 rounded-md bg-canvas px-4 py-3">
                <Lock size={14} strokeWidth={1.75} className="text-fg-muted" />
                <p className="type-caption text-fg-muted">
                  Credential management will be available in a future release.
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
