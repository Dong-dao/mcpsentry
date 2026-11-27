import { useState } from "react";
import DisclaimerBar from "../components/score/DisclaimerBar";
import ScoreEntryCard from "../components/score/ScoreEntryCard";
import ShareableScoreCard from "../components/score/ShareableScoreCard";
import { analyzeConfig, type ScoreResult } from "../components/score/rules";
import { Notice } from "../components/ui";

function diagnosisText(result: ScoreResult): string {
  return [
    "MCP 配置安全体检",
    `总分 ${result.total}/100 · ${result.tier}`,
    result.summary,
    ...result.dimensions.map((d) => `${d.label} ${d.score}/100：${d.diagnosis}`),
    "本地规则计算，不代表动态攻击验证结果",
  ].join("\n");
}

export default function Health() {
  const [text, setText] = useState("");
  const [fileName, setFileName] = useState("");
  const [result, setResult] = useState<ScoreResult | null>(null);
  const [error, setError] = useState("");
  const [copyStatus, setCopyStatus] = useState("");

  function analyze() {
    setError("");
    setCopyStatus("");
    if (!text.trim()) {
      setError("请先粘贴配置或工具清单。");
      return;
    }
    try {
      setResult(analyzeConfig(text));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function onFile(file: File) {
    setFileName(file.name);
    setError("");
    try {
      setText(await file.text());
    } catch {
      setError("文件读取失败，请改用粘贴方式。");
    }
  }

  async function copyDiagnosis() {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(diagnosisText(result));
      setCopyStatus("已复制诊断");
    } catch {
      setCopyStatus("复制失败，请手动选择文本");
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-[30px] font-semibold leading-tight text-slate-50 sm:text-[36px]">
          安全体检
        </h1>
        <p className="mt-2 max-w-3xl text-base leading-7 text-slate-300">
          粘贴自己的 MCP 配置或工具清单，从权限面、污点面、sink 暴露、防御配置四个维度给出本地诊断。
        </p>
      </header>

      <ScoreEntryCard
        text={text}
        fileName={fileName}
        busy={false}
        onTextChange={(value) => {
          setText(value);
          setCopyStatus("");
        }}
        onFile={(file) => void onFile(file)}
        onAnalyze={analyze}
      />

      {error && <Notice tone="bad" title="体检未完成" message={error} />}
      {copyStatus && <Notice tone="info" title="操作完成" message={copyStatus} />}

      {result && (
        <>
          <ShareableScoreCard result={result} configLabel={fileName || "粘贴的配置"} />
          <div className="flex flex-wrap items-center gap-3">
            <button className="btn" type="button" onClick={() => void copyDiagnosis()}>
              复制诊断
            </button>
            <button
              className="btn"
              type="button"
              disabled
              title="请用系统截图保存"
            >
              保存为图片
            </button>
          </div>
          <DisclaimerBar />
        </>
      )}
    </div>
  );
}
