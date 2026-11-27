export default function ScoreEntryCard({
  text,
  fileName,
  busy,
  onTextChange,
  onFile,
  onAnalyze,
}: {
  text: string;
  fileName: string;
  busy: boolean;
  onTextChange: (value: string) => void;
  onFile: (file: File) => void;
  onAnalyze: () => void;
}) {
  return (
    <section className="panel">
      <h2 className="text-xl font-semibold text-slate-100">粘贴配置或工具清单</h2>
      <p className="mt-1 text-sm leading-6 text-slate-400">
        支持 MCP 配置 JSON，也支持每行一个工具名。内容只在浏览器里计算，不上传。
      </p>
      <textarea
        className="field mono mt-4 h-52 w-full resize-y leading-6"
        value={text}
        onChange={(e) => onTextChange(e.target.value)}
        placeholder={'例如：{"mcpServers": {"files": {"command": "python"}}} 或每行一个工具名'}
        spellCheck={false}
        aria-label="MCP 配置或工具清单"
      />
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <label className="text-[13px] text-slate-400">
          可选上传
          <input
            type="file"
            accept=".json,.txt,.md"
            className="ml-2 block text-[13px] text-slate-400 file:mr-3 file:min-h-9 file:rounded-md file:border file:border-line file:bg-ink file:px-3 file:text-[13px] file:text-slate-200"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onFile(file);
            }}
          />
        </label>
        {fileName && <span className="mono text-slate-500">{fileName}</span>}
      </div>
      <button
        className="btn btn-primary mt-5 min-h-[48px] w-full justify-center sm:w-auto"
        type="button"
        onClick={onAnalyze}
        disabled={!text.trim() || busy}
        aria-busy={busy}
      >
        开始体检
      </button>
    </section>
  );
}
