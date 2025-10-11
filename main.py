from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from typing import Dict, List
import json
import os
import time
import uuid


@register(
    "accounting",  # 插件名称
    "anchor",      # 作者
    "简单记账机器人（含AA分账功能）",  # 描述
    "1.4.1"        # 版本
)
class AccountingPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.user_records: Dict[str, List[Dict]] = {}  # 记账记录
        self.aa_bills: Dict[str, List[Dict]] = {}      # AA账单数据
        # 数据路径
        self.acc_data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "accounting_data.json")
        self.aa_data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aa_bills_data.json")
        # 加载数据
        self._load_accounting_data()
        self._load_aa_data()

    # ---------------------- 主指令组 ----------------------
    @filter.command_group("ac")
    def accounting_main_group(self):
        """记账主指令组"""
        pass

    # ---------------------- 基础记账功能 ----------------------
    @accounting_main_group.command("help")
    async def show_help(self, event: AstrMessageEvent):
        """显示帮助"""
        help_text = (
            "📊 记账机器人帮助（v1.4.1 · 修复版）\n"
            "====================\n"
            "【基础记账】\n"
            "/ac + [金额] [来源] [备注] - 加收入（例：/ac + 5000 工资 6月）\n"
            "/ac - [金额] [分类] [备注] - 加支出（例：/ac - 25 餐饮 午餐）\n"
            "/ac 查       - 看最近10条记录\n"
            "/ac 汇总     - 看收支总览\n"
            "/ac 删 [ID]  - 删除记录\n"
            "\n【AA分账】\n"
            "/ac aa [参与人1] [参与人2] [金额] - 创建AA账单\n"
            "/ac aa 对账     - 查看所有AA账单\n"
            "/ac aa 清账 [ID] - 标记AA账单为已清账\n"
            "====================\n"
            "💡 提示：所有金额需大于0，支持小数"
        )
        yield event.plain_result(help_text)

    @accounting_main_group.command("+")
    async def add_income(self, event: AstrMessageEvent, amount: str, source: str, note: str = ""):
        user_id = event.get_sender_id()
        try:
            amount_val = float(amount)
            if amount_val <= 0:
                raise ValueError("金额必须大于0")
        except ValueError as e:
            yield event.plain_result(f"❌ 收入添加失败：{str(e)}")
            return

        timestamp = int(time.time())
        record = {
            "id": str(uuid.uuid4())[:8],
            "type": "income",
            "amount": round(amount_val, 2),
            "source": source,
            "note": note.strip(),
            "create_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp)),
            "timestamp": timestamp
        }

        self.user_records.setdefault(user_id, []).append(record)
        self._save_accounting_data()
        yield event.plain_result(
            f"✅ 收入添加成功！\n"
            f"金额：{record['amount']} | 来源：{source}\n"
            f"时间：{record['create_time']} | ID：{record['id']}"
        )

    @accounting_main_group.command("-")
    async def add_expense(self, event: AstrMessageEvent, amount: str, category: str, note: str = ""):
        user_id = event.get_sender_id()
        try:
            amount_val = float(amount)
            if amount_val <= 0:
                raise ValueError("金额必须大于0")
        except ValueError as e:
            yield event.plain_result(f"❌ 支出添加失败：{str(e)}")
            return

        timestamp = int(time.time())
        record = {
            "id": str(uuid.uuid4())[:8],
            "type": "expense",
            "amount": round(amount_val, 2),
            "category": category,
            "note": note.strip(),
            "create_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp)),
            "timestamp": timestamp
        }

        self.user_records.setdefault(user_id, []).append(record)
        self._save_accounting_data()
        yield event.plain_result(
            f"✅ 支出添加成功！\n"
            f"金额：{record['amount']} | 分类：{category}\n"
            f"时间：{record['create_time']} | ID：{record['id']}"
        )

    @accounting_main_group.command("查")
    async def list_recent_records(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        records = self.user_records.get(user_id, [])
        if not records:
            yield event.plain_result("📒 暂无记账记录")
            return

        sorted_records = sorted(records, key=lambda x: x["timestamp"], reverse=True)[:10]
        output = f"📜 最近{len(sorted_records)}条记录（共{len(records)}条）：\n"
        for idx, rec in enumerate(sorted_records, 1):
            type_tag = "💵 收入" if rec["type"] == "income" else "💸 支出"
            type_extra = f"来源：{rec['source']}" if rec["type"] == "income" else f"分类：{rec['category']}"
            output += (
                f"{idx}. {type_tag} | 金额：{rec['amount']}\n"
                f"   {type_extra} | 备注：{rec['note'] or '无'}\n"
                f"   时间：{rec['create_time']} | ID：{rec['id']}\n"
            )
        yield event.plain_result(output)

    @accounting_main_group.command("汇总")
    async def show_finance_summary(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        records = self.user_records.get(user_id, [])
        if not records:
            yield event.plain_result("📒 暂无记账记录")
            return

        total_income = round(sum(r["amount"] for r in records if r["type"] == "income"), 2)
        total_expense = round(sum(r["amount"] for r in records if r["type"] == "expense"), 2)
        balance = round(total_income - total_expense, 2)

        output = f"📊 收支汇总：\n"
        output += f"💵 总收入：{total_income} | 💸 总支出：{total_expense}\n"
        output += f"📈 结余：{balance}"
        yield event.plain_result(output)

    @accounting_main_group.command("删")
    async def delete_record(self, event: AstrMessageEvent, record_id: str):
        user_id = event.get_sender_id()
        records = self.user_records.get(user_id, [])
        for idx, rec in enumerate(records):
            if rec["id"] == record_id:
                records.pop(idx)
                self._save_accounting_data()
                type_str = "收入" if rec["type"] == "income" else "支出"
                yield event.plain_result(f"✅ 已删除{type_str}记录：{rec['amount']}")
                return
        yield event.plain_result(f"❌ 未找到ID为「{record_id}」的记录")

    # ---------------------- AA分账功能 ----------------------
    @accounting_main_group.command("aa")
    async def handle_aa_all_in_one(self, event: AstrMessageEvent, *args):
        """AA分账总处理函数"""
        user_id = event.get_sender_id()
        current_user = event.get_sender_name() or f"用户{user_id[:4]}"
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        current_timestamp = int(time.time())

        # 操作1：AA对账
        if args and args[0] == "对账":
            async for res in self._show_aa_bills(event):
                yield res
            return

        # 操作2：AA清账
        if len(args) >= 2 and args[0] == "清账":
            bill_id = args[1]
            async for res in self._clear_aa_bill(event, bill_id, current_time):
                yield res
            return

        # 操作3：创建AA账单
        if len(args) < 2:
            yield event.plain_result(
                "❌ AA指令格式错误！正确用法：\n"
                "1. 创建：/ac aa 参与人1 参与人2 金额（例：/ac aa 张三 李四 300）\n"
                "2. 对账：/ac aa 对账\n"
                "3. 清账：/ac aa 清账 账单ID"
            )
            return

        # 解析参数
        amount_str = args[-1]
        participants = list(args[:-1])

        # 验证金额
        try:
            total_amount = float(amount_str)
            if total_amount <= 0:
                raise ValueError("金额必须大于0")
        except ValueError:
            yield event.plain_result(f"❌ 金额错误：请输入数字（如100或250.5）")
            return

        # 处理参与人
        if current_user not in participants:
            participants.append(current_user)
        participants = list(set(participants))
        total_people = len(participants)
        per_person = round(total_amount / total_people, 2)

        # 处理分账误差
        total_calculated = round(per_person * total_people, 2)
        diff = round(total_amount - total_calculated, 2)

        # 生成账单ID
        bill_id = str(uuid.uuid4())[:4]

        # 创建支出记录
        expense_id = str(uuid.uuid4())[:8]
        expense_record = {
            "id": expense_id,
            "type": "expense",
            "amount": round(total_amount, 2),
            "category": "AA制支出",
            "note": f"AA分账-{bill_id}-{', '.join(participants)}",
            "create_time": current_time,
            "timestamp": current_timestamp
        }
        self.user_records.setdefault(user_id, []).append(expense_record)

        # 创建应收记录
        income_records = []
        other_people = [p for p in participants if p != current_user]
        for person in other_people:
            income_id = str(uuid.uuid4())[:8]
            income_record = {
                "id": income_id,
                "type": "income",
                "amount": per_person,
                "source": "AA制应收",
                "note": f"AA分账-{bill_id}-来自{person}",
                "create_time": current_time,
                "timestamp": current_timestamp
            }
            self.user_records.setdefault(user_id, []).append(income_record)
            income_records.append({"person": person, "id": income_id, "amount": per_person})

        # 保存AA账单
        self.aa_bills.setdefault(user_id, []).append({
            "id": bill_id,
            "total_amount": round(total_amount, 2),
            "per_person": per_person,
            "payer": current_user,
            "participants": participants,
            "status": "待清账",
            "create_time": current_time,
            "clear_time": None
        })

        # 保存数据
        self._save_accounting_data()
        self._save_aa_data()

        # 返回结果
        result = (
            f"✅ AA分账完成！\n"
            f"🆔 账单ID：{bill_id}\n"
            f"💵 总金额：{total_amount}元（{total_people}人平摊）\n"
            f"👥 参与人：{', '.join(participants)}\n"
            f"💸 每人：{per_person}元"
        )
        if diff != 0:
            result += f"（你多承担{diff}元误差）"
        yield event.plain_result(result)

    # ---------------------- AA辅助功能 ----------------------
    async def _show_aa_bills(self, event: AstrMessageEvent):
        """查看AA账单"""
        user_id = event.get_sender_id()
        bills = self.aa_bills.get(user_id, [])
        if not bills:
            yield event.plain_result("📋 暂无AA账单\n创建：/ac aa 参与人 金额")
            return

        sorted_bills = sorted(bills, key=lambda x: x["create_time"], reverse=True)
        pending = [b for b in sorted_bills if b["status"] == "待清账"]
        cleared = [b for b in sorted_bills if b["status"] == "已清账"]

        output = "📊 AA对账记录\n"
        output += "========================================\n"

        if pending:
            output += f"🔴 待清账（{len(pending)}条）\n"
            for bill in pending[:5]:
                output += (
                    f"ID: {bill['id']} | 金额: {bill['total_amount']}元\n"
                    f"参与: {', '.join(bill['participants'])} | 每人: {bill['per_person']}元\n"
                    f"操作: /ac aa 清账 {bill['id']}\n"
                    "----------------------------------------\n"
                )

        if cleared:
            output += f"🟢 已清账（{len(cleared)}条）\n"
            for bill in cleared[:3]:
                output += (
                    f"ID: {bill['id']} | 金额: {bill['total_amount']}元\n"
                    f"参与: {', '.join(bill['participants'])} | 清账时间: {bill['clear_time']}\n"
                    "----------------------------------------\n"
                )

        yield event.plain_result(output)

    async def _clear_aa_bill(self, event: AstrMessageEvent, bill_id: str, clear_time: str):
        """标记AA账单为已清账"""
        user_id = event.get_sender_id()
        bills = self.aa_bills.get(user_id, [])
        
        for bill in bills:
            if bill["id"] == bill_id:
                if bill["status"] == "已清账":
                    yield event.plain_result(f"✅ 账单「{bill_id}」已是已清账状态")
                    return
                bill["status"] = "已清账"
                bill["clear_time"] = clear_time
                self._save_aa_data()
                yield event.plain_result(
                    f"✅ 账单「{bill_id}」已标记为清账\n"
                    f"金额: {bill['total_amount']}元 | 参与人: {', '.join(bill['participants'])}"
                )
                return

        yield event.plain_result(f"❌ 未找到ID为「{bill_id}」的AA账单")

    # ---------------------- 数据加载/保存 ----------------------
    def _load_accounting_data(self):
        try:
            if os.path.exists(self.acc_data_path):
                with open(self.acc_data_path, "r", encoding="utf-8") as f:
                    self.user_records = json.load(f)
        except Exception as e:
            self.user_records = {}
            logger.error(f"加载记账数据失败：{str(e)}")

    def _save_accounting_data(self):
        try:
            with open(self.acc_data_path, "w", encoding="utf-8") as f:
                json.dump(self.user_records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存记账数据失败：{str(e)}")

    def _load_aa_data(self):
        try:
            if os.path.exists(self.aa_data_path):
                with open(self.aa_data_path, "r", encoding="utf-8") as f:
                    self.aa_bills = json.load(f)
        except Exception as e:
            self.aa_bills = {}
            logger.error(f"加载AA数据失败：{str(e)}")

    def _save_aa_data(self):
        try:
            with open(self.aa_data_path, "w", encoding="utf-8") as f:
                json.dump(self.aa_bills, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存AA数据失败：{str(e)}")

    async def terminate(self):
        self._save_accounting_data()
        self._save_aa_data()
        logger.info("记账插件已卸载，数据已保存")
