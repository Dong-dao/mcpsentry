export interface ScoreDimension {
  key: string;
  label: string;
  score: number;
  diagnosis: string;
}

export interface ScoreResult {
  total: number;
  tier: string;
  dimensions: ScoreDimension[];
  summary: string;
}

interface ToolEntry {
  name: string;
  description: string;
}

const HIGH_PRIVILEGE = /admin|root|sudo|exec|shell|eval|spawn|process|delete|drop|system|full_access|all_scope|高权限|完全访问|所有权限/i;
const UNTRUSTED_SOURCE = /fetch|web|http|url|email|mail|read|file|search|query|input|scan|外部|网页|邮件|文档|搜索|读取/i;
const OUTBOUND_SINK = /send|post|upload|email|mail|write|exec|submit|publish|delete|外发|发送|写入|上传|提交/i;
const DEFENSE_HINT = /proxy|taint|defense|allowlist|whitelist|sandbox|readonly|read_only|dry_run|confirm|approval|limit|代理|污点|白名单|沙箱|只读|确认|审批|限制/i;

const clamp = (n: number) => Math.max(0, Math.min(100, Math.round(n)));

function collect(parsed: unknown, out: ToolEntry[]): void {
  if (!parsed || typeof parsed !== "object") return;
  if (Array.isArray(parsed)) {
    parsed.forEach((item) => collect(item, out));
    return;
  }
  const obj = parsed as Record<string, unknown>;
  if (typeof obj.name === "string" && obj.name.trim()) {
    const detail = [obj.description, obj.command, obj.url, obj.args]
      .filter(Boolean)
      .map((v) => (typeof v === "string" ? v : JSON.stringify(v)))
      .join(" ");
    out.push({ name: obj.name.trim(), description: detail });
  }
  ["tools", "mcpServers", "servers"].forEach((key) => {
    const value = obj[key];
    if (!value) return;
    if (Array.isArray(value)) {
      value.forEach((item) => collect(item, out));
      return;
    }
    if (typeof value === "object") {
      Object.entries(value as Record<string, unknown>).forEach(([name, detail]) => {
        out.push({
          name,
          description:
            typeof detail === "string" ? detail : detail ? JSON.stringify(detail).slice(0, 300) : "",
        });
      });
    }
  });
}

function extractTools(text: string): ToolEntry[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  try {
    const parsed: unknown = JSON.parse(trimmed);
    const found: ToolEntry[] = [];
    collect(parsed, found);
    if (found.length) return found;
  } catch {
    // 非 JSON 时按逐行工具清单处理
  }
  return trimmed
    .split(/\r?\n/)
    .map((line) => line.replace(/^[\s\-*"'·,，]+/, "").trim())
    .filter(Boolean)
    .map((line) => {
      const [name, ...rest] = line.split(/[：:\s]+/);
      return { name, description: rest.join(" ") };
    });
}

export function tierFor(score: number): string {
  if (score >= 90) return "较稳";
  if (score >= 70) return "基本可用";
  if (score >= 40) return "需要修补";
  return "风险较高";
}

/** 纯客户端规则：只统计配置里声明的工具名与描述，不做任何动态验证。 */
export function analyzeConfig(text: string): ScoreResult {
  const tools = extractTools(text);
  const describe = (re: RegExp) => tools.filter((t) => re.test(`${t.name} ${t.description}`)).length;
  const privileged = describe(HIGH_PRIVILEGE);
  const sources = describe(UNTRUSTED_SOURCE);
  const sinks = describe(OUTBOUND_SINK);
  const defenses = describe(DEFENSE_HINT);

  const permissions = tools.length === 0 ? 55 : clamp(100 - privileged * 22);
  const taint = tools.length === 0 ? 55 : clamp(100 - sources * 14);
  const sink = tools.length === 0 ? 50 : clamp(100 - sinks * 16 - (defenses === 0 && sinks > 0 ? 10 : 0));
  const defense = tools.length === 0 ? 40 : clamp(35 + defenses * 18);
  const total = Math.round((permissions + taint + sink + defense) / 4);

  const dimensions: ScoreDimension[] = [
    {
      key: "permissions",
      label: "权限面",
      score: permissions,
      diagnosis:
        privileged === 0
          ? "结论：未发现明显的高权限或执行类工具声明。"
          : "风险点：存在高权限或执行类工具，建议收紧到完成工作所需的最小权限。",
    },
    {
      key: "taint",
      label: "污点面",
      score: taint,
      diagnosis:
        sources <= 1
          ? "结论：外部内容入口较少，建议逐个标注来源。"
          : "风险点：存在多个外部内容入口，建议逐项标注并在工具边界打标记。",
    },
    {
      key: "sink",
      label: "sink 暴露",
      score: sink,
      diagnosis:
        sinks <= 1
          ? "结论：外发出口收敛，建议继续保持出口最小化。"
          : "风险点：外发出口较多，建议逐个确认必要性并收敛出口数量。",
    },
    {
      key: "defense",
      label: "防御配置",
      score: defense,
      diagnosis:
        defenses > 0
          ? "结论：配置中出现代理或约束线索，建议核对其是否真正生效。"
          : "风险点：未见明确的代理、白名单或只读约束配置，建议补充。",
    },
  ];

  return {
    total,
    tier: tierFor(total),
    dimensions,
    summary:
      total >= 70
        ? "结论：配置具备基本约束，可按维度建议逐项加固。"
        : "风险点：配置仍有明显可收敛面，建议按低分维度依次修补。",
  };
}
