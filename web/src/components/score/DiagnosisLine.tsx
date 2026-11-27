export default function DiagnosisLine({ text }: { text: string }) {
  const isRisk = text.startsWith("风险点：");
  return (
    <p className={`mt-1 text-[13px] leading-5 ${isRisk ? "text-warn" : "text-slate-400"}`}>
      {text}
    </p>
  );
}
