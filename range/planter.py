"""注入载体投放：实现 engine.attacks.engine.Planter 协议。

载体落点（靶场工作区约定见 range/workspace.py）：
- carrier=doc（A2/A4）：`docs/external.txt` = 私有文档（含金丝雀）+ 注入正文；
  同时镜像写 `web/external.txt`——T1/T5 经 read_doc 读到它，T2 经 web_fetch 读到它，
  攻击语义一致而污点源工具不同（RunConfig.carrier 保持 doc，因为引擎的
  间接注入触发语只对 carrier=doc 生成，改成 web 会退化成直接注入）。
- carrier=desc（A3）：写 `desc.txt` 作为 weather 工具描述全文；
  T4 首轮写良性描述建立 rug-pull 基线，第 2 轮起换成投毒描述。

与 A 的 tests/fixtures 约定（docs/doc.txt）相比，这里把注入写进 external.txt，
和引擎 _act_message 里硬编码的文件名对齐；私有文档仍留在 doc.txt。
"""

from __future__ import annotations

from pathlib import Path

from engine.attacks.engine import Planter
from engine.contracts import AttackClass, RunConfig

from . import workspace as ws
from .backend import BENIGN_WEATHER_DESC
from .victim import EMAIL_RE


class CarrierPlanter(Planter):
    def __init__(self, config: RunConfig, workdir: Path):
        self.config = config
        self.ws = ws.Workspace(Path(workdir))

    def plant(self, payload, round_no: int) -> None:
        cls = self.config.attack.class_
        if cls is AttackClass.A3_DESCRIPTION_POISONING:
            self._plant_desc(payload.text, round_no)
            return
        if self.config.attack.carrier == "doc":
            self._plant_doc(payload.text)

    def _plant_desc(self, text: str, round_no: int) -> None:
        # T4 第 1 轮必须先建立良性基线，否则 rug-pull 无漂移可比对
        if self.config.target.id == "T4" and round_no == 1:
            text = BENIGN_WEATHER_DESC
        self.ws.desc.write_text(text, encoding="utf-8")

    def _plant_doc(self, injection: str) -> None:
        private = ws.private_doc_text(self.config.oracle.canary)
        carrier = f"{private}\n\n{injection}\n"
        self.ws.docs.mkdir(parents=True, exist_ok=True)
        self.ws.web.mkdir(parents=True, exist_ok=True)
        self.ws.carrier_doc.write_text(carrier, encoding="utf-8")
        self.ws.carrier_web.write_text(carrier, encoding="utf-8")

    def reset(self) -> None:
        """轮次之间清掉证据文件由 runner 负责，这里只保证载体可重复写。"""
        for path in (self.ws.carrier_doc, self.ws.carrier_web, self.ws.desc):
            path.unlink(missing_ok=True)


def attacker_recipient(payload_text: str) -> str | None:
    """从注入文本里取攻击者收件人，供 runner 写进 meta 做人工核对。"""
    m = EMAIL_RE.search(payload_text)
    return m.group(0) if m else None
