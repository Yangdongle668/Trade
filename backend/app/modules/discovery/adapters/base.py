"""数据源适配器契约（03 文档 §5 / 架构 §5.2）。

新增数据源 = 实现本接口并在 registry 注册，核心流水线不改。
适配器必须：无 Key 时返回 available=False 自动停用；自行遵守限速。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class CompanyCandidate:
    domain: str                 # 已归一化注册域
    name: str = ""
    country: str = ""
    city: str = ""
    website: str = ""
    source: str = ""
    meta: dict = field(default_factory=dict)  # 源侧原始信号（评论数/SIC 码/地址…）


class DataSourceAdapter(ABC):
    name: str = "base"

    @abstractmethod
    def available(self) -> bool:
        """Key 未配置或配额耗尽 → False，流水线自动跳过本源。"""

    @abstractmethod
    def discover(self, icp: dict, limit: int = 50) -> list[CompanyCandidate]:
        """按 ICP 检索候选公司。icp 结构见 campaign.models.Campaign.icp 注释。"""
