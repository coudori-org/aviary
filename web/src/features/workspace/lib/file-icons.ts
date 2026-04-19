import type { ComponentType } from "react";
import { File, FileCode, FileImage, FileJson, FileText } from "@/components/icons";

const CODE_EXT = new Set([
  "ts", "tsx", "js", "jsx", "mjs", "cjs",
  "py", "pyi",
  "go", "rs", "c", "cc", "cpp", "h", "hpp",
  "java", "kt", "scala",
  "rb", "php", "swift", "dart",
  "sh", "bash", "zsh", "fish",
  "sql", "ps1",
  "vue", "svelte",
  "css", "scss", "sass", "less",
  "html", "htm", "xml",
  "yaml", "yml", "toml", "ini", "conf",
  "dockerfile",
]);

const IMAGE_EXT = new Set(["png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "bmp"]);

export function fileIconFor(name: string): ComponentType<{ size?: number; strokeWidth?: number; className?: string }> {
  const lower = name.toLowerCase();
  const dot = lower.lastIndexOf(".");
  const ext = dot === -1 ? "" : lower.slice(dot + 1);
  if (ext === "json") return FileJson;
  if (IMAGE_EXT.has(ext)) return FileImage;
  if (CODE_EXT.has(ext)) return FileCode;
  if (ext === "md" || ext === "markdown" || ext === "txt" || ext === "log") return FileText;
  return File;
}

const LANGUAGE_BY_EXT: Record<string, string> = {
  ts: "typescript",
  tsx: "typescript",
  js: "javascript",
  jsx: "javascript",
  mjs: "javascript",
  cjs: "javascript",
  py: "python",
  go: "go",
  rs: "rust",
  java: "java",
  kt: "kotlin",
  rb: "ruby",
  php: "php",
  swift: "swift",
  c: "c",
  cc: "cpp",
  cpp: "cpp",
  h: "cpp",
  hpp: "cpp",
  cs: "csharp",
  sh: "shell",
  bash: "shell",
  zsh: "shell",
  sql: "sql",
  json: "json",
  yaml: "yaml",
  yml: "yaml",
  toml: "ini",
  ini: "ini",
  md: "markdown",
  markdown: "markdown",
  html: "html",
  htm: "html",
  xml: "xml",
  css: "css",
  scss: "scss",
  less: "less",
  vue: "html",
  svelte: "html",
  dockerfile: "dockerfile",
};

export function monacoLanguageFor(name: string): string {
  const lower = name.toLowerCase();
  if (lower === "dockerfile") return "dockerfile";
  const dot = lower.lastIndexOf(".");
  if (dot === -1) return "plaintext";
  return LANGUAGE_BY_EXT[lower.slice(dot + 1)] ?? "plaintext";
}
