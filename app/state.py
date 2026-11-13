from dataclasses import dataclass, field


@dataclass
class BIState:
    question: str
    lang: str = "fr"
    plan: list = field(default_factory=list)
    datasets: dict = field(default_factory=dict)    # nom -> {"columns","rows","sql"}
    forecasts: dict = field(default_factory=dict)   # nom -> {"labels","history","forecast",...}
    findings: list = field(default_factory=list)    # [{"agent","text"}]
    answer: str = ""
