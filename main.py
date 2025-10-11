# 彻底修复'module not callable'错误的AA分账系统插件

# 正确导入filter模块及其子模块
from astrbot.api.event import filter  # 导入filter模块
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from typing import Dict, List, Optional
import json
import os
import time
import uuid
from datetime import datetime


@register(
    "aa分账系统",
    "anchor",
    "简易AA分账系统（支持创建账单、查看账单、对账明细、标记清账）",
    "1.0.4"
)
class AASettlementPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.aa_bills: Dict[str, List[Dict]] = {}  # {用户ID: [账单列表]}
        self.settlement_records: Dict[str, List[Dict]] = {}  # {用户ID: [清账记录]}
        self.bills_path = os.path.join(os.path.dirname(__file__), "aa账单数据.json")
        self.records_path = os.path.join(os.path.dirname(__file__), "aa清账记录.json")
        self._加载历史数据()

    async def initialize(self):
        logger.info("AA分账系统插件初始化完成")

    # 关键修复：使用filter.message.command装饰器（根据框架结构调整）
    @filter.message.command("创建账单")
    async def 创建账单(self, event: AstrMessageEvent):
        消息内容 = event.message_str.strip()
        # 分割参数时使用内置filter函数，避免与框架filter模块冲突
        参数列表 = list(__builtins__.filter(None, 消息内容.split(" ")))[1:]

        if len(参数列表) < 2:
            yield event.plain_result(
                "❌ 格式错误！\n"
                "简单模式：/创建账单 [参与人] [金额]（例：/创建账单 陈 100）\n"
                "完整模式：/创建账单 [参与人1] [参与人2] [金额] [描述]（例：/创建账单 张三 李四 600 聚餐）"
            )
            return

        # 解析金额
        总金额 = None
        金额索引 = -1
        for 索引 in reversed(range(len(参数列表))):
            try:
                总金额 = float(参数列表[索引])
                金额索引 = 索引
                break
            except ValueError:
                continue

        if 总金额 is None or 总金额 <= 0:
            yield event.plain_result("❌ 金额错误！请输入正数（支持小数，如25.5）")
            return

        # 提取信息
        参与人列表 = 参数列表[:金额索引]
        消费描述 = " ".join(参数列表[金额索引+1:]) if (金额索引 + 1 < len(参数列表)) else "日常消费"
        付款人ID = event.get_sender_id()
        付款人名称 = event.get_sender_name() or f"用户{付款人ID[:4]}"

        if 付款人名称 not in 参与人列表:
            参与人列表.append(付款人名称)
        参与人列表 = list(set(参与人列表))
        参与人数 = len(参与人列表)
        每人分摊 = round(总金额 / 参与人数, 2)

        # 生成账单
        账单ID = str(uuid.uuid4())[:6]
        创建时间 = datetime.now().strftime("%Y-%m-%d %H:%M")
        账单信息 = {
            "账单ID": 账单ID,
            "付款人": {"ID": 付款人ID, "名称": 付款人名称},
            "总金额": round(总金额, 2),
            "消费描述": 消费描述,
            "参与人": 参与人列表,
            "每人分摊": 每人分摊,
            "状态": "待清账",
            "创建时间": 创建时间,
            "清账时间": None,
            "清账人": None,
            "债务关系": self._生成债务关系(付款人名称, 参与人列表, 每人分摊)
        }

        self.aa_bills.setdefault(付款人ID, []).append(账单信息)
        self._保存数据()

        # 回复内容
        回复内容 = (
            f"✅ 账单创建成功！\n"
            f"🆔 账单ID：{账单ID}\n"
            f"💸 付款人：{付款人名称}\n"
            f"📝 描述：{消费描述}\n"
            f"💰 总金额：{账单信息['总金额']}元 | 参与人：{', '.join(参与人列表)}\n"
            f"🧮 每人分摊：{每人分摊}元\n"
        )
        yield event.plain_result(回复内容)

    @filter.message.command("查看账单")
    async def 查看账单(self, event: AstrMessageEvent):
        用户ID = event.get_sender_id()
        用户账单列表 = self.aa_bills.get(用户ID, [])

        if not 用户账单列表:
            yield event.plain_result("📋 暂无账单\n💡 快速创建：/创建账单 [参与人] [金额]（例：/创建账单 陈 100）")
            return

        # 精简列表显示
        待清账数量 = len([b for b in 用户账单列表 if b["状态"] == "待清账"])
        已清账数量 = len(用户账单列表) - 待清账数量
        回复内容 = f"📊 我的AA账单（待清账：{待清账数量} | 已清账：{已清账数量}）\n" + "-"*40 + "\n"

        # 显示最近5条
        最近账单 = sorted(用户账单列表, key=lambda x: x["创建时间"], reverse=True)[:5]
        for 序号, 账单 in enumerate(最近账单, 1):
            状态标签 = "🔴 待清账" if 账单["状态"] == "待清账" else "🟢 已清账"
            回复内容 += (
                f"{序号}. ID：{账单['账单ID']} | {状态标签}\n"
                f"   描述：{账单['消费描述']} | 金额：{账单['总金额']}元\n"
                f"   时间：{账单['创建时间']}\n"
                "-"*40 + "\n"
            )
        yield event.plain_result(回复内容)

    @filter.message.command("对账明细")
    async def 对账明细(self, event: AstrMessageEvent):
        消息内容 = event.message_str.strip()
        参数列表 = list(__builtins__.filter(None, 消息内容.split(" ")))[1:]

        if not 参数列表:
            yield event.plain_result("❌ 缺少账单ID！\n用法：/对账明细 [账单ID]（例：/对账明细 abc123）")
            return

        目标账单ID = 参数列表[0]
        用户ID = event.get_sender_id()
        目标账单 = None
        for 账单 in self.aa_bills.get(用户ID, []):
            if 账单["账单ID"] == 目标账单ID:
                目标账单 = 账单
                break

        if not 目标账单:
            yield event.plain_result(f"❌ 未找到账单ID「{目标账单ID}」\n💡 用 /查看账单 确认ID")
            return

        # 债务明细
        回复内容 = (
            f"📊 账单「{目标账单ID}」明细\n"
            f"📝 描述：{目标账单['消费描述']} | 金额：{目标账单['总金额']}元\n"
            f"💸 付款人：{目标账单['付款人']['名称']}\n"
            "\n【债务关系】\n"
        )
        for 债务 in 目标账单["债务关系"]:
            回复内容 += f"👉 {债务['债务人']} → {债务['债权人']}：{债务['金额']}元\n"

        yield event.plain_result(回复内容)

    @filter.message.command("标记清账")
    async def 标记清账(self, event: AstrMessageEvent):
        消息内容 = event.message_str.strip()
        参数列表 = list(__builtins__.filter(None, 消息内容.split(" ")))[1:]

        if not 参数列表:
            yield event.plain_result("❌ 缺少账单ID！\n用法：/标记清账 [账单ID]（例：/标记清账 abc123）")
            return

        目标账单ID = 参数列表[0]
        用户ID = event.get_sender_id()
        清账人名称 = event.get_sender_name() or f"用户{用户ID[:4]}"
        清账时间 = datetime.now().strftime("%Y-%m-%d %H:%M")
        目标账单 = None

        for 账单 in self.aa_bills.get(用户ID, []):
            if 账单["账单ID"] == 目标账单ID:
                目标账单 = 账单
                break

        if not 目标账单:
            yield event.plain_result(f"❌ 未找到账单ID「{目标账单ID}」\n💡 用 /查看账单 确认ID")
            return

        if 目标账单["状态"] == "已清账":
            yield event.plain_result(f"✅ 账单「{目标账单ID}」已清账\n清账时间：{目标账单['清账时间']}")
            return

        # 更新状态
        目标账单["状态"] = "已清账"
        目标账单["清账时间"] = 清账时间
        目标账单["清账人"] = 清账人名称
        self._保存数据()

        yield event.plain_result(
            f"✅ 账单「{目标账单ID}」已标记清账！\n"
            f"⏰ 时间：{清账时间}\n"
            f"🧑 操作人：{清账人名称}"
        )

    @filter.message.command("帮助中心")
    async def 帮助中心(self, event: AstrMessageEvent):
        帮助文本 = (
            "📋 AA分账系统帮助（v1.0.4）\n"
            "="*30 + "\n"
            "1. 创建账单\n"
            "   指令：/创建账单 [参与人] [金额] [描述可选]\n"
            "   示例：/创建账单 陈 100 | /创建账单 张三 李四 600 聚餐\n"
            "\n"
            "2. 查看账单\n"
            "   指令：/查看账单\n"
            "   功能：显示最近5条账单及状态\n"
            "\n"
            "3. 对账明细\n"
            "   指令：/对账明细 [账单ID]\n"
            "   示例：/对账明细 abc123\n"
            "\n"
            "4. 标记清账\n"
            "   指令：/标记清账 [账单ID]\n"
            "   示例：/标记清账 abc123\n"
            "\n"
            "5. 帮助中心\n"
            "   指令：/帮助中心\n"
            "   功能：显示本帮助\n"
            "="*30
        )
        yield event.plain_result(帮助文本)

    # 辅助方法
    def _生成债务关系(self, 付款人: str, 参与人列表: List[str], 金额: float) -> List[Dict]:
        return [{"债务人": p, "债权人": 付款人, "金额": 金额} for p in 参与人列表 if p != 付款人]

    def _加载历史数据(self):
        try:
            if os.path.exists(self.bills_path):
                with open(self.bills_path, "r", encoding="utf-8") as f:
                    self.aa_bills = json.load(f)
            if os.path.exists(self.records_path):
                with open(self.records_path, "r", encoding="utf-8") as f:
                    self.settlement_records = json.load(f)
        except Exception as e:
            logger.error(f"加载数据失败：{e}")
            self.aa_bills = {}
            self.settlement_records = {}

    def _保存数据(self):
        try:
            with open(self.bills_path, "w", encoding="utf-8") as f:
                json.dump(self.aa_bills, f, ensure_ascii=False, indent=2)
            with open(self.records_path, "w", encoding="utf-8") as f:
                json.dump(self.settlement_records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存数据失败：{e}")

    async def terminate(self):
        self._save_data()
        logger.info("AA分账系统插件已卸载，数据已保存")
    
