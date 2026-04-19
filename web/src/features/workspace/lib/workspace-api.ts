import { http } from "@/lib/http/client";

export interface TreeEntry {
  name: string;
  type: "file" | "dir";
  size?: number;
  mtime?: number;
  hidden?: boolean;
}

export interface TreeListing {
  path: string;
  entries: TreeEntry[];
}

export interface FileContents {
  path: string;
  content: string;
  encoding: "utf8" | "base64";
  size: number;
  mtime: number;
  isBinary: boolean;
  truncated: boolean;
}

export async function getTree(
  sessionId: string,
  rel: string,
  includeHidden: boolean,
): Promise<TreeListing> {
  const params = new URLSearchParams({
    path: rel,
    include_hidden: includeHidden ? "true" : "false",
  });
  return http.get<TreeListing>(
    `/sessions/${sessionId}/workspace/tree?${params.toString()}`,
  );
}

export async function getFile(sessionId: string, rel: string): Promise<FileContents> {
  const params = new URLSearchParams({ path: rel });
  return http.get<FileContents>(
    `/sessions/${sessionId}/workspace/file?${params.toString()}`,
  );
}
