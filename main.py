from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from typing import Dict, List, Optional, Union
import json
import os
import time
import uuid

@register(
    "accounting",
    "anchor",
    "简单记账机器人（含极简AA分账功能）",
    "1.3.9"  # 最终稳定版
)
class AccountingPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.user_records: Dict[str, List[Dict]] = {}
        self.aa_bills: Dict[str, Dict] = {}
        self.data_dir = os.path.dirname(os.path.abspath(__file__))
        self._load_data()

    # === 关键修复 ===
    def _empty(self, *args, **kwargs):
        """框架兼容方法（必须保留）"""
        return None

    # === 主指令组 ===
    @filter.command_group("ac")
    def accounting_main_group(self):
        pass

    # === 基础记账功能 ===
    @accounting_main_group.command("help")
    async def show_help(self, event: AstrMessageEvent):
        help_text = (
            "📊 记账机器人帮助（v1.3.9 稳定版）\n"
            "【基础记账】\n"
            "/ac + [金额] [来源] [备注] - 加收入\n"
            "/ac - [金额] [分类] [备注] - 加支出\n"
            "/ac 查 - 最近10条记录\n"
            "/ac 汇总 - 收支总览\n"
            "/ac 分类 - 支出统计\n"
            "/ac 删 [ID] - 删除记录\n"
            "\n【AA分账】\n"
            "/ac aa [参与人] [金额] - 创建分账\n"
            "/ac aa 对账 - 查看账单\n"
            "/ac aa 清账 [ID] - 标记已付款"
        )
        yield event.plain_result(help_text)

    @accounting_main_group.command("+")
    async def add_income(self, event: AstrMessageEvent, amount: str, source: str, note: str = ""):
        try:
            amount_val = float(amount)
            record = {
                "id": str(uuid.uuid4())[:6],
                "type": "income",
                "amount": round(amount_val, 2),
                "source": source,
                "note": note,
                "time": time.strftime("%Y-%m-%d %H:%M")
            }
            self.user_records.setdefault(event.get_sender_id(), []).append(record)
            self._save_data()
            yield event.plain_result(f"✅ 已记录收入 {record['amount']}元")
        except ValueError:
            yield event.plain_result("❌ 金额必须是数字")

    @accounting_main_group.command("-")
    async def add_expense(self, event: AstrMessage_event, amount: str, category: str, note: str = ""):
        try:
            amount_val = float(amount)
            record = {
                "id": str(uuid.uuid4())[:6],
                "type": "expense",
                "amount": round(amount_val, 2),
                "category": category,
                "note": note,
                "time": time.strftime("%Y-%m-%d %H:%M")
            }
            self.user_records.setdefault(event.get_sender_id(), []).append(record)
            self._save_data()
            yield event.plain_result(f"✅ 已记录支出 {record['amount']}元")
        except ValueError:
            yield event.plain_result("❌ 金额必须是数字")

    # === AA分账功能 ===
    @accounting_main_group.command("aa")
    async def handle_aa(self, event: AstrMessageEvent, *args):
        if not args:
            yield event.plain_result("❌ 参数错误！使用 /ac help 查看帮助")
            return

        if args[0] == "对账":
            yield from self._show_aa_bills(event)
        elif args[0] == "清账" and len(args) > 1:
            yield from self._clear_aa_bill(event, args[1])
        else:
            yield from self._create_aa_bill(event, *args)

    async def _create_aa_bill(self, event: AstrMessageEvent, *args):
        try:
            # 参数解析
            amount = float(args[-1])
            participants = list({p for p in args[:-1]})
            payer = event.get_sender_name() or f"用户{event.get_sender_id()[:4]}"
            
            # 计算分摊
            per_person = round(amount / len(participants), 2)
            bill_id = f"aa{time.strftime('%m%d')}_{uuid.uuid4().hex[:4]}"
            
            # 生成记录
            self._generate_aa_records(
                event.get_sender_id(),
                payer,
                participants,
                amount,
                per_person,
                bill_id
            )
            
            yield event.plain_result(
                f"✅ AA分账成功！\n"
                f"ID: {bill_id}\n"
                f"每人应付: {per_person}元"
            )
        except (ValueError, IndexError):
            yield event.plain_result("❌ 参数格式错误")

    def _generate_aa_records(self, user_id, payer, participants, total, per_person, bill_id):
        """生成AA相关记录"""
        # 付款记录
        self.user_records.setdefault(user_id, []).append({
            "id": str(uuid.uuid4())[:6],
            "type": "expense",
            "amount": total,
            "category": "AA支出",
            "note": f"AA账单#{bill_id}",
            "time": time.strftime("%Y-%m-%d %H:%M"),
            "aa_bill_id": bill_id
        })
        
        # 应收记录
        for p in [x for x in participants if x != payer]:
            self.user_records[user_id].append({
                "id": str(uuid.uuid4())[:6],
                "type": "income",
                "amount": per_person,
                "source": "AA应收",
                "note": f"来自{p}",
                "time": time.strftime("%Y-%m-%d %H:%M"),
                "aa_bill_id": bill_id
            })
        
        # 保存账单
        self.aa_bills[bill_id] = {
            "id": bill_id,
            "payer": payer,
            "amount": total,
            "per_person": per_person,
            "participants": participants,
            "status": "待清账",
            "time": time.time()
        }
        self._save_data()

    async def _show_aa_bills(self, event: AstrMessageEvent):
        if not self.aa_bills:
            yield event.plain_result("📭 暂无AA账单")
            return

        pending = [b for b in self.aa_bills.values() if b["status"] == "待清账"]
        output = ["🔴 待清账账单"] + [
            f"{idx}. ID:{b['id']} 总金额:{b['amount']}元\n  每人应付:{b['per_person']}元"
            for idx, b in enumerate(pending[:5], 1)
        ]
        yield event.plain_result("\n".join(output))

    async def _clear_aa_bill(self, event: AstrMessageEvent, bill_id: str):
        if bill_id in self.aa_bills:
            self.aa_bills[bill_id]["status"] = "已清账"
            self._save_data()
            yield event.plain_result(f"✅ 账单 {bill_id} 已清账")
        else:
            yield event.plain_result("❌ 账单不存在")

    # === 数据操作 ===
    def _load_data(self):
        """加载数据（静默处理错误）"""
        try:
            acc_path = os.path.join(self.data_dir, "accounting_data.json")
            if os.path.exists(acc_path):
                with open(acc_path, "r", encoding="utf-8") as f:
                    self.user_records = json.load(f)
            
            aa_path = os.path.join(self.data_dir, "aa_bills_data.json")
            if os.path.exists(aa_path):
                with open(aa_path, "r", encoding="utf-8") as f:
                    self.aa_bills = json.load(f)
        except:
            self.user_records = {}
            self.aa_bills = {}

    def _save_data(self):
        """保存数据（静默处理错误）"""
        try:
            with open(os.path.join(self.data_dir, "accounting_data.json"), "w", encoding="utf-8") as f:
                json.dump(self.user_records, f, ensure_ascii=False, indent=2)
            
            with open(os.path.join(self.data_dir, "aa_bills_data.json"), "w", encoding="utf-8") as f:
                json.dump(self.aa_bills, f, ensure_ascii=False, indent=2)
        except:
            pass

    async def terminate(self):
        self._save_data()
