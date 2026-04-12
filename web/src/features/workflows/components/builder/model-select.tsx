"use client";

import { useEffect, useState } from "react";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { modelsApi, type ModelOption } from "@/features/agents/api/agents-api";

interface ModelSelectProps {
  backend: string;
  model: string;
  onChange: (backend: string, model: string) => void;
}

export function ModelSelect({ backend, model, onChange }: ModelSelectProps) {
  const [allModels, setAllModels] = useState<ModelOption[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    modelsApi
      .list()
      .then((res) => { if (!cancelled) setAllModels(res.models); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const backends = Array.from(new Set(allModels.map((m) => m.backend)));
  const models = allModels.filter((m) => m.backend === (backend || backends[0]));

  // Auto-select first backend if none set
  useEffect(() => {
    if (backends.length > 0 && !backend) {
      const defaultBackend = backends[0];
      const defaultModels = allModels.filter((m) => m.backend === defaultBackend);
      const defaultModel = defaultModels.find((m) => m.model_info?._ui?.default_model) ?? defaultModels[0];
      if (defaultModel) onChange(defaultBackend, defaultModel.id);
    }
  }, [backends, backend, allModels, onChange]);

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor="node-backend" className="text-[11px] font-medium text-fg-disabled uppercase tracking-wider">
          Backend
        </Label>
        <Select
          id="node-backend"
          value={backend}
          onChange={(e) => {
            const newBackend = e.target.value;
            const newModels = allModels.filter((m) => m.backend === newBackend);
            const defaultModel = newModels.find((m) => m.model_info?._ui?.default_model) ?? newModels[0];
            onChange(newBackend, defaultModel?.id ?? "");
          }}
          disabled={loading}
          className="text-[13px]"
        >
          {loading && <option>Loading…</option>}
          {backends.map((b) => (
            <option key={b} value={b}>{b}</option>
          ))}
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="node-model" className="text-[11px] font-medium text-fg-disabled uppercase tracking-wider">
          Model
        </Label>
        <Select
          id="node-model"
          value={model}
          onChange={(e) => onChange(backend, e.target.value)}
          disabled={loading}
          className="text-[13px]"
        >
          {models.map((m) => (
            <option key={m.id} value={m.id}>{m.name}</option>
          ))}
        </Select>
      </div>
    </div>
  );
}
