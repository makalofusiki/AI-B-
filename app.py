from __future__ import annotations

try:
    import tkinter as tk
    from tkinter import ttk
except ModuleNotFoundError:  # pragma: no cover
    tk = None
    ttk = None


def generate_reply(question: str) -> str:
    text = question.strip().lower()
    if not text:
        return "请先输入您的问题，例如：你们有什么经典中成药？"

    knowledge = {
        "公司": "我们是一家专注中药研发、生产与服务的企业，提供中药饮片与中成药方案。",
        "产品": "常见产品方向包括感冒调理、脾胃调理、睡眠调理与慢病辅助管理相关中药产品。",
        "质量": "我们执行原料溯源、批次检测和出厂复检，确保中药产品质量稳定可追踪。",
        "合作": "可提供医院、连锁药房与企业健康管理合作方案，欢迎留下您的需求场景。",
        "联系方式": "您可联系商务邮箱：biz@tcm-ai-assistant.local（示例地址）。",
    }

    for keyword, answer in knowledge.items():
        if keyword in text:
            return answer

    return "已收到您的问题。当前为演示版助手，可先咨询：公司介绍、产品方向、质量管理、合作方式、联系方式。"


class TcmAssistantApp(tk.Tk if tk else object):
    def __init__(self) -> None:
        if not tk or not ttk:
            raise RuntimeError("当前 Python 环境未安装 tkinter，无法启动桌面界面。")
        super().__init__()
        self.title("中药公司 AI 询问助手")
        self.geometry("720x480")
        self.minsize(560, 380)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        title = ttk.Label(self, text="中药公司 AI 询问助手", font=("Arial", 16, "bold"))
        title.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="w")

        self.chat = tk.Text(self, wrap="word", state="disabled")
        self.chat.grid(row=1, column=0, padx=16, pady=8, sticky="nsew")

        input_frame = ttk.Frame(self)
        input_frame.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="ew")
        input_frame.columnconfigure(0, weight=1)

        self.question_var = tk.StringVar()
        self.entry = ttk.Entry(input_frame, textvariable=self.question_var)
        self.entry.grid(row=0, column=0, sticky="ew")
        self.entry.bind("<Return>", self.on_ask)

        ask_button = ttk.Button(input_frame, text="提问", command=self.on_ask)
        ask_button.grid(row=0, column=1, padx=(8, 0))

        self.append_chat("助手", "您好！我是中药公司 AI 询问助手。您可以向我咨询公司、产品、质量、合作等问题。")
        self.entry.focus()

    def append_chat(self, role: str, message: str) -> None:
        self.chat.configure(state="normal")
        self.chat.insert("end", f"{role}：{message}\n\n")
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def on_ask(self, _event: object | None = None) -> None:
        question = self.question_var.get().strip()
        if not question:
            return

        self.append_chat("我", question)
        self.question_var.set("")

        reply = generate_reply(question)
        self.append_chat("助手", reply)


if __name__ == "__main__":
    app = TcmAssistantApp()
    app.mainloop()
